from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from ..core.auth import CodexAuthStore, CodexCredentials
from ..core.http import HttpResponse, http_get, http_post_form
from ..core.model import BillingUsage, FailureKind, ProviderStatus, ProviderUsage, UsageWindow
from ..core.parsing import (
    non_empty,
    number,
    provider_datetime,
    retry_datetime,
    title_case_identifier,
)
from .base import errored, rate_limited, unauthenticated


USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
REFRESH_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
ICON = "provider-codex.svg"
DISPLAY = "Codex"
PROVIDER_ID = "codex"
CREDIT_USD_RATE = 0.04


def _plan_label(plan_type) -> Optional[str]:
    raw = non_empty(plan_type)
    if raw is None:
        return None
    lowered = raw.lower()
    if lowered == "prolite":
        return "Pro 5x"
    if lowered == "pro":
        return "Pro 20x"
    return title_case_identifier(raw)


class CodexProvider:
    id = PROVIDER_ID
    display_name = DISPLAY

    def __init__(
        self,
        creds: Optional[CodexCredentials | list[CodexCredentials]] = None,
        getter: Callable[..., HttpResponse] = http_get,
        form_poster: Callable[..., HttpResponse] = http_post_form,
        auth_store: Optional[CodexAuthStore] = None,
        now: Optional[Callable[[], datetime]] = None,
        allow_keyring: bool = False,
    ):
        if creds is None:
            self._credentials: list[CodexCredentials] = []
        elif isinstance(creds, list):
            self._credentials = creds
        else:
            self._credentials = [creds]
        self._get = getter
        self._post_form = form_poster
        self._auth_store = auth_store or CodexAuthStore(now=now)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._allow_keyring = allow_keyring

    def is_configured(self) -> bool:
        return bool(self._credentials)

    def fetch(self) -> ProviderUsage:
        last_authentication_failure = None
        for credentials in self._credentials:
            usage = self._probe(credentials)
            if usage.status != ProviderStatus.UNAUTHENTICATED:
                return usage
            if credentials.is_api_key_only:
                return usage
            last_authentication_failure = usage

        if self._allow_keyring:
            keyring = self._auth_store.load_keyring()
            if keyring is not None:
                usage = self._probe(keyring)
                if usage.status != ProviderStatus.UNAUTHENTICATED:
                    return usage
                last_authentication_failure = usage

        return last_authentication_failure or unauthenticated(
            PROVIDER_ID,
            DISPLAY,
            ICON,
            "Not logged in. Run `codex` to authenticate.",
        )

    def _probe(self, credentials: CodexCredentials) -> ProviderUsage:
        if credentials.is_api_key_only:
            return unauthenticated(
                PROVIDER_ID,
                DISPLAY,
                ICON,
                "Usage not available for API key.",
            )
        access_token = non_empty(credentials.access_token)
        if access_token is None:
            return unauthenticated(
                PROVIDER_ID,
                DISPLAY,
                ICON,
                "Not logged in. Run `codex` to authenticate.",
            )

        state = credentials
        if self._auth_store.needs_refresh(state):
            live = self._auth_store.reload(state)
            if live is not None and live.has_access_token:
                state = live
                access_token = live.access_token
        if self._auth_store.needs_refresh(state) and state.refresh_token:
            state, failure = self._refresh(state)
            if failure is not None:
                return failure
            assert state is not None
            access_token = state.access_token

        response, failure = self._send_usage(access_token, state.account_id)
        if failure is not None:
            return failure
        assert response is not None

        if response.status in (401, 403):
            if not state.refresh_token:
                return unauthenticated(
                    PROVIDER_ID,
                    DISPLAY,
                    ICON,
                    "Token expired. Run `codex` to log in again.",
                )
            state, failure = self._refresh(state)
            if failure is not None:
                return failure
            assert state is not None
            response, failure = self._send_usage(state.access_token, state.account_id)
            if failure is not None:
                return failure
            assert response is not None
            if response.status in (401, 403):
                return unauthenticated(
                    PROVIDER_ID,
                    DISPLAY,
                    ICON,
                    "Token expired. Run `codex` to log in again.",
                )

        if response.status == 429:
            retry_at = retry_datetime(response.header("retry-after"), self._utc_now())
            return rate_limited(
                PROVIDER_ID,
                DISPLAY,
                ICON,
                "Codex is rate limited. Try again later.",
                retry_at,
            )
        if not 200 <= response.status < 300:
            return errored(
                PROVIDER_ID,
                DISPLAY,
                ICON,
                f"Codex usage request failed ({response.status}).",
                (
                    FailureKind.TRANSIENT
                    if response.status >= 500
                    else FailureKind.INVALID_RESPONSE
                ),
            )
        try:
            data = response.json()
        except (ValueError, UnicodeDecodeError):
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Codex returned unreadable usage data.",
                FailureKind.INVALID_RESPONSE,
            )
        if not isinstance(data, dict):
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Codex returned unreadable usage data.",
                FailureKind.INVALID_RESPONSE,
            )

        return self._map(response, data)

    def _refresh(
        self,
        credentials: CodexCredentials,
    ) -> tuple[Optional[CodexCredentials], Optional[ProviderUsage]]:
        refresh_token = non_empty(credentials.refresh_token)
        if refresh_token is None:
            return (
                None,
                unauthenticated(
                    PROVIDER_ID,
                    DISPLAY,
                    ICON,
                    "Token expired. Run `codex` to log in again.",
                ),
            )
        try:
            response = self._post_form(
                REFRESH_URL,
                [
                    ("grant_type", "refresh_token"),
                    ("client_id", CLIENT_ID),
                    ("refresh_token", refresh_token),
                ],
                {"Accept": "application/json"},
            )
        except Exception:
            return None, errored(PROVIDER_ID, DISPLAY, ICON, "Codex could not be reached.")

        if response.status in (400, 401):
            code = self._refresh_error_code(response)
            messages = {
                "refresh_token_expired": "Session expired. Run `codex` to log in again.",
                "refresh_token_reused": "Token conflict. Run `codex` to log in again.",
                "refresh_token_invalidated": "Token revoked. Run `codex` to log in again.",
            }
            if code in messages:
                return None, unauthenticated(PROVIDER_ID, DISPLAY, ICON, messages[code])
            return (
                None,
                errored(
                    PROVIDER_ID,
                    DISPLAY,
                    ICON,
                    f"Codex token refresh failed ({response.status}).",
                ),
            )
        if not 200 <= response.status < 300:
            return (
                None,
                errored(
                    PROVIDER_ID,
                    DISPLAY,
                    ICON,
                    f"Codex token refresh failed ({response.status}).",
                ),
            )
        try:
            body = response.json()
        except (ValueError, UnicodeDecodeError):
            body = None
        access_token = non_empty(body.get("access_token")) if isinstance(body, dict) else None
        if access_token is None:
            return (
                None,
                unauthenticated(
                    PROVIDER_ID,
                    DISPLAY,
                    ICON,
                    "Token expired. Run `codex` to log in again.",
                ),
            )
        updated = replace(
            credentials,
            access_token=access_token,
            refresh_token=(
                non_empty(body.get("refresh_token"))
                if isinstance(body, dict)
                else None
            ) or credentials.refresh_token,
            id_token=(
                non_empty(body.get("id_token"))
                if isinstance(body, dict)
                else None
            ) or credentials.id_token,
            last_refresh=self._utc_now().isoformat().replace("+00:00", "Z"),
        )
        if credentials.source is not None and not self._auth_store.save(updated):
            return (
                None,
                unauthenticated(
                    PROVIDER_ID,
                    DISPLAY,
                    ICON,
                    "Codex login changed during refresh. Refresh again.",
                ),
            )
        return updated, None

    @staticmethod
    def _refresh_error_code(response: HttpResponse) -> Optional[str]:
        try:
            body = response.json()
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(body, dict):
            return None
        error = body.get("error")
        if isinstance(error, dict):
            return (
                non_empty(error.get("code"))
                or non_empty(error.get("error"))
            )
        return non_empty(error) or non_empty(body.get("code"))

    def _send_usage(
        self,
        access_token: str,
        account_id: str,
    ) -> tuple[Optional[HttpResponse], Optional[ProviderUsage]]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "AIUsage/0.1",
        }
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id
        try:
            return self._get(USAGE_URL, headers=headers), None
        except Exception:
            return None, errored(PROVIDER_ID, DISPLAY, ICON, "Codex could not be reached.")

    def _map(self, response: HttpResponse, data: dict) -> ProviderUsage:
        windows = self._classify(
            data.get("rate_limit"),
            kinds=("session", "weekly"),
            captions=("Session · 5h", "Weekly · 7d"),
            header_percents=(
                number(response.header("x-codex-primary-used-percent")),
                number(response.header("x-codex-secondary-used-percent")),
            ),
        )

        additional = data.get("additional_rate_limits")
        if isinstance(additional, list):
            for entry in additional:
                if not isinstance(entry, dict) or not self._is_spark(entry):
                    continue
                windows.extend(self._classify(
                    entry.get("rate_limit"),
                    kinds=("spark", "spark_weekly"),
                    captions=("Spark", "Spark Weekly"),
                    header_percents=(None, None),
                ))
                break

        billing_usage = self._billing_usage(response, data)
        return ProviderUsage(
            provider_id=PROVIDER_ID,
            display_name=DISPLAY,
            icon=ICON,
            plan=_plan_label(data.get("plan_type")),
            status=ProviderStatus.OK,
            error_message=None,
            windows=windows,
            billing_usage=billing_usage,
            last_updated=self._utc_now(),
            retry_at=None,
        )

    def _classify(
        self,
        rate_limit,
        *,
        kinds: tuple[str, str],
        captions: tuple[str, str],
        header_percents: tuple[Optional[float], Optional[float]],
    ) -> list[UsageWindow]:
        root = rate_limit if isinstance(rate_limit, dict) else {}
        candidates = []
        for slot, header_percent, fallback_kind in (
            ("primary_window", header_percents[0], "session"),
            ("secondary_window", header_percents[1], "weekly"),
        ):
            value = root.get(slot)
            if isinstance(value, dict):
                obj = value
            elif header_percent is not None:
                obj = {}
            else:
                continue
            body_percent = number(obj.get("used_percent"))
            candidates.append((
                obj,
                body_percent if body_percent is not None else header_percent,
                fallback_kind,
            ))

        windows: list[UsageWindow] = []
        for wanted, output_kind, caption in (
            ("session", kinds[0], captions[0]),
            ("weekly", kinds[1], captions[1]),
        ):
            exact = next(
                (candidate for candidate in candidates if self._exact_kind(candidate[0]) == wanted),
                None,
            )
            fallback = next(
                (
                    candidate
                    for candidate in candidates
                    if self._exact_kind(candidate[0]) is None and candidate[2] == wanted
                ),
                None,
            )
            candidate = exact or fallback
            if candidate is None or candidate[1] is None:
                continue
            obj, used, _ = candidate
            windows.append(UsageWindow(
                caption=caption,
                kind=output_kind,
                used_percent=used,
                resets_at=self._reset_date(obj),
            ))
        return windows

    @staticmethod
    def _exact_kind(window: dict) -> Optional[str]:
        seconds = number(window.get("limit_window_seconds"))
        if seconds is None:
            return None
        rounded = round(seconds)
        if rounded == 18_000:
            return "session"
        if rounded == 604_800:
            return "weekly"
        return None

    def _reset_date(self, window: dict) -> Optional[datetime]:
        if number(window.get("reset_at")) is not None:
            return provider_datetime(window.get("reset_at"))
        reset_after = number(window.get("reset_after_seconds"))
        return self._utc_now() + timedelta(seconds=reset_after) if reset_after is not None else None

    @staticmethod
    def _is_spark(entry: dict) -> bool:
        return any(
            "spark" in value.lower()
            for key in ("limit_name", "metered_feature")
            if (value := non_empty(entry.get(key))) is not None
        )

    @staticmethod
    def _billing_usage(
        response: HttpResponse,
        data: dict,
    ) -> Optional[BillingUsage]:
        remaining = None
        credits = data.get("credits")
        if isinstance(credits, dict):
            remaining = number(credits.get("balance"))
            if remaining is None and credits.get("has_credits") is False:
                remaining = 0.0
        if remaining is None:
            remaining = number(response.header("x-codex-credits-balance"))
        if remaining is None:
            return None
        remaining_credits = max(math.floor(remaining), 0)
        return BillingUsage.flex_credit_balance(
            remaining_credits,
            remaining_credits * CREDIT_USD_RATE,
        )

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
