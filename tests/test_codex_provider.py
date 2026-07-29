import base64
import json
from datetime import datetime, timedelta, timezone

from conftest import fixture
from ai_usage_kde.core.auth import CodexAuthStore, SecretToolStore
from ai_usage_kde.core.environment import LoginShellEnvironment
from ai_usage_kde.core.http import HttpResponse
from ai_usage_kde.core.model import ProviderStatus
from ai_usage_kde.providers.codex import (
    CLIENT_ID,
    REFRESH_URL,
    USAGE_URL,
    CodexProvider,
)


NOW = datetime(2027, 1, 15, tzinfo=timezone.utc)


def _jwt(expiration):
    def segment(value):
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{segment({'alg': 'none'})}.{segment({'exp': expiration})}."


def _store():
    return CodexAuthStore(
        LoginShellEnvironment(environ={"PATH": "/usr/bin"}),
        secret_store=SecretToolStore(executable=""),
        now=lambda: NOW,
    )


def _credentials(path=None):
    store = _store()
    credentials = store.load_file(path or fixture("codex_auth.json"))
    credentials.last_refresh = None
    return credentials, store


def _response(status=200, body=None, headers=None):
    value = (
        json.loads(fixture("codex_usage.json").read_text())
        if body is None
        else body
    )
    return HttpResponse(
        status=status,
        body=json.dumps(value).encode(),
        headers={key.lower(): item for key, item in (headers or {}).items()},
    )


def test_codex_fetch_maps_windows_plan_and_flex_balance():
    credentials, store = _credentials()
    usage = CodexProvider(
        creds=credentials,
        auth_store=store,
        getter=lambda *args, **kwargs: _response(),
        now=lambda: NOW,
    ).fetch()

    assert usage.status == ProviderStatus.OK
    assert usage.plan == "Pro 20x"
    assert {window.kind: window.used_percent for window in usage.windows} == {
        "session": 67,
        "weekly": 31,
        "spark": 101.4,
        "spark_weekly": 22,
    }
    assert usage.billing_usage.kind == "flex_credit_balance"
    assert usage.billing_usage.remaining_credits == 820
    assert usage.billing_usage.usd_value == 32.8


def test_codex_sets_account_header():
    credentials, store = _credentials()
    captured = {}

    def getter(url, headers, timeout=15.0):
        captured["url"] = url
        captured["headers"] = headers
        return _response()

    CodexProvider(
        creds=credentials,
        auth_store=store,
        getter=getter,
        now=lambda: NOW,
    ).fetch()
    assert captured["url"] == USAGE_URL
    assert captured["headers"]["Authorization"] == "Bearer cx-acc-1"
    assert captured["headers"]["ChatGPT-Account-Id"] == "acct-uuid-1"


def test_codex_falls_back_to_percent_headers():
    credentials, store = _credentials()
    response = _response(
        body={
            "rate_limit": {
                "primary_window": {"limit_window_seconds": 18_000},
                "secondary_window": {"limit_window_seconds": 604_800},
            }
        },
        headers={
            "X-Codex-Primary-Used-Percent": "17.25",
            "x-codex-secondary-used-percent": "68",
        },
    )
    usage = CodexProvider(
        creds=credentials,
        auth_store=store,
        getter=lambda *args, **kwargs: response,
        now=lambda: NOW,
    ).fetch()
    assert [window.used_percent for window in usage.windows] == [17.25, 68]


def test_codex_proactive_refresh_uses_exact_source_and_persists(tmp_path):
    path = tmp_path / "auth.json"
    document = json.loads(fixture("codex_auth.json").read_text())
    document["tokens"]["access_token"] = _jwt(NOW.timestamp() + 60)
    document["tokens"]["refresh_token"] = "refresh +&"
    document["last_refresh"] = None
    path.write_text(json.dumps(document), encoding="utf-8")

    store = _store()
    credentials = store.load_file(path)
    refresh_calls = []
    request_headers = []

    def poster(url, data, headers, timeout=15.0):
        refresh_calls.append((url, data, headers))
        return _response(200, {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "id_token": "new-id",
        })

    def getter(url, headers, timeout=15.0):
        request_headers.append(headers)
        return _response()

    usage = CodexProvider(
        creds=credentials,
        auth_store=store,
        getter=getter,
        form_poster=poster,
        now=lambda: NOW,
    ).fetch()

    assert usage.status == ProviderStatus.OK
    assert refresh_calls[0][0] == REFRESH_URL
    assert ("client_id", CLIENT_ID) in refresh_calls[0][1]
    assert ("refresh_token", "refresh +&") in refresh_calls[0][1]
    assert request_headers[0]["ChatGPT-Account-Id"] == "acct-uuid-1"
    saved = json.loads(path.read_text())
    assert saved["tokens"]["access_token"] == "new-access"
    assert saved["tokens"]["refresh_token"] == "new-refresh"
    assert saved["tokens"]["id_token"] == "new-id"


def test_codex_api_key_only_never_calls_usage(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text('{"OPENAI_API_KEY":"sk-test"}', encoding="utf-8")
    store = _store()
    credentials = store.load_file(path)

    def forbidden(*args, **kwargs):
        raise AssertionError("usage endpoint must not be called")

    usage = CodexProvider(
        creds=credentials,
        auth_store=store,
        getter=forbidden,
        now=lambda: NOW,
    ).fetch()
    assert usage.status == ProviderStatus.UNAUTHENTICATED
    assert usage.error_message == "Usage not available for API key."


def test_codex_known_refresh_failure_is_authentication_error():
    credentials, store = _credentials()
    credentials.access_token = _jwt(NOW.timestamp() + 60)
    usage = CodexProvider(
        creds=credentials,
        auth_store=store,
        form_poster=lambda *args, **kwargs: _response(
            400,
            {"error": {"code": "refresh_token_reused"}},
        ),
        now=lambda: NOW,
    ).fetch()
    assert usage.status == ProviderStatus.UNAUTHENTICATED
    assert "Token conflict" in usage.error_message


def test_codex_429_reports_retry_without_persisting_backend_cooldown():
    credentials, store = _credentials()
    calls = 0

    def getter(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _response(429, {}, {"Retry-After": "60"})

    provider = CodexProvider(
        creds=credentials,
        auth_store=store,
        getter=getter,
        now=lambda: NOW,
    )
    first = provider.fetch()
    second = provider.fetch()
    assert first.status == ProviderStatus.RATE_LIMITED
    assert first.retry_at == NOW + timedelta(seconds=60)
    assert second.status == ProviderStatus.RATE_LIMITED
    assert calls == 2


def test_codex_unconfigured_is_unauthenticated():
    usage = CodexProvider(
        creds=None,
    ).fetch()
    assert usage.status == ProviderStatus.UNAUTHENTICATED
