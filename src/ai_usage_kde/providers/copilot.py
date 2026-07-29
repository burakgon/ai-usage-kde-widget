from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ..core.auth import SecretToolStore
from ..core.environment import LoginShellEnvironment
from ..core.http import HttpResponse, http_get
from ..core.model import FailureKind, ProviderStatus, ProviderUsage, UsageWindow
from ..core.parsing import non_empty, number, provider_datetime, retry_datetime, title_case_identifier, unwrap_go_keyring
from .base import errored, rate_limited, unauthenticated


PROVIDER_ID = "copilot"
DISPLAY = "GitHub Copilot"
ICON = "provider-copilot.svg"
USAGE_URL = "https://api.github.com/copilot_internal/user"
KEYRING_SERVICE = "gh:github.com"


class CopilotAuthStore:
    def __init__(
        self,
        environment: Optional[LoginShellEnvironment] = None,
        secret_store: Optional[SecretToolStore] = None,
    ):
        self.environment = environment or LoginShellEnvironment()
        self.secrets = secret_store or SecretToolStore()

    def paths(self) -> list[Path]:
        configured = self.environment.value("XDG_CONFIG_HOME")
        config = Path(configured).expanduser() if configured else Path.home() / ".config"
        return [
            config / "github-copilot" / "apps.json",
            config / "github-copilot" / "hosts.json",
            config / "gh" / "hosts.yml",
        ]

    def load_token(self) -> Optional[str]:
        for path in self.paths()[:2]:
            try:
                token = self.oauth_token(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            if token:
                return token
        try:
            token = self.yaml_value(self.paths()[2].read_text(encoding="utf-8"), "oauth_token")
        except OSError:
            token = None
        if token:
            return token
        return unwrap_go_keyring(self.secrets.lookup(KEYRING_SERVICE))

    @staticmethod
    def oauth_token(text: str) -> Optional[str]:
        try:
            root = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(root, dict):
            return None
        for host, value in root.items():
            if (
                (host == "github.com" or host.startswith("github.com:"))
                and isinstance(value, dict)
                and (token := non_empty(value.get("oauth_token")))
            ):
                return token
        return None

    @staticmethod
    def yaml_value(text: str, key: str, host: str = "github.com") -> Optional[str]:
        in_host = False
        for raw_line in text.splitlines():
            if raw_line and not raw_line[0].isspace():
                in_host = raw_line.strip().startswith(f"{host}:")
                continue
            if not in_host:
                continue
            stripped = raw_line.strip()
            prefix = f"{key}:"
            if stripped.startswith(prefix):
                return non_empty(stripped[len(prefix):].strip().strip("\"'"))
        return None


class CopilotProvider:
    id = PROVIDER_ID
    display_name = DISPLAY

    def __init__(
        self,
        auth_store: Optional[CopilotAuthStore] = None,
        getter: Callable[..., HttpResponse] = http_get,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self._auth = auth_store or CopilotAuthStore()
        self._get = getter
        self._now = now or (lambda: datetime.now(timezone.utc))

    def is_configured(self) -> bool:
        return self._auth.load_token() is not None

    def fetch(self) -> ProviderUsage:
        token = self._auth.load_token()
        if token is None:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Not logged in. Sign in to GitHub Copilot or run `gh auth login`.",
            )
        try:
            response = self._get(
                USAGE_URL,
                {
                    "Authorization": f"token {token}",
                    "Accept": "application/json",
                    "Editor-Version": "vscode/1.96.2",
                    "Editor-Plugin-Version": "copilot-chat/0.26.7",
                    "User-Agent": "GitHubCopilotChat/0.26.7",
                    "X-Github-Api-Version": "2025-04-01",
                },
            )
        except Exception:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "GitHub Copilot could not be reached.",
                FailureKind.TRANSIENT,
            )
        if response.status in (401, 403):
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "GitHub token expired. Run `gh auth login` again.",
            )
        if response.status == 429:
            return rate_limited(
                PROVIDER_ID, DISPLAY, ICON,
                "GitHub Copilot is rate limited. Try again later.",
                retry_datetime(response.header("retry-after"), self._utc_now()),
            )
        return self.map(response, self._utc_now())

    @staticmethod
    def map(response: HttpResponse, now: datetime) -> ProviderUsage:
        if not 200 <= response.status < 300:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                f"Copilot usage request failed ({response.status}).",
                FailureKind.TRANSIENT if response.status >= 500 else FailureKind.INVALID_RESPONSE,
            )
        try:
            body = response.json()
        except (ValueError, UnicodeDecodeError):
            body = None
        if not isinstance(body, dict):
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Copilot usage response changed.",
                FailureKind.INVALID_RESPONSE,
            )
        reset = provider_datetime(body.get("quota_reset_date"))
        if reset is None:
            reset = provider_datetime(body.get("limited_user_reset_date"))
        snapshots = body.get("quota_snapshots")
        snapshots = snapshots if isinstance(snapshots, dict) else {}
        windows: list[UsageWindow] = []
        for key, kind, caption in (
            ("premium_interactions", "credits", "Credits"),
            ("chat", "chat", "Chat"),
            ("completions", "completions", "Completions"),
        ):
            window = CopilotProvider._quota_window(
                snapshots.get(key), kind, caption, reset,
            )
            if window:
                windows.append(window)
        if not windows:
            limited = body.get("limited_user_quotas")
            monthly = body.get("monthly_quotas")
            limited = limited if isinstance(limited, dict) else {}
            monthly = monthly if isinstance(monthly, dict) else {}
            for key, kind, caption in (
                ("chat", "chat", "Chat"),
                ("completions", "completions", "Completions"),
            ):
                total = number(monthly.get(key))
                remaining = number(limited.get(key))
                if total is not None and total > 0 and remaining is not None:
                    windows.append(UsageWindow(
                        caption,
                        kind,
                        min(max(((total - remaining) / total) * 100, 0), 100),
                        reset,
                    ))
        if not windows and body.get("token_based_billing") is not True:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Copilot usage data is unavailable for this account.",
                FailureKind.INVALID_RESPONSE,
            )
        raw_plan = non_empty(body.get("copilot_plan"))
        return ProviderUsage(
            provider_id=PROVIDER_ID,
            display_name=DISPLAY,
            icon=ICON,
            plan=title_case_identifier(raw_plan) if raw_plan else None,
            status=ProviderStatus.OK,
            error_message=None,
            windows=windows,
            last_updated=now,
        )

    @staticmethod
    def _quota_window(
        value,
        kind: str,
        caption: str,
        reset: Optional[datetime],
    ) -> Optional[UsageWindow]:
        if not isinstance(value, dict):
            return None
        entitlement = number(value.get("entitlement"))
        remaining = number(value.get("remaining"))
        if (
            value.get("unlimited") is True
            or entitlement in (-1, 0)
            or remaining == -1
        ):
            return None
        percent_remaining = number(value.get("percent_remaining"))
        if percent_remaining is not None:
            used = 100 - percent_remaining
        elif entitlement is not None and entitlement > 0 and remaining is not None:
            used = 100 - (remaining / entitlement) * 100
        else:
            return None
        return UsageWindow(caption, kind, min(max(used, 0), 100), reset)

    def _utc_now(self) -> datetime:
        value = self._now()
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
