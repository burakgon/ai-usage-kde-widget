import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from conftest import fixture
from ai_usage_kde.core.auth import (
    CLAUDE_REFRESH_SCOPES,
    CLAUDE_REFRESH_URL,
    ClaudeAuthStore,
)
from ai_usage_kde.core.environment import LoginShellEnvironment
from ai_usage_kde.core.http import HttpResponse
from ai_usage_kde.core.model import ProviderStatus
from ai_usage_kde.providers.claude import ClaudeProvider, USAGE_URL


NOW = datetime(2027, 1, 15, tzinfo=timezone.utc)


def _credentials(path=None):
    store = ClaudeAuthStore(LoginShellEnvironment(environ={"PATH": "/usr/bin"}))
    return store.load(path or fixture("claude_credentials.json")), store


def _response(status=200, body=None, headers=None):
    value = (
        json.loads(fixture("claude_usage.json").read_text())
        if body is None
        else body
    )
    return HttpResponse(
        status=status,
        body=json.dumps(value).encode(),
        headers={key.lower(): item for key, item in (headers or {}).items()},
    )


def test_claude_fetch_maps_current_windows_plan_and_billing():
    credentials, store = _credentials()
    provider = ClaudeProvider(
        creds=credentials,
        auth_store=store,
        getter=lambda *args, **kwargs: _response(),
        now=lambda: NOW,
    )

    usage = provider.fetch()

    assert usage.status == ProviderStatus.OK
    assert usage.plan == "Max 20x"
    assert {window.kind: window.used_percent for window in usage.windows} == {
        "session": 42,
        "weekly": 18,
        "sonnet": 55,
        "fable": 73,
    }
    assert usage.billing_usage.kind == "bounded_spend"
    assert usage.billing_usage.used_amount == 5
    assert usage.billing_usage.limit_amount == 10


def test_claude_fetch_sets_required_headers():
    credentials, store = _credentials()
    captured = {}

    def getter(url, headers, timeout=15.0):
        captured["url"] = url
        captured["headers"] = headers
        return _response()

    ClaudeProvider(
        creds=credentials,
        auth_store=store,
        getter=getter,
        now=lambda: NOW,
    ).fetch()

    assert captured["url"] == USAGE_URL
    assert captured["headers"]["Authorization"] == "Bearer acc-123"
    assert captured["headers"]["anthropic-beta"] == "oauth-2025-04-20"
    assert captured["headers"]["User-Agent"] == "claude-code/2.1.69"


def test_claude_rejects_known_missing_profile_scope_without_network():
    credentials, store = _credentials()
    credentials = replace(credentials, scopes=("user:inference",))

    def forbidden(*args, **kwargs):
        raise AssertionError("usage endpoint must not be called")

    usage = ClaudeProvider(
        creds=credentials,
        auth_store=store,
        getter=forbidden,
        now=lambda: NOW,
    ).fetch()
    assert usage.status == ProviderStatus.UNAUTHENTICATED
    assert "Re-login" in usage.error_message


def test_claude_retries_401_and_persists_rotated_credentials(tmp_path):
    path = tmp_path / ".credentials.json"
    path.write_text(fixture("claude_credentials.json").read_text(), encoding="utf-8")
    credentials, store = _credentials(path)
    usage_responses = [_response(401, {}), _response()]
    usage_urls = []
    refresh_calls = []

    def getter(url, headers, timeout=15.0):
        usage_urls.append(url)
        return usage_responses.pop(0)

    def poster(url, data, headers, timeout=15.0):
        refresh_calls.append((url, data, headers))
        return _response(200, {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        })

    usage = ClaudeProvider(
        creds=credentials,
        auth_store=store,
        getter=getter,
        json_poster=poster,
        now=lambda: NOW,
    ).fetch()

    assert usage.status == ProviderStatus.OK
    assert usage_urls == [USAGE_URL, USAGE_URL]
    assert refresh_calls[0][0] == CLAUDE_REFRESH_URL
    assert refresh_calls[0][1]["scope"] == CLAUDE_REFRESH_SCOPES
    saved = json.loads(path.read_text())
    assert saved["claudeAiOauth"]["accessToken"] == "new-access"
    assert saved["claudeAiOauth"]["refreshToken"] == "new-refresh"


def test_claude_429_reports_retry_without_persisting_backend_cooldown():
    credentials, store = _credentials()
    calls = 0

    def getter(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _response(429, {}, {"Retry-After": "120"})

    provider = ClaudeProvider(
        creds=credentials,
        auth_store=store,
        getter=getter,
        now=lambda: NOW,
    )
    first = provider.fetch()
    second = provider.fetch()

    assert first.status == ProviderStatus.RATE_LIMITED
    assert first.retry_at == NOW + timedelta(seconds=120)
    assert second.status == ProviderStatus.RATE_LIMITED
    assert calls == 2


def test_claude_invalid_grant_is_authentication_failure():
    credentials, store = _credentials()
    credentials = replace(credentials, expires_at_ms=0)
    usage = ClaudeProvider(
        creds=credentials,
        auth_store=store,
        json_poster=lambda *args, **kwargs: _response(
            400,
            {"error": "invalid_grant"},
        ),
        now=lambda: NOW,
    ).fetch()
    assert usage.status == ProviderStatus.UNAUTHENTICATED
    assert "Session expired" in usage.error_message


def test_claude_unconfigured_is_unauthenticated():
    usage = ClaudeProvider(
        creds=None,
    ).fetch()
    assert usage.status == ProviderStatus.UNAUTHENTICATED
