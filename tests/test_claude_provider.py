import json

from conftest import fixture
from ai_usage_kde.core.http import HttpResponse
from ai_usage_kde.core.model import ProviderStatus
from ai_usage_kde.providers.claude import ClaudeProvider


def _fake_getter(status=200, body=None):
    payload = json.dumps(body if body is not None
                         else json.loads(fixture("claude_usage.json").read_text())).encode()
    captured = {}

    def getter(url, headers, timeout=15.0):
        captured["url"] = url
        captured["headers"] = headers
        return HttpResponse(status=status, body=payload, headers={})
    getter.captured = captured
    return getter


def test_claude_fetch_maps_windows_and_credits():
    p = ClaudeProvider(creds=_DummyCreds(), getter=_fake_getter())
    usage = p.fetch()
    assert usage.status == ProviderStatus.OK
    kinds = {w.kind: w.used_percent for w in usage.windows}
    assert kinds["session"] == 42
    assert kinds["weekly"] == 18
    assert kinds["weekly_opus"] == 55
    assert usage.credits.used == 3.2 and usage.credits.cap == 50


def test_claude_fetch_sets_required_headers():
    getter = _fake_getter()
    ClaudeProvider(creds=_DummyCreds(), getter=getter).fetch()
    h = getter.captured["headers"]
    assert h["Authorization"] == "Bearer acc-123"
    assert h["anthropic-beta"] == "oauth-2025-04-20"
    assert h["User-Agent"].startswith("claude-code/")


def test_claude_fetch_401_is_error_status():
    p = ClaudeProvider(creds=_DummyCreds(), getter=_fake_getter(status=401))
    usage = p.fetch()
    assert usage.status in (ProviderStatus.ERROR, ProviderStatus.UNAUTHENTICATED)


class _DummyCreds:
    access_token = "acc-123"
    refresh_token = "ref"
    subscription_type = "max"
    rate_limit_tier = "default_max_20x"
    def is_expired(self, now_ms=None):
        return False
