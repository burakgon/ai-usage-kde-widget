from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from ..core.http import http_get, HttpResponse
from ..core.model import Credits, ProviderStatus, ProviderUsage, UsageWindow
from .base import errored, parse_reset, unauthenticated

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
# Track a current Claude Code version; a real UA is required to avoid 429 buckets.
CLAUDE_CODE_VERSION = "2.1.69"
ICON = "claude.svg"
DISPLAY = "Claude Code"
PROVIDER_ID = "claude"

_PLAN_LABELS = {"default_max_20x": "Max 20x", "default_max_5x": "Max 5x", "default_pro": "Pro"}


def _plan_label(creds) -> Optional[str]:
    tier = getattr(creds, "rate_limit_tier", "") or ""
    if tier in _PLAN_LABELS:
        return _PLAN_LABELS[tier]
    sub = getattr(creds, "subscription_type", "") or ""
    return sub.capitalize() if sub else None


class ClaudeProvider:
    id = PROVIDER_ID
    display_name = DISPLAY

    def __init__(self, creds=None, getter: Callable[..., HttpResponse] = http_get):
        self._creds = creds
        self._get = getter

    def is_configured(self) -> bool:
        return self._creds is not None

    def fetch(self) -> ProviderUsage:
        if self._creds is None:
            return unauthenticated(PROVIDER_ID, DISPLAY, ICON,
                                   "Not signed in — log in via Claude Code.")
        headers = {
            "Authorization": f"Bearer {self._creds.access_token.strip()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": f"claude-code/{CLAUDE_CODE_VERSION}",
        }
        resp = self._get(USAGE_URL, headers=headers)
        if resp.status in (401, 403):
            return errored(PROVIDER_ID, DISPLAY, ICON,
                           "Re-authenticate in Claude Code.")
        if resp.status != 200:
            return errored(PROVIDER_ID, DISPLAY, ICON, f"Usage request failed ({resp.status}).")
        try:
            data = resp.json()
        except ValueError:
            return errored(PROVIDER_ID, DISPLAY, ICON, "Couldn't read usage.")
        return self._map(data)

    def _map(self, data: dict) -> ProviderUsage:
        windows: list[UsageWindow] = []

        def add(key, kind, caption):
            w = data.get(key)
            if isinstance(w, dict) and w.get("utilization") is not None:
                windows.append(UsageWindow(caption=caption, kind=kind,
                                           used_percent=float(w["utilization"]),
                                           resets_at=parse_reset(w.get("resets_at"))))

        add("five_hour", "session", "Session · 5h")
        add("seven_day", "weekly", "Weekly · 7d")
        add("seven_day_omelette", "weekly_opus", "Weekly · Opus")

        credits = None
        ex = data.get("extra_usage")
        if isinstance(ex, dict) and ex.get("is_enabled"):
            credits = Credits(used=float(ex.get("used_credits", 0)),
                              cap=float(ex.get("monthly_limit", 0)), currency="USD")

        return ProviderUsage(
            provider_id=PROVIDER_ID, display_name=DISPLAY, icon=ICON,
            plan=_plan_label(self._creds), status=ProviderStatus.OK, error_message=None,
            windows=windows, credits=credits, last_updated=datetime.now(timezone.utc),
        )
