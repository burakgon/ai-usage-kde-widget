from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from ..core.http import http_get, HttpResponse
from ..core.model import Credits, ProviderStatus, ProviderUsage, UsageWindow
from .base import errored, parse_reset, unauthenticated

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
ICON = "codex.svg"
DISPLAY = "Codex"
PROVIDER_ID = "codex"


def _plan_label(plan_type: Optional[str]) -> Optional[str]:
    if not plan_type:
        return None
    return {"plus": "Plus", "pro": "Pro", "team": "Team", "free": "Free"}.get(
        plan_type.lower(), plan_type.capitalize())


class CodexProvider:
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
                                   "Not signed in — log in via the Codex CLI.")
        headers = {
            "Authorization": f"Bearer {self._creds.access_token}",
            "Accept": "application/json",
            "User-Agent": "ai-usage-kde",
        }
        if getattr(self._creds, "account_id", ""):
            headers["ChatGPT-Account-Id"] = self._creds.account_id
        resp = self._get(USAGE_URL, headers=headers)
        if resp.status in (401, 403):
            return errored(PROVIDER_ID, DISPLAY, ICON, "Re-authenticate in the Codex CLI.")
        if resp.status != 200:
            return errored(PROVIDER_ID, DISPLAY, ICON, f"Usage request failed ({resp.status}).")
        try:
            data = resp.json()
        except ValueError:
            return errored(PROVIDER_ID, DISPLAY, ICON, "Couldn't read usage.")
        return self._map(data)

    def _map(self, data: dict) -> ProviderUsage:
        windows: list[UsageWindow] = []
        rl = data.get("rate_limit") or {}

        def add(window: dict, kind: str, caption: str):
            if isinstance(window, dict) and window.get("used_percent") is not None:
                windows.append(UsageWindow(caption=caption, kind=kind,
                                           used_percent=float(window["used_percent"]),
                                           resets_at=parse_reset(window.get("reset_at"))))

        add(rl.get("primary_window") or {}, "session", "Session · 5h")
        add(rl.get("secondary_window") or {}, "weekly", "Weekly · 7d")
        cr = (data.get("code_review_rate_limit") or {}).get("primary_window") or {}
        add(cr, "code_review", "Code review · 7d")

        credits = None
        c = data.get("credits")
        if isinstance(c, dict) and c.get("has_credits"):
            credits = Credits(used=float(c.get("balance", 0)), cap=0.0, currency="USD")

        return ProviderUsage(
            provider_id=PROVIDER_ID, display_name=DISPLAY, icon=ICON,
            plan=_plan_label(data.get("plan_type")), status=ProviderStatus.OK,
            error_message=None, windows=windows, credits=credits,
            last_updated=datetime.now(timezone.utc),
        )
