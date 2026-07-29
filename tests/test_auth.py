import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from conftest import fixture
from ai_usage_kde.core.auth import (
    CODEX_KEYRING_SERVICE,
    ClaudeAuthStore,
    ClaudeCredentials,
    CodexAuthStore,
    CodexCredentials,
    SecretToolCredentialSource,
    SecretToolStore,
    load_claude_credentials,
    load_codex_credentials,
)
from ai_usage_kde.core.environment import LoginShellEnvironment


def _environment(values=None):
    return LoginShellEnvironment(
        environ={"PATH": "/usr/bin", **(values or {})},
    )


def _jwt(expiration: float) -> str:
    def segment(value):
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{segment({'alg': 'none'})}.{segment({'exp': expiration})}."


def test_load_claude_credentials_reads_fields_and_scope():
    credentials = load_claude_credentials(path=fixture("claude_credentials.json"))
    assert isinstance(credentials, ClaudeCredentials)
    assert credentials.access_token == "acc-123"
    assert credentials.refresh_token == "ref-456"
    assert credentials.subscription_type == "max"
    assert credentials.scopes == ("user:profile", "user:inference")
    assert credentials.is_expired(now_ms=0) is False


def test_claude_uses_config_dir_and_ignores_setup_token(tmp_path):
    config_dir = tmp_path / "claude-profile"
    config_dir.mkdir()
    (config_dir / ".credentials.json").write_text(
        fixture("claude_credentials.json").read_text(),
        encoding="utf-8",
    )
    environment = _environment({
        "CLAUDE_CONFIG_DIR": str(config_dir),
        "CLAUDE_CODE_OAUTH_TOKEN": "setup-token-must-not-win",
    })
    credentials = ClaudeAuthStore(environment).load()
    assert credentials.access_token == "acc-123"
    assert credentials.source.path == config_dir / ".credentials.json"

    (config_dir / ".credentials.json").unlink()
    assert ClaudeAuthStore(environment).load() is None


def test_claude_scope_rules_allow_unknown_and_reject_known_missing_profile():
    store = ClaudeAuthStore(_environment())
    base = dict(
        access_token="a",
        refresh_token="r",
        expires_at_ms=None,
        subscription_type="max",
        rate_limit_tier="tier",
    )
    assert store.has_usage_scope(ClaudeCredentials(**base, scopes=None))
    assert store.has_usage_scope(ClaudeCredentials(**base, scopes=()))
    assert not store.has_usage_scope(ClaudeCredentials(**base, scopes=("user:inference",)))
    assert store.has_usage_scope(ClaudeCredentials(**base, scopes=("user:profile",)))


def test_claude_credentials_expiry_detection():
    credentials = ClaudeCredentials(
        access_token="a",
        refresh_token="r",
        expires_at_ms=1_000,
        subscription_type="max",
        rate_limit_tier="x",
    )
    assert credentials.is_expired(now_ms=1_000)
    assert credentials.is_expired(now_ms=0)
    assert not credentials.is_expired(now_ms=-10_000_000)


def test_claude_save_is_private_and_compare_before_write(tmp_path):
    path = tmp_path / ".credentials.json"
    path.write_text(fixture("claude_credentials.json").read_text(), encoding="utf-8")
    store = ClaudeAuthStore(_environment())
    credentials = store.load(path)
    credentials.access_token = "rotated"
    assert store.save(credentials)
    assert json.loads(path.read_text())["claudeAiOauth"]["accessToken"] == "rotated"
    assert os.stat(path).st_mode & 0o777 == 0o600

    stale = store.load(path)
    path.write_text('{"claudeAiOauth":{"accessToken":"cli-won"}}', encoding="utf-8")
    stale.access_token = "must-not-overwrite"
    assert not store.save(stale)
    assert json.loads(path.read_text())["claudeAiOauth"]["accessToken"] == "cli-won"


def test_codex_home_overrides_default_paths(tmp_path):
    environment = _environment({"CODEX_HOME": str(tmp_path / "custom-codex")})
    store = CodexAuthStore(
        environment,
        secret_store=SecretToolStore(executable=""),
    )
    assert store.auth_paths() == [tmp_path / "custom-codex" / "auth.json"]


def test_load_codex_credentials_reads_nested_tokens():
    credentials = load_codex_credentials(path=fixture("codex_auth.json"))
    assert isinstance(credentials, CodexCredentials)
    assert credentials.access_token == "cx-acc-1"
    assert credentials.account_id == "acct-uuid-1"
    assert credentials.last_refresh == "2026-05-30T10:00:00Z"


def test_codex_api_key_only_document_is_detected(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text('{"OPENAI_API_KEY":"sk-test"}', encoding="utf-8")
    credentials = load_codex_credentials(path=path)
    assert credentials.is_api_key_only
    assert not credentials.has_access_token


def test_codex_jwt_expiration_wins_over_old_last_refresh(tmp_path):
    now = datetime(2027, 1, 15, tzinfo=timezone.utc)
    store = CodexAuthStore(
        _environment({"CODEX_HOME": str(tmp_path)}),
        secret_store=SecretToolStore(executable=""),
        now=lambda: now,
    )
    future = CodexCredentials(
        access_token=_jwt(now.timestamp() + 3_600),
        refresh_token="r",
        id_token="",
        account_id="a",
        last_refresh="2020-01-01T00:00:00Z",
    )
    expiring = CodexCredentials(
        access_token=_jwt(now.timestamp() + 60),
        refresh_token="r",
        id_token="",
        account_id="a",
    )
    assert not store.needs_refresh(future)
    assert store.needs_refresh(expiring)


def test_secret_tool_uses_codex_service_account_and_stdin(tmp_path):
    document = fixture("codex_auth.json").read_text()
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "lookup":
            return SimpleNamespace(returncode=0, stdout=document, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    secret_store = SecretToolStore(
        executable="/usr/bin/secret-tool",
        runner=runner,
    )
    environment = _environment({"CODEX_HOME": str(tmp_path)})
    store = CodexAuthStore(environment, secret_store=secret_store)
    credentials = store.load_keyring()
    assert isinstance(credentials.source, SecretToolCredentialSource)
    assert credentials.source.service == CODEX_KEYRING_SERVICE
    assert credentials.source.username.startswith("cli|")
    assert len(credentials.source.username) == len("cli|") + 16

    credentials.access_token = "rotated-keyring-token"
    assert store.save(credentials)
    store_call = next(item for item in calls if item[0][1] == "store")
    assert "rotated-keyring-token" not in store_call[0]
    assert "rotated-keyring-token" in store_call[1]["input"]


def test_secret_tool_supports_service_only_without_secret_in_argv():
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "lookup":
            return SimpleNamespace(returncode=0, stdout="secret-value\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    store = SecretToolStore(
        executable="/usr/bin/secret-tool",
        runner=runner,
    )
    assert store.lookup("cursor-access-token") == "secret-value"
    assert store.store(
        "cursor-access-token",
        None,
        "rotated-secret",
        label="Cursor access token",
    )
    command, arguments = calls[-1]
    assert "rotated-secret" not in command
    assert arguments["input"] == "rotated-secret"
    assert "username" not in command


def test_missing_credentials_return_none(tmp_path):
    assert load_claude_credentials(path=tmp_path / "missing") is None
    assert load_codex_credentials(path=tmp_path / "missing") is None
