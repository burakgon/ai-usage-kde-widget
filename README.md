# ai-usage-kde

A native KDE Plasma system-tray tracker for Claude Code and Codex subscription
usage: 5-hour and 7-day window utilization, plan/credits, and a local Claude
token/cost breakdown.

## Requirements
- KDE Plasma 6, Qt 6.11, system `pyside6` package (`sudo pacman -S pyside6`).

## Run
    QT_QUICK_CONTROLS_STYLE=org.kde.desktop python -m ai_usage_kde

## Develop / test
    QT_QPA_PLATFORM=offscreen python -m pytest
