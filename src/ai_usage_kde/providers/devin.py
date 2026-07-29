from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from ..core.environment import LoginShellEnvironment
from ..core.http import HttpResponse, http_post_json
from ..core.model import FailureKind, ProviderStatus, ProviderUsage, UsageWindow
from ..core.parsing import non_empty, number, provider_datetime
from ..core.sqlite_store import SQLiteStateStore
from .base import errored, unauthenticated


PROVIDER_ID = "devin"
DISPLAY = "Devin"
ICON = "provider-devin.svg"
DEFAULT_SERVER = "https://server.codeium.com"
SERVICE = "exa.seat_management_pb.SeatManagementService"
VERSION = "1.108.2"


@dataclass(frozen=True)
class DevinCredentials:
    api_key: str
    server_url: Optional[str] = None


class DevinAuthStore:
    def __init__(
        self,
        environment: Optional[LoginShellEnvironment] = None,
        sqlite_store: Optional[SQLiteStateStore] = None,
    ):
        self.environment = environment or LoginShellEnvironment()
        self.sqlite = sqlite_store or SQLiteStateStore()

    def credentials_path(self) -> Path:
        configured = self.environment.value("XDG_DATA_HOME")
        root = Path(configured).expanduser() if configured else Path.home() / ".local" / "share"
        return root / "devin" / "credentials.toml"

    def database_paths(self) -> list[Path]:
        configured = self.environment.value("XDG_CONFIG_HOME")
        config = Path(configured).expanduser() if configured else Path.home() / ".config"
        return [
            config / "Devin" / "User" / "globalStorage" / "state.vscdb",
            config / "devin" / "User" / "globalStorage" / "state.vscdb",
        ]

    def load_candidates(self) -> list[DevinCredentials]:
        candidates: list[DevinCredentials] = []
        file_credentials = self.load_file()
        if file_credentials:
            candidates.append(file_credentials)
        app_credentials = self.load_app()
        if app_credentials and app_credentials not in candidates:
            candidates.append(app_credentials)
        return candidates

    def load_file(self) -> Optional[DevinCredentials]:
        try:
            text = self.credentials_path().read_text(encoding="utf-8")
        except OSError:
            return None
        api_key = self.read_toml_string(text, "windsurf_api_key")
        if api_key is None:
            return None
        server = self.clean_server_url(self.read_toml_string(text, "api_server_url"))
        return DevinCredentials(api_key, server)

    def load_app(self) -> Optional[DevinCredentials]:
        for path in self.database_paths():
            raw = self.sqlite.read(path, "windsurfAuthStatus")
            if raw is None:
                continue
            try:
                value = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            api_key = non_empty(value.get("apiKey")) if isinstance(value, dict) else None
            if api_key:
                return DevinCredentials(api_key)
        return None

    @staticmethod
    def read_toml_string(text: str, key: str) -> Optional[str]:
        for raw in text.splitlines():
            parts = raw.split("=", 1)
            if len(parts) != 2 or parts[0].strip() != key:
                continue
            value = parts[1].strip()
            if not value:
                return None
            if value[0] in "\"'":
                quote = value[0]
                end = value.find(quote, 1)
                if end < 0:
                    return None
                value = value[1:end].strip()
            else:
                value = value.split("#", 1)[0].strip()
            return value or None
        return None

    @staticmethod
    def clean_server_url(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.netloc:
            return None
        return value.strip().rstrip("/")


class DevinProvider:
    id = PROVIDER_ID
    display_name = DISPLAY

    def __init__(
        self,
        auth_store: Optional[DevinAuthStore] = None,
        poster: Callable[..., HttpResponse] = http_post_json,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self._auth = auth_store or DevinAuthStore()
        self._post = poster
        self._now = now or (lambda: datetime.now(timezone.utc))

    def is_configured(self) -> bool:
        return bool(self._auth.load_candidates())

    def fetch(self) -> ProviderUsage:
        candidates = self._auth.load_candidates()
        if not candidates:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Not logged in. Run `devin auth login`.",
            )
        saw_authentication = False
        for credentials in candidates:
            server = credentials.server_url or DEFAULT_SERVER
            try:
                response = self._post(
                    f"{server}/{SERVICE}/GetUserStatus",
                    {
                        "metadata": {
                            "apiKey": credentials.api_key,
                            "ideName": "devin",
                            "ideVersion": VERSION,
                            "extensionName": "devin",
                            "extensionVersion": VERSION,
                            "locale": "en",
                        }
                    },
                    {"Connect-Protocol-Version": "1"},
                )
            except Exception:
                continue
            if response.status in (401, 403):
                saw_authentication = True
                continue
            return self.map(response, self._utc_now())
        if saw_authentication:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Devin session expired. Run `devin auth login`.",
            )
        return errored(
            PROVIDER_ID, DISPLAY, ICON,
            "Devin could not be reached.",
            FailureKind.TRANSIENT,
        )

    @staticmethod
    def map(response: HttpResponse, now: datetime) -> ProviderUsage:
        if not 200 <= response.status < 300:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                f"Devin usage request failed ({response.status}).",
                FailureKind.TRANSIENT if response.status >= 500 else FailureKind.INVALID_RESPONSE,
            )
        try:
            body = response.json()
        except (ValueError, UnicodeDecodeError):
            body = None
        status = body.get("userStatus") if isinstance(body, dict) else None
        if not isinstance(status, dict):
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Devin quota response changed.",
                FailureKind.INVALID_RESPONSE,
            )
        plan_status = status.get("planStatus")
        plan_status = plan_status if isinstance(plan_status, dict) else {}
        plan_info = plan_status.get("planInfo")
        plan_info = plan_info if isinstance(plan_info, dict) else {}
        hides_daily = plan_info.get("hideDailyQuota") is True
        daily_remaining = number(plan_status.get("dailyQuotaRemainingPercent"))
        weekly_remaining = number(plan_status.get("weeklyQuotaRemainingPercent"))
        weekly_reset = provider_datetime(plan_status.get("weeklyQuotaResetAtUnix"))
        windows: list[UsageWindow] = []
        if not hides_daily and daily_remaining is not None:
            windows.append(UsageWindow(
                "Daily",
                "daily",
                min(max(100 - daily_remaining, 0), 100),
                provider_datetime(plan_status.get("dailyQuotaResetAtUnix")),
            ))
        if weekly_remaining is not None:
            windows.append(UsageWindow(
                "Weekly",
                "weekly",
                min(max(100 - weekly_remaining, 0), 100),
                weekly_reset,
            ))
        elif hides_daily and daily_remaining is not None:
            windows.append(UsageWindow(
                "Weekly",
                "weekly",
                min(max(100 - daily_remaining, 0), 100),
                weekly_reset,
            ))
        if not windows:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Devin quota data is unavailable.",
                FailureKind.INVALID_RESPONSE,
            )
        return ProviderUsage(
            provider_id=PROVIDER_ID,
            display_name=DISPLAY,
            icon=ICON,
            plan=non_empty(plan_info.get("planName")),
            status=ProviderStatus.OK,
            error_message=None,
            windows=windows,
            last_updated=now,
        )

    def _utc_now(self) -> datetime:
        value = self._now()
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
