import time

from conftest import fixture
from ai_usage_kde.core.auth import (
    ClaudeCredentials, CodexCredentials, load_claude_credentials, load_codex_credentials,
)


def test_load_claude_credentials_reads_fields():
    c = load_claude_credentials(path=fixture("claude_credentials.json"))
    assert isinstance(c, ClaudeCredentials)
    assert c.access_token == "acc-123"
    assert c.refresh_token == "ref-456"
    assert c.subscription_type == "max"
    assert c.is_expired(now_ms=0) is False  # expiresAt is far future


def test_claude_credentials_expiry_detection():
    c = ClaudeCredentials(access_token="a", refresh_token="r", expires_at_ms=1000,
                          subscription_type="max", rate_limit_tier="x")
    # expired if now >= expires - 5 min skew
    assert c.is_expired(now_ms=1000) is True
    assert c.is_expired(now_ms=0) is True          # within 5-min skew of 1000ms
    assert c.is_expired(now_ms=-10_000_000) is False


def test_load_claude_credentials_missing_returns_none(tmp_path):
    assert load_claude_credentials(path=tmp_path / "nope.json") is None


def test_load_codex_credentials_reads_nested_tokens():
    c = load_codex_credentials(path=fixture("codex_auth.json"))
    assert isinstance(c, CodexCredentials)
    assert c.access_token == "cx-acc-1"
    assert c.account_id == "acct-uuid-1"


def test_load_codex_credentials_missing_returns_none(tmp_path):
    assert load_codex_credentials(path=tmp_path / "nope.json") is None
