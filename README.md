<div align="center">

# AI Usage — KDE Plasma widget

**Claude Code &amp; Codex subscription usage, native in your Plasma panel.**

[![KDE Plasma 6](https://img.shields.io/badge/KDE%20Plasma-6-1d99f3?logo=kde&logoColor=white)](https://kde.org/plasma-desktop/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/)
![stdlib only](https://img.shields.io/badge/deps-stdlib%20only-44cc11)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

<img src="docs/preview.png" alt="AI Usage plasmoid: a Plasma panel popup showing Claude Code and Codex usage bars and a local token breakdown" width="420">

</div>

A native **KDE Plasma 6** panel widget (plasmoid) that shows your **Claude Code** and **Codex**
subscription usage at a glance: the 5-hour and 7-day rate-limit windows, your plan, extra-usage
credits and reset times — plus a local Claude token/cost breakdown for the current machine. It
looks and behaves like a first-class Plasma widget: theme-/accent-adaptive colors, a frosted popup
with a proper shadow, and it sits on your panel next to your other widgets.

## What it shows

- **Panel badge** — the highest current *session* (5h) usage %, in your theme's text color.
- **Popup**, per provider (Claude Code, Codex):
  - Session (5h) and Weekly (7d) usage bars with threshold colors (accent → neutral → negative as
    you approach the limit) and relative reset times.
  - Plan label, and extra-usage credits when applicable.
  - **Claude local usage** parsed from `~/.claude` transcripts: today's tokens and an
    API-equivalent `$` estimate, the model split, and a 7-day sparkline.
- Codex shows "Not signed in" until you've logged in to the Codex CLI.

## How it works

The plasmoid runs a tiny, dependency-free Python helper — `python3 -m ai_usage_kde --json` —
every few minutes via a Plasma `executable` data source. The helper:

- reads the OAuth token Claude Code stores in `~/.claude/.credentials.json` and calls
  `GET https://api.anthropic.com/api/oauth/usage`;
- reads the Codex token from `~/.codex/auth.json` (or `$CODEX_HOME` / `~/.config/codex`) and calls
  `GET https://chatgpt.com/backend-api/wham/usage`;
- parses your local Claude transcripts for the token/cost breakdown;
- prints a single JSON snapshot, which the plasmoid renders natively.

Your tokens never leave your machine except to call the providers' own usage endpoints.

## Requirements

- KDE Plasma 6 (Qt 6).
- Python 3.11+ — standard library only; the helper has **no** third-party dependencies.

## Install

```bash
# 1. Install the helper (exposes `python3 -m ai_usage_kde --json`)
pip install --user --break-system-packages .

# 2. Install the plasmoid
kpackagetool6 -t Plasma/Applet -i plasmoid
#   update later with:  kpackagetool6 -t Plasma/Applet -u plasmoid

# 3. Right-click your panel → "Add Widgets…" → search "AI Usage" → add it.
```

Log in to **Claude Code** (and optionally the **Codex CLI**) so the tokens exist locally.

## Usage

Refresh runs every 180 s (a safe poll rate) and whenever you open the popup. Middle-click the panel
badge to refresh now; right-click for the context menu.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
QT_QPA_PLATFORM=offscreen python -m pytest
```

The Python backend is fully unit-tested; the QML follows the standard Plasma component patterns
(`PlasmoidItem`, `PlasmaExtras.Representation`, `Kirigami.Theme`).

## Credits

Inspired by [openusage](https://github.com/robinebers/openusage); built natively for KDE Plasma.

## License

[MIT](LICENSE)
