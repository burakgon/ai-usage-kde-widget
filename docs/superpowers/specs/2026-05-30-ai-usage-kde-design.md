# ai-usage-kde — Design Spec

- **Date:** 2026-05-30
- **Status:** Approved (brainstorming complete)
- **Display name:** "AI Usage" · **Package:** `ai-usage-kde`

## 1. Summary

A lightweight AI-coding-subscription usage tracker for KDE Plasma. It lives in the
system tray; clicking the tray icon opens a Breeze-styled Kirigami popup showing,
for **Claude Code** and **Codex**:

- Live plan usage — 5-hour (session) and 7-day (weekly) window utilization %, plan
  tier, credits/overage, and reset times.
- (Claude) a local token & cost breakdown parsed from `~/.claude` transcripts.

It is a focused, native-KDE reimplementation of the relevant parts of
[openusage](https://github.com/robinebers/openusage) (a macOS Tauri menu-bar app),
limited to the two providers above. All UI text is in **English**.

## 2. Goals & non-goals

**Goals**
- Native KDE look (Kirigami + Breeze) and behavior (system tray / StatusNotifierItem).
- Faithful "layout A" popup: per-provider sections with labeled horizontal bars.
- Accurate live usage via the same authenticated endpoints openusage uses.
- Local Claude token/cost breakdown (ccusage-style) computed in-process.
- Robust background refresh, graceful degradation when a provider isn't signed in.

**Non-goals (YAGNI — may revisit later)**
- The other 17 openusage providers (Cursor, Copilot, Gemini, …).
- openusage's local HTTP API on `127.0.0.1:6736`.
- Global keyboard shortcut, proxy routing, ccusage as an external dependency.
- Packaging to AUR/Flatpak in v1 (autostart .desktop is enough to start).
- Codex *local* token parsing — v1 shows Codex **live** usage only. (Codex CLI
  isn't installed here to verify the rollout-log format; Claude local tokens are
  fully supported and testable. Codex local parsing can be added later.)

## 3. Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Popup layout | **A** — faithful list rows: each provider a section with labeled bars |
| UI language | **English**, entirely |
| Form factor | **System-tray app** (icon in panel → popup), like a macOS menu-bar app |
| Tech | **Python 3 + PySide6 (Qt6)** backend · **QML + Kirigami** UI |
| Metrics | **Live plan usage + local token/cost** breakdown |
| Refresh | 180 s background timer (the safe interval); refresh-on-popup-open |
| Tray badge | Highest current **session** % across providers, threshold-colored |

## 4. Architecture

- **Single process.** `QApplication` hosts a `QSystemTrayIcon` (KDE renders it via the
  StatusNotifierItem protocol) and a QML engine for the popup.
- **Backend (Python/PySide6):** networking, OAuth token read/refresh, JSONL parsing,
  timers, threshold logic. Network/parse work runs off the GUI thread (QThreadPool)
  so the UI never blocks.
- **UI (QML/Kirigami):** `QT_QUICK_CONTROLS_STYLE=org.kde.desktop` ensures native Breeze
  controls. The popup is a frameless QML window positioned at the tray icon.
- **State bridge:** a `Controller` `QObject` exposed to QML holds the current
  `ProviderUsage` list and emits change signals; QML binds to it.

## 5. Components

```
main.py                  # QApplication, tray icon + menu, QML engine, theme env
core/controller.py       # QObject exposed to QML: state, QTimer(180s), refresh orchestration, signals
core/config.py           # QSettings: refresh interval, badge on/off, autostart, enabled providers
core/auth.py             # token discovery + OAuth refresh (proactive 5m before expiry, reactive on 401/403)
core/tray.py             # QSystemTrayIcon, dynamically painted badge (QPainter), context menu
providers/base.py        # Provider interface: id, display_name, icon, is_configured(), fetch() -> ProviderUsage
providers/claude.py      # ~/.claude/.credentials.json -> GET https://api.anthropic.com/api/oauth/usage
providers/codex.py       # ~/.codex/auth.json (+ CODEX_HOME, ~/.config/codex) -> GET https://chatgpt.com/backend-api/wham/usage
usage/local_claude.py    # parse ~/.claude/projects/**/*.jsonl -> tokens & cost (mtime/size cache)
usage/pricing.py         # per-model price table + cost computation
qml/Main.qml             # popup window: header + ProviderSection list + footer
qml/ProviderSection.qml  # provider header (icon, name, plan tag) + UsageBar list + local block
qml/UsageBar.qml         # labeled bar: caption, %, reset text, threshold color
qml/LocalBlock.qml       # Claude local: today tokens / ~$ equiv / model split / 7-day sparkline
qml/Settings.qml         # refresh interval, badge toggle, autostart toggle
resources/               # provider icons (claude.svg, codex.svg), app icon
```

## 6. Data model (backend → QML)

```
UsageWindow   = { caption: str, kind: "session"|"weekly"|"opus"|..., used_percent: float, resets_at: datetime|None }
Credits       = { used: float, cap: float, currency: str } | None
ProviderUsage = {
    provider_id: str, display_name: str, icon: str, plan: str|None,
    status: "ok"|"unauthenticated"|"error"|"stale",
    error_message: str|None,
    windows: [UsageWindow], credits: Credits, last_updated: datetime|None,
}
LocalClaudeUsage = {
    today_tokens: int, today_cost_usd: float,
    model_split: { model_name: percent },   # e.g. {"opus": 0.71, "sonnet": 0.29}
    last7days: [ { date, tokens, cost_usd } ],
}
```

Thresholds (applied in UI per window): `0–60%` normal (Breeze blue `#3daee9`),
`60–85%` warning (`#f67400`), `85%+` critical (`#da4453`).

## 7. Data sources & auth

### Claude Code
- **Token:** read `~/.claude/.credentials.json` → `claudeAiOauth.accessToken`
  (fields present on this machine: `accessToken`, `refreshToken`, `expiresAt`,
  `scopes`, `subscriptionType`, `rateLimitTier`). Refresh with `refreshToken` when
  `expiresAt` is near or on HTTP 401/403.
- **Endpoint:** `GET https://api.anthropic.com/api/oauth/usage`
- **Headers:** `Authorization: Bearer <token>`, `anthropic-beta: oauth-2025-04-20`,
  `Accept: application/json`, `Content-Type: application/json`,
  `User-Agent: claude-code/<version>` (required to avoid aggressive 429 buckets;
  safe at ≥180 s intervals, per the documented behavior).
- **Maps to:** session (5h) %, weekly (7d) %, optional Opus model limit, extra
  usage/credits (spent, monthly cap, currency).

### Codex
- **Token:** first existing of `$CODEX_HOME/auth.json`, `~/.config/codex/auth.json`,
  `~/.codex/auth.json`. Fields: `access_token`, `refresh_token`, `id_token`,
  `account_id`. (Not present on this machine yet → section shows "Not signed in".)
- **Endpoint:** `GET https://chatgpt.com/backend-api/wham/usage`
- **Headers:** `Authorization: Bearer <access_token>`, optional `ChatGPT-Account-Id: <account_id>`.
- **Maps to:** session (5h) %, weekly (7d) %, plan tier, credits balance/status,
  optional code-review weekly allocation.

### Local Claude tokens (no network)
- Parse `~/.claude/projects/**/*.jsonl`; each assistant line carries
  `message.usage` = `{ input_tokens, cache_creation_input_tokens,
  cache_read_input_tokens, output_tokens, ... }` plus `message.model` and a
  top-level `timestamp`.
- Aggregate tokens and **estimated API-equivalent cost** per day and per model.
- **Cache:** remember each file's `(size, mtime)` and last byte offset; only re-read
  appended/changed files. (215 transcripts on this machine today.)
- Subscription users don't pay per token, so cost is labeled "~$ API-equivalent".

### Field-shape confirmation (impl-time)
Exact JSON field names for the two usage endpoints will be confirmed by reading
openusage's `plugins/claude/plugin.js` and `plugins/codex/plugin.js` (authoritative,
no live call needed). Parsers will be written defensively against missing fields.
Claude's local pricing table seeds from openusage's `scripts/bump-ccusage-version.mjs`
data / public model pricing.

## 8. Data flow

1. On start and every 180 s (`QTimer`), `Controller` dispatches each enabled,
   configured provider's `fetch()` to a worker thread.
2. `fetch()` reads the token, refreshes if needed, calls the usage endpoint, and
   returns a normalized `ProviderUsage`.
3. On popup open, `local_claude` recomputes (from cache + changed files) the local block.
4. `Controller` updates exposed state → QML re-renders; tray badge = max session %.
5. Failures map to a `status` and a friendly per-section message (see §9).

## 9. Error handling

| Condition | Behavior |
|---|---|
| No credentials file / unauthenticated | Section: "Not signed in" + hint to log in via the CLI |
| 401/403 | Attempt one token refresh; if it still fails → "Re-authenticate in Claude Code / Codex CLI" |
| Network error / timeout | Keep last-known data, mark `stale` with a subtle indicator + retry next tick |
| 429 rate limited | Back off; never poll faster than 180 s |
| Malformed/empty usage JSON | Section: "Couldn't read usage" (log details); other providers unaffected |
| Local parse error on a file | Skip that file, continue; never crash the aggregate |

## 10. Config, autostart & packaging

- **Config:** `QSettings` (`~/.config/ai-usage-kde/...`) — refresh interval, badge
  on/off, autostart on/off, enabled providers.
- **Autostart:** toggling writes/removes `~/.config/autostart/ai-usage-kde.desktop`.
- **Run:** a venv with `PySide6`; entry `python -m ai_usage_kde` or a console script
  via `pyproject.toml`. Kirigami runtime is already present on Plasma.

## 11. Testing

- **Unit:** JSONL → token aggregation; pricing math; usage-JSON → `ProviderUsage`
  mapping. Fixtures derived from real `~/.claude` transcripts (sanitized) and from
  sample usage payloads (shape per openusage plugin docs). No secrets committed.
- **Auth:** token-refresh logic with a mocked HTTP layer (expiry, 401-then-refresh).
- **Caching:** local parser only re-reads changed files (mtime/size + offset).
- **UI:** manual verification in a running Plasma session (tray, popup, thresholds,
  badge, settings, autostart toggle).

## 12. Environment

- KDE Plasma 6, Qt 6.11 (present), KDE Frameworks 6 (`kreadconfig6` present).
- Python 3 + `PySide6` (Qt6 bindings). Kirigami QML modules from the system.
- Verified on this machine: `~/.claude` with tokens + 215 transcripts; `~/.codex` absent.

## 13. Open items to confirm during implementation

1. Exact JSON field names from the two usage endpoints (via openusage `plugin.js`).
2. Whether the OAuth usage response exposes Opus/"Claude Design" sub-limits to show.
3. PySide6 install path on CachyOS (system `python-pyside6` vs pip in venv).
4. Frameless-popup positioning details across single/multi-monitor panels.
