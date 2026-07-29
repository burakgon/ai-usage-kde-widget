from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .environment import LoginShellEnvironment
from .http import HttpResponse, http_post_json
from .parsing import (
    decode_json_with_hex_fallback,
    jwt_expiration,
    non_empty,
    provider_datetime,
)
from .storage import atomic_write_private


_FIVE_MIN_MS = 5 * 60 * 1000
_CODEX_REFRESH_WINDOW = timedelta(minutes=5)
_CODEX_LAST_REFRESH_MAX_AGE = timedelta(days=8)

CLAUDE_REFRESH_URL = "https://platform.claude.com/v1/oauth/token"
CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_REQUIRED_USAGE_SCOPE = "user:profile"
CLAUDE_REFRESH_SCOPES = (
    "user:profile user:inference user:sessions:claude_code "
    "user:mcp_servers user:file_upload"
)

CODEX_KEYRING_SERVICE = "Codex Auth"


@dataclass(frozen=True)
class FileCredentialSource:
    path: Path


@dataclass(frozen=True)
class SecretToolCredentialSource:
    service: str
    username: str


CredentialSource = FileCredentialSource | SecretToolCredentialSource


@dataclass
class ClaudeCredentials:
    access_token: str
    refresh_token: str
    expires_at_ms: Optional[float]
    subscription_type: str
    rate_limit_tier: str
    scopes: Optional[tuple[str, ...]] = None
    source: Optional[FileCredentialSource] = field(default=None, repr=False, compare=False)
    document: Optional[dict[str, Any]] = field(default=None, repr=False, compare=False)
    raw_text: Optional[str] = field(default=None, repr=False, compare=False)

    def is_expired(self, now_ms: Optional[int] = None) -> bool:
        if self.expires_at_ms is None:
            return False
        now = int(time.time() * 1000) if now_ms is None else now_ms
        return now >= (self.expires_at_ms - _FIVE_MIN_MS)


@dataclass
class CodexCredentials:
    access_token: str
    refresh_token: str
    id_token: str
    account_id: str
    last_refresh: Optional[str] = None
    api_key: str = ""
    source: Optional[CredentialSource] = field(default=None, repr=False, compare=False)
    document: Optional[dict[str, Any]] = field(default=None, repr=False, compare=False)
    raw_text: Optional[str] = field(default=None, repr=False, compare=False)

    @property
    def has_access_token(self) -> bool:
        return non_empty(self.access_token) is not None

    @property
    def is_api_key_only(self) -> bool:
        return not self.has_access_token and non_empty(self.api_key) is not None


class SecretToolStore:
    """Small Secret Service adapter that never places secrets in argv."""

    def __init__(
        self,
        executable: Optional[str] = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        timeout: float = 5.0,
    ):
        self.executable = executable if executable is not None else shutil.which("secret-tool")
        self._runner = runner
        self._timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.executable)

    def lookup(self, service: str, username: Optional[str] = None) -> Optional[str]:
        if not self.executable:
            return None
        attributes = ["service", service]
        if username:
            attributes.extend(["username", username])
        try:
            result = self._runner(
                [self.executable, "lookup", *attributes],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def store(
        self,
        service: str,
        username: Optional[str],
        value: str,
        *,
        label: Optional[str] = None,
    ) -> bool:
        if not self.executable:
            return False
        attributes = ["service", service]
        if username:
            attributes.extend(["username", username])
        try:
            result = self._runner(
                [
                    self.executable,
                    "store",
                    f"--label={label or service}",
                    *attributes,
                ],
                input=value,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0


class ClaudeAuthStore:
    def __init__(self, environment: Optional[LoginShellEnvironment] = None):
        self.environment = environment or LoginShellEnvironment()

    def credentials_path(self) -> Path:
        config_dir = self.environment.value("CLAUDE_CONFIG_DIR")
        root = Path(config_dir).expanduser() if config_dir else Path.home() / ".claude"
        return root / ".credentials.json"

    def load(self, path: Optional[Path] = None) -> Optional[ClaudeCredentials]:
        source_path = path or self.credentials_path()
        try:
            raw = source_path.read_text(encoding="utf-8")
        except OSError:
            return None
        document = decode_json_with_hex_fallback(raw)
        oauth = document.get("claudeAiOauth") if document else None
        if not isinstance(oauth, dict):
            return None
        access_token = non_empty(oauth.get("accessToken"))
        if access_token is None:
            return None
        scopes_value = oauth.get("scopes")
        scopes: Optional[tuple[str, ...]]
        if isinstance(scopes_value, list):
            scopes = tuple(item for item in scopes_value if isinstance(item, str))
        else:
            scopes = None
        expires = oauth.get("expiresAt")
        try:
            expires_at = float(expires) if expires is not None else None
        except (TypeError, ValueError):
            expires_at = None
        return ClaudeCredentials(
            access_token=access_token,
            refresh_token=non_empty(oauth.get("refreshToken")) or "",
            expires_at_ms=expires_at,
            subscription_type=non_empty(oauth.get("subscriptionType")) or "",
            rate_limit_tier=non_empty(oauth.get("rateLimitTier")) or "",
            scopes=scopes,
            source=FileCredentialSource(source_path),
            document=document,
            raw_text=raw,
        )

    @staticmethod
    def has_usage_scope(credentials: ClaudeCredentials) -> bool:
        if not credentials.scopes:
            return True
        return CLAUDE_REQUIRED_USAGE_SCOPE in credentials.scopes

    def reload(self, credentials: ClaudeCredentials) -> Optional[ClaudeCredentials]:
        if credentials.source is None:
            return credentials
        return self.load(credentials.source.path)

    def save(self, credentials: ClaudeCredentials) -> bool:
        if (
            credentials.source is None
            or credentials.document is None
            or credentials.raw_text is None
        ):
            return False
        document = copy.deepcopy(credentials.document)
        oauth = document.setdefault("claudeAiOauth", {})
        if not isinstance(oauth, dict):
            return False
        oauth["accessToken"] = credentials.access_token
        oauth["refreshToken"] = credentials.refresh_token
        if credentials.expires_at_ms is not None:
            oauth["expiresAt"] = credentials.expires_at_ms
        serialized = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        saved = atomic_write_private(
            credentials.source.path,
            serialized,
            expected_text=credentials.raw_text,
        )
        if saved:
            credentials.document = document
            credentials.raw_text = serialized
        return saved


class CodexAuthStore:
    def __init__(
        self,
        environment: Optional[LoginShellEnvironment] = None,
        secret_store: Optional[SecretToolStore] = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.environment = environment or LoginShellEnvironment()
        self.secret_store = secret_store or SecretToolStore()
        self._now = now or (lambda: datetime.now(timezone.utc))

    def auth_paths(self) -> list[Path]:
        if codex_home := self.environment.value("CODEX_HOME"):
            return [Path(codex_home).expanduser() / "auth.json"]
        return [
            Path.home() / ".config" / "codex" / "auth.json",
            Path.home() / ".codex" / "auth.json",
        ]

    def load_file_candidates(self) -> list[CodexCredentials]:
        return [
            credentials
            for path in self.auth_paths()
            if (credentials := self.load_file(path)) is not None
        ]

    def load_file(self, path: Path) -> Optional[CodexCredentials]:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return None
        return self._credentials(
            raw,
            source=FileCredentialSource(path),
        )

    def load_keyring(self) -> Optional[CodexCredentials]:
        username = self.keyring_username()
        raw = self.secret_store.lookup(CODEX_KEYRING_SERVICE, username)
        if raw is None:
            return None
        return self._credentials(
            raw,
            source=SecretToolCredentialSource(CODEX_KEYRING_SERVICE, username),
        )

    def reload(self, credentials: CodexCredentials) -> Optional[CodexCredentials]:
        source = credentials.source
        if isinstance(source, FileCredentialSource):
            return self.load_file(source.path)
        if isinstance(source, SecretToolCredentialSource):
            raw = self.secret_store.lookup(source.service, source.username)
            return self._credentials(raw, source=source) if raw is not None else None
        return credentials

    def save(self, credentials: CodexCredentials) -> bool:
        if credentials.document is None or credentials.raw_text is None:
            return False
        document = copy.deepcopy(credentials.document)
        tokens = document.setdefault("tokens", {})
        if not isinstance(tokens, dict):
            return False
        tokens["access_token"] = credentials.access_token
        tokens["refresh_token"] = credentials.refresh_token
        tokens["id_token"] = credentials.id_token
        tokens["account_id"] = credentials.account_id
        if credentials.last_refresh is not None:
            document["last_refresh"] = credentials.last_refresh
        serialized = json.dumps(
            document,
            ensure_ascii=False,
            indent=2 if isinstance(credentials.source, FileCredentialSource) else None,
            sort_keys=isinstance(credentials.source, FileCredentialSource),
            separators=None if isinstance(credentials.source, FileCredentialSource) else (",", ":"),
        )

        source = credentials.source
        if isinstance(source, FileCredentialSource):
            saved = atomic_write_private(
                source.path,
                serialized,
                expected_text=credentials.raw_text,
            )
        elif isinstance(source, SecretToolCredentialSource):
            current = self.secret_store.lookup(source.service, source.username)
            saved = current == credentials.raw_text and self.secret_store.store(
                source.service,
                source.username,
                serialized,
            )
        else:
            return False
        if saved:
            credentials.document = document
            credentials.raw_text = serialized
        return saved

    def needs_refresh(self, credentials: CodexCredentials) -> bool:
        if expiration := jwt_expiration(credentials.access_token):
            return expiration - self._now() <= _CODEX_REFRESH_WINDOW
        refreshed_at = provider_datetime(credentials.last_refresh)
        if refreshed_at is None:
            return False
        return self._now() - refreshed_at > _CODEX_LAST_REFRESH_MAX_AGE

    def keyring_username(self) -> str:
        configured = self.environment.value("CODEX_HOME")
        codex_home = Path(configured).expanduser() if configured else Path.home() / ".codex"
        try:
            normalized = codex_home.resolve(strict=True)
        except OSError:
            normalized = codex_home
        digest = hashlib.sha256(str(normalized).encode("utf-8")).hexdigest()[:16]
        return f"cli|{digest}"

    @staticmethod
    def _credentials(
        raw: str,
        *,
        source: CredentialSource,
    ) -> Optional[CodexCredentials]:
        document = decode_json_with_hex_fallback(raw)
        if document is None:
            return None
        tokens = document.get("tokens")
        tokens = tokens if isinstance(tokens, dict) else {}
        access_token = non_empty(tokens.get("access_token")) or ""
        api_key = non_empty(document.get("OPENAI_API_KEY")) or ""
        if not access_token and not api_key:
            return None
        return CodexCredentials(
            access_token=access_token,
            refresh_token=non_empty(tokens.get("refresh_token")) or "",
            id_token=non_empty(tokens.get("id_token")) or "",
            account_id=non_empty(tokens.get("account_id")) or "",
            last_refresh=non_empty(document.get("last_refresh")),
            api_key=api_key,
            source=source,
            document=document,
            raw_text=raw.strip() if isinstance(source, SecretToolCredentialSource) else raw,
        )


def claude_credentials_path(
    environment: Optional[LoginShellEnvironment] = None,
) -> Path:
    return ClaudeAuthStore(environment).credentials_path()


def load_claude_credentials(
    path: Optional[Path] = None,
    environment: Optional[LoginShellEnvironment] = None,
) -> Optional[ClaudeCredentials]:
    return ClaudeAuthStore(environment).load(path)


def codex_auth_candidates(
    environment: Optional[LoginShellEnvironment] = None,
) -> list[Path]:
    return CodexAuthStore(environment, secret_store=SecretToolStore(executable="")).auth_paths()


def load_codex_credentials(
    path: Optional[Path] = None,
    environment: Optional[LoginShellEnvironment] = None,
    secret_store: Optional[SecretToolStore] = None,
) -> Optional[CodexCredentials]:
    store = CodexAuthStore(environment, secret_store=secret_store)
    if path is not None:
        return store.load_file(path)
    candidates = store.load_file_candidates()
    return candidates[0] if candidates else store.load_keyring()


def refresh_claude_token(
    creds: ClaudeCredentials,
    poster: Callable[..., HttpResponse] = http_post_json,
) -> Optional[str]:
    """Compatibility helper: refresh in memory and return the new access token."""
    if not creds.refresh_token:
        return None
    resp = poster(
        CLAUDE_REFRESH_URL,
        {
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "client_id": CLAUDE_CLIENT_ID,
            "scope": CLAUDE_REFRESH_SCOPES,
        },
        {"Accept": "application/json"},
    )
    if not 200 <= resp.status < 300:
        return None
    try:
        return non_empty(resp.json().get("access_token"))
    except (ValueError, AttributeError):
        return None
