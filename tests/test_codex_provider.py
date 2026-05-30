import json

from conftest import fixture
from ai_usage_kde.core.http import HttpResponse
from ai_usage_kde.core.model import ProviderStatus
from ai_usage_kde.providers.codex import CodexProvider


def _getter(status=200):
    payload = fixture("codex_usage.json").read_text().encode()
    captured = {}

    def g(url, headers, timeout=15.0):
        captured["headers"] = headers
        return HttpResponse(status=status, body=payload, headers={})
    g.captured = captured
    return g


class _Creds:
    access_token = "cx-acc-1"
    account_id = "acct-1"


def test_codex_unconfigured_is_unauthenticated():
    u = CodexProvider(creds=None).fetch()
    assert u.status == ProviderStatus.UNAUTHENTICATED


def test_codex_fetch_maps_windows_plan_credits():
    u = CodexProvider(creds=_Creds(), getter=_getter()).fetch()
    kinds = {w.kind: w.used_percent for w in u.windows}
    assert kinds["session"] == 67
    assert kinds["weekly"] == 31
    assert kinds["code_review"] == 10
    assert u.plan == "Plus"
    assert u.credits.used == 12.5


def test_codex_sets_account_header():
    g = _getter()
    CodexProvider(creds=_Creds(), getter=g).fetch()
    assert g.captured["headers"]["Authorization"] == "Bearer cx-acc-1"
    assert g.captured["headers"]["ChatGPT-Account-Id"] == "acct-1"
