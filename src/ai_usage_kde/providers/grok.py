from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from ..core.environment import LoginShellEnvironment
from ..core.http import HttpResponse, http_get, http_post_form
from ..core.model import FailureKind, ProviderStatus, ProviderUsage, UsageWindow
from ..core.parsing import jwt_expiration, non_empty, number, provider_datetime
from ..core.storage import atomic_write_private
from .base import errored, unauthenticated


PROVIDER_ID = "grok"
DISPLAY = "Grok"
ICON = "provider-grok.svg"
USAGE_URL = "https://cli-chat-proxy.grok.com/v1/billing?format=credits"
SETTINGS_URL = "https://cli-chat-proxy.grok.com/v1/settings"
REFRESH_URL = "https://auth.x.ai/oauth2/token"
DEFAULT_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
WEEKLY_PERIOD = "USAGE_PERIOD_TYPE_WEEKLY"


@dataclass
class GrokCredentials:
    document: dict
    entry_key: str
    entry: dict
    token: str
    path: Path
    raw_text: str


class GrokAuthStore:
    def __init__(
        self,
        environment: Optional[LoginShellEnvironment] = None,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self.environment = environment or LoginShellEnvironment()
        self._now = now or (lambda: datetime.now(timezone.utc))

    def auth_path(self) -> Path:
        return Path.home() / ".grok" / "auth.json"

    def load_candidates(self) -> list[GrokCredentials]:
        path = self.auth_path()
        try:
            raw = path.read_text(encoding="utf-8")
            root = json.loads(raw)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return []
        if not isinstance(root, dict):
            return []
        candidates = []
        for entry_key, entry in root.items():
            token = non_empty(entry.get("key")) if isinstance(entry, dict) else None
            if token:
                candidates.append(GrokCredentials(
                    root,
                    entry_key,
                    copy.deepcopy(entry),
                    token,
                    path,
                    raw,
                ))
        return candidates

    def save(self, credentials: GrokCredentials) -> bool:
        document = copy.deepcopy(credentials.document)
        document[credentials.entry_key] = credentials.entry
        serialized = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
        saved = atomic_write_private(
            credentials.path,
            serialized,
            expected_text=credentials.raw_text,
        )
        if saved:
            credentials.document = document
            credentials.raw_text = serialized
        return saved

    def expiration(self, credentials: GrokCredentials) -> Optional[datetime]:
        return (
            jwt_expiration(credentials.token)
            or provider_datetime(credentials.entry.get("expires_at"))
            or provider_datetime(credentials.entry.get("expires"))
        )

    def needs_refresh(self, credentials: GrokCredentials) -> bool:
        expiration = self.expiration(credentials)
        return expiration is not None and (
            expiration - self._utc_now()
        ).total_seconds() <= 300

    def is_expired(self, credentials: GrokCredentials) -> bool:
        expiration = self.expiration(credentials)
        return expiration is not None and self._utc_now() >= expiration

    @staticmethod
    def refresh_token(credentials: GrokCredentials) -> Optional[str]:
        return (
            non_empty(credentials.entry.get("refresh_token"))
            or non_empty(credentials.entry.get("refresh"))
        )

    @staticmethod
    def client_id(credentials: GrokCredentials) -> str:
        explicit = non_empty(credentials.entry.get("oidc_client_id"))
        if explicit:
            return explicit
        suffix = credentials.entry_key.split("::")[-1].strip()
        return suffix or DEFAULT_CLIENT_ID

    def _utc_now(self) -> datetime:
        value = self._now()
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )


class GrokProvider:
    id = PROVIDER_ID
    display_name = DISPLAY

    def __init__(
        self,
        auth_store: Optional[GrokAuthStore] = None,
        getter: Callable[..., HttpResponse] = http_get,
        form_poster: Callable[..., HttpResponse] = http_post_form,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._auth = auth_store or GrokAuthStore(now=self._now)
        self._get = getter
        self._post_form = form_poster

    def is_configured(self) -> bool:
        return bool(self._auth.load_candidates())

    def fetch(self) -> ProviderUsage:
        candidates = self._auth.load_candidates()
        if not candidates:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Not logged in. Run `grok login`.",
            )
        saw_expired = False
        for credentials in candidates:
            if self._auth.needs_refresh(credentials):
                refreshed, failure = self._refresh(credentials)
                if failure is not None:
                    return failure
                if not refreshed:
                    saw_expired = saw_expired or self._auth.is_expired(credentials)
                    continue
            response = self._request(USAGE_URL, credentials.token)
            if response is None:
                continue
            if response.status in (401, 403):
                refreshed, failure = self._refresh(credentials)
                if failure is not None:
                    return failure
                if not refreshed:
                    saw_expired = True
                    continue
                response = self._request(USAGE_URL, credentials.token)
                if response is None:
                    continue
            if response.status in (401, 403):
                saw_expired = True
                continue
            plan_response = self._request(SETTINGS_URL, credentials.token)
            return self.map(response, plan_response, self._utc_now())
        if saw_expired:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Grok session expired. Run `grok login`.",
            )
        return errored(
            PROVIDER_ID, DISPLAY, ICON,
            "Grok could not be reached.",
            FailureKind.TRANSIENT,
        )

    def _request(self, url: str, token: str) -> Optional[HttpResponse]:
        try:
            return self._get(url, {
                "Authorization": f"Bearer {token}",
                "X-XAI-Token-Auth": "xai-grok-cli",
                "Accept": "application/json",
                "User-Agent": "AIUsage/0.1",
            })
        except Exception:
            return None

    def _refresh(
        self,
        credentials: GrokCredentials,
    ) -> tuple[bool, Optional[ProviderUsage]]:
        refresh_token = self._auth.refresh_token(credentials)
        if refresh_token is None:
            return False, None
        try:
            response = self._post_form(
                REFRESH_URL,
                [
                    ("grant_type", "refresh_token"),
                    ("client_id", self._auth.client_id(credentials)),
                    ("refresh_token", refresh_token),
                ],
                {},
            )
            body = response.json()
        except Exception:
            return False, None
        access_token = non_empty(body.get("access_token")) if isinstance(body, dict) else None
        if not 200 <= response.status < 300 or access_token is None:
            return False, None
        credentials.token = access_token
        credentials.entry["key"] = access_token
        if token := non_empty(body.get("refresh_token")):
            credentials.entry["refresh_token"] = token
        if token := non_empty(body.get("id_token")):
            credentials.entry["id_token"] = token
        expires_in = number(body.get("expires_in"))
        expiration = (
            self._utc_now() + timedelta(seconds=expires_in)
            if expires_in is not None
            else jwt_expiration(access_token)
        )
        if expiration:
            credentials.entry["expires_at"] = expiration.isoformat()
        if not self._auth.save(credentials):
            return False, errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Grok credentials could not be updated.",
                FailureKind.STORAGE,
            )
        return True, None

    @staticmethod
    def map(
        response: HttpResponse,
        plan_response: Optional[HttpResponse],
        now: datetime,
    ) -> ProviderUsage:
        if not 200 <= response.status < 300:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                f"Grok usage request failed ({response.status}).",
                FailureKind.TRANSIENT if response.status >= 500 else FailureKind.INVALID_RESPONSE,
            )
        try:
            body = response.json()
        except (ValueError, UnicodeDecodeError):
            body = None
        config = body.get("config") if isinstance(body, dict) else None
        period = config.get("currentPeriod") if isinstance(config, dict) else None
        period_type = non_empty(period.get("type")) if isinstance(period, dict) else None
        reset = provider_datetime(period.get("end")) if isinstance(period, dict) else None
        if not isinstance(config, dict) or period_type is None or reset is None:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Grok quota response changed.",
                FailureKind.INVALID_RESPONSE,
            )
        windows = []
        if period_type == WEEKLY_PERIOD:
            used = number(config.get("creditUsagePercent"))
            windows.append(UsageWindow(
                "Weekly",
                "weekly",
                min(max(used if used is not None else 0, 0), 100),
                reset,
            ))
        if not windows:
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Grok weekly quota is unavailable for this account.",
                FailureKind.INVALID_RESPONSE,
            )
        plan = None
        if plan_response is not None and 200 <= plan_response.status < 300:
            try:
                plan_body = plan_response.json()
                plan = (
                    non_empty(plan_body.get("subscription_tier_display"))
                    if isinstance(plan_body, dict)
                    else None
                )
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
