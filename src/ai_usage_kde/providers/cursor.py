from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ..core.auth import SecretToolStore
from ..core.environment import LoginShellEnvironment
from ..core.http import HttpResponse, http_post_json
from ..core.model import FailureKind, ProviderStatus, ProviderUsage, UsageWindow
from ..core.parsing import jwt_expiration, jwt_payload, non_empty, number, provider_datetime, retry_datetime
from ..core.sqlite_store import SQLiteStateStore
from .base import errored, rate_limited, unauthenticated


PROVIDER_ID = "cursor"
DISPLAY = "Cursor"
ICON = "provider-cursor.svg"
USAGE_URL = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage"
PLAN_URL = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetPlanInfo"
REFRESH_URL = "https://api2.cursor.sh/oauth/token"
CLIENT_ID = "KbZUR41cY7W6zRSdpSUJ7I7mLYBKOCmB"

ACCESS_KEY = "cursorAuth/accessToken"
REFRESH_KEY = "cursorAuth/refreshToken"
MEMBERSHIP_KEY = "cursorAuth/stripeMembershipType"
ACCESS_SERVICE = "cursor-access-token"
REFRESH_SERVICE = "cursor-refresh-token"


@dataclass(frozen=True)
class CursorCredentialSource:
    kind: str
    path: Optional[Path] = None
    expected_access_token: Optional[str] = None


@dataclass
class CursorCredentials:
    access_token: Optional[str]
    refresh_token: Optional[str]
    source: CursorCredentialSource


class CursorAuthStore:
    def __init__(
        self,
        environment: Optional[LoginShellEnvironment] = None,
        sqlite_store: Optional[SQLiteStateStore] = None,
        secret_store: Optional[SecretToolStore] = None,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self.environment = environment or LoginShellEnvironment()
        self.sqlite = sqlite_store or SQLiteStateStore()
        self.secrets = secret_store or SecretToolStore()
        self._now = now or (lambda: datetime.now(timezone.utc))

    def database_paths(self) -> list[Path]:
        configured = self.environment.value("XDG_CONFIG_HOME")
        config = Path(configured).expanduser() if configured else Path.home() / ".config"
        return [
            config / "Cursor" / "User" / "globalStorage" / "state.vscdb",
            Path.home() / ".cursor" / "User" / "globalStorage" / "state.vscdb",
        ]

    def load(self) -> Optional[CursorCredentials]:
        keychain_access = non_empty(self.secrets.lookup(ACCESS_SERVICE))
        keychain_refresh = non_empty(self.secrets.lookup(REFRESH_SERVICE))
        for path in self.database_paths():
            sqlite_access = non_empty(self.sqlite.read(path, ACCESS_KEY))
            sqlite_refresh = non_empty(self.sqlite.read(path, REFRESH_KEY))
            if sqlite_access is None and sqlite_refresh is None:
                continue
            membership = (self.sqlite.read(path, MEMBERSHIP_KEY) or "").lower()
            sqlite_subject = self._subject(sqlite_access)
            keychain_subject = self._subject(keychain_access)
            if (
                membership == "free"
                and sqlite_subject
                and keychain_subject
                and sqlite_subject != keychain_subject
                and (keychain_access or keychain_refresh)
            ):
                return CursorCredentials(
                    keychain_access,
                    keychain_refresh,
                    CursorCredentialSource(
                        "secret_service",
                        expected_access_token=keychain_access,
                    ),
                )
            return CursorCredentials(
                sqlite_access,
                sqlite_refresh,
                CursorCredentialSource("sqlite", path, sqlite_access),
            )
        if keychain_access or keychain_refresh:
            return CursorCredentials(
                keychain_access,
                keychain_refresh,
                CursorCredentialSource(
                    "secret_service",
                    expected_access_token=keychain_access,
                ),
            )
        return None

    def needs_refresh(self, access_token: Optional[str]) -> bool:
        expiration = jwt_expiration(access_token or "")
        return expiration is None or (expiration - self._utc_now()).total_seconds() <= 300

    def save_access_token(self, credentials: CursorCredentials, token: str) -> bool:
        source = credentials.source
        if source.kind == "sqlite" and source.path is not None:
            return self.sqlite.compare_and_swap(
                source.path,
                ACCESS_KEY,
                expected=source.expected_access_token,
                value=token,
            )
        if source.kind == "secret_service":
            current = non_empty(self.secrets.lookup(ACCESS_SERVICE))
            return (
                current == source.expected_access_token
                and self.secrets.store(
                    ACCESS_SERVICE,
                    None,
                    token,
                    label="Cursor access token",
                )
            )
        return False

    @staticmethod
    def _subject(token: Optional[str]) -> Optional[str]:
        body = jwt_payload(token or "")
        return non_empty(body.get("sub")) if body else None

    def _utc_now(self) -> datetime:
        value = self._now()
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )


class CursorProvider:
    id = PROVIDER_ID
    display_name = DISPLAY

    def __init__(
        self,
        auth_store: Optional[CursorAuthStore] = None,
        poster: Callable[..., HttpResponse] = http_post_json,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._auth = auth_store or CursorAuthStore(now=self._now)
        self._post = poster

    def is_configured(self) -> bool:
        return self._auth.load() is not None

    def fetch(self) -> ProviderUsage:
        credentials = self._auth.load()
        if credentials is None:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Not logged in. Sign in through Cursor.",
            )
        if self._auth.needs_refresh(credentials.access_token):
            failure = self._refresh(credentials)
            if failure is not None:
                return failure
        token = non_empty(credentials.access_token)
        if token is None:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Cursor session expired. Sign in again.",
            )
        response = self._request(USAGE_URL, token)
        if isinstance(response, ProviderUsage):
            return response
        if response.status in (401, 403):
            failure = self._refresh(credentials)
            if failure is not None:
                return failure
            token = credentials.access_token or ""
            response = self._request(USAGE_URL, token)
            if isinstance(response, ProviderUsage):
                return response
        if response.status in (401, 403):
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Cursor session expired. Sign in again.",
            )
        if response.status == 429:
            return rate_limited(
                PROVIDER_ID, DISPLAY, ICON,
                "Cursor is rate limited. Try again later.",
                retry_datetime(response.header("retry-after"), self._utc_now()),
            )
        plan = self._request(PLAN_URL, token)
        plan_response = plan if isinstance(plan, HttpResponse) else None
        return self.map(response, plan_response, self._utc_now())

    def _request(self, url: str, token: str) -> HttpResponse | ProviderUsage:
        try:
            return self._post(
                url,
                {},
                {
                    "Authorization": f"Bearer {token}",
                    "Connect-Protocol-Version": "1",
                },
            )
        except Exception:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Cursor could not be reached.",
                FailureKind.TRANSIENT,
            )

    def _refresh(self, credentials: CursorCredentials) -> Optional[ProviderUsage]:
        refresh_token = non_empty(credentials.refresh_token)
        if refresh_token is None:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Cursor session expired. Sign in again.",
            )
        try:
            response = self._post(
                REFRESH_URL,
                {
                    "grant_type": "refresh_token",
                    "client_id": CLIENT_ID,
                    "refresh_token": refresh_token,
                },
                {},
            )
        except Exception:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Cursor could not refresh its session.",
                FailureKind.TRANSIENT,
            )
        try:
            body = response.json()
        except (ValueError, UnicodeDecodeError):
            body = None
        token = non_empty(body.get("access_token")) if isinstance(body, dict) else None
        if (
            not 200 <= response.status < 300
            or not token
            or (isinstance(body, dict) and body.get("shouldLogout") is True)
        ):
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Cursor session expired. Sign in again.",
            )
        if not self._auth.save_access_token(credentials, token):
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Cursor session could not be saved.",
                FailureKind.STORAGE,
            )
        credentials.access_token = token
        credentials.source = CursorCredentialSource(
            credentials.source.kind,
            credentials.source.path,
            token,
        )
        return None

    @staticmethod
    def map(
        usage: HttpResponse,
        plan_response: Optional[HttpResponse],
        now: datetime,
    ) -> ProviderUsage:
        if not 200 <= usage.status < 300:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                f"Cursor usage request failed ({usage.status}).",
                FailureKind.TRANSIENT if usage.status >= 500 else FailureKind.INVALID_RESPONSE,
            )
        try:
            body = usage.json()
        except (ValueError, UnicodeDecodeError):
            body = None
        plan_usage = body.get("planUsage") if isinstance(body, dict) else None
        if isinstance(body, dict) and body.get("enabled") is False:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "No active Cursor subscription.",
            )
        if not isinstance(plan_usage, dict):
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Cursor quota response changed.",
                FailureKind.INVALID_RESPONSE,
            )
        reset = provider_datetime(body.get("billingCycleEnd"))
        values: list[tuple[str, str, Optional[float]]] = [
            ("total_usage", "Total Usage", number(plan_usage.get("totalPercentUsed"))),
            ("auto_usage", "Auto Usage", number(plan_usage.get("autoPercentUsed"))),
            ("api_usage", "API Usage", number(plan_usage.get("apiPercentUsed"))),
        ]
        if values[0][2] is None:
            limit = number(plan_usage.get("limit"))
            if limit is not None and limit > 0:
                spent = number(plan_usage.get("totalSpend"))
                if spent is None:
                    remaining = number(plan_usage.get("remaining"))
                    spent = limit - (remaining if remaining is not None else limit)
                values[0] = ("total_usage", "Total Usage", spent / limit * 100)
        windows = [
            UsageWindow(caption, kind, min(max(value, 0), 100), reset)
            for kind, caption, value in values
            if value is not None
        ]
        if not windows:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Cursor quota response changed.",
                FailureKind.INVALID_RESPONSE,
            )
        plan = None
        if plan_response is not None and 200 <= plan_response.status < 300:
            try:
                plan_body = plan_response.json()
                info = plan_body.get("planInfo") if isinstance(plan_body, dict) else None
                plan = non_empty(info.get("planName")) if isinstance(info, dict) else None
            except (ValueError, UnicodeDecodeError):
                pass
        return ProviderUsage(
            provider_id=PROVIDER_ID,
            display_name=DISPLAY,
            icon=ICON,
            plan=plan,
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
