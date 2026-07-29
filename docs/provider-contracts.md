# Provider contracts

The implementation follows
[`ai-usage-menubar` at `3df27e9`](https://github.com/burakgon/ai-usage-menubar/tree/3df27e9081192bc5c954f932e4e807e097a49c02),
using Linux/XDG equivalents for local storage. These endpoints are not public
provider APIs, so sanitized fixture tests protect the known response shapes.

## Discovery and failure behavior

The helper merges the process and login-shell `PATH`, then checks provider CLI
names and local data locations. Only tracked and installed providers are
contacted. Authentication and storage failures clear the widget's previous
reading; transient, rate-limit, and invalid-response failures preserve the
last successful reading in Plasma memory and mark it stale.

`Retry-After` accepts seconds or an HTTP date and defaults to five minutes.
Cooldowns are held in Plasma memory and are not written to disk.

## Claude Code

- Auth: `$CLAUDE_CONFIG_DIR/.credentials.json`, otherwise
  `~/.claude/.credentials.json`
- Usage: `GET https://api.anthropic.com/api/oauth/usage`
- Refresh: `POST https://platform.claude.com/v1/oauth/token`
- Metrics: Session, Weekly, Sonnet, Fable, Extra Usage

The `user:profile` scope is required when scope metadata exists.
`CLAUDE_CODE_OAUTH_TOKEN` setup tokens are intentionally ignored.

## Codex

- Auth: `$CODEX_HOME/auth.json` exclusively when set; otherwise
  `~/.config/codex/auth.json`, `~/.codex/auth.json`, then Secret Service
  `Codex Auth`
- Usage: `GET https://chatgpt.com/backend-api/wham/usage`
- Refresh: `POST https://auth.openai.com/oauth/token`
- Metrics: Session, Weekly, Spark, Spark Weekly, Credits

API-key-only documents are detected but cannot read ChatGPT subscription
usage.

## Cursor

- Auth: `~/.config/Cursor/User/globalStorage/state.vscdb` (plus the legacy
  `~/.cursor` equivalent), then Secret Service services
  `cursor-access-token` and `cursor-refresh-token`
- Usage:
  `POST https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage`
- Plan:
  `POST https://api2.cursor.sh/aiserver.v1.DashboardService/GetPlanInfo`
- Refresh: `POST https://api2.cursor.sh/oauth/token`
- Metrics: Total Usage, Auto Usage, API Usage

## Antigravity

- Auth: Secret Service service `gemini`, username `antigravity`
- OAuth refresh metadata: resolved at runtime from the installed Antigravity IDE
  bundle; no OAuth client credentials are shipped in this repository
- Refresh: `POST https://oauth2.googleapis.com/token`
- Usage: `retrieveUserQuotaSummary`, falling back to
  `fetchAvailableModels`, on Google's daily Cloud Code and Cloud Code hosts
- Plan: `loadCodeAssist`
- Metrics: Gemini Session/Weekly and Claude Session/Weekly

The derived access-token cache is documented in [Privacy](privacy.md).

## GitHub Copilot

- Auth: `~/.config/github-copilot/apps.json`, then `hosts.json`, then
  `~/.config/gh/hosts.yml`, then Secret Service `gh:github.com`
- Usage: `GET https://api.github.com/copilot_internal/user`
- Metrics: Credits, Chat, Completions

Unlimited and zero-entitlement buckets are not rendered.

## Devin

- Auth: `~/.local/share/devin/credentials.toml`, then the Linux Devin
  `state.vscdb`
- Usage:
  `POST /exa.seat_management_pb.SeatManagementService/GetUserStatus` on the
  configured HTTPS server or `https://server.codeium.com`
- Metrics: Daily, Weekly

## Grok

- Auth: `~/.grok/auth.json`
- Refresh: `POST https://auth.x.ai/oauth2/token`
- Usage: `GET https://cli-chat-proxy.grok.com/v1/billing?format=credits`
- Plan: `GET https://cli-chat-proxy.grok.com/v1/settings`
- Metric: Weekly

All credential rotations use source-aware, mode-`0600` writes and avoid
overwriting a concurrent login.
