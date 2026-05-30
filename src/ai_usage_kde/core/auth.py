from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .http import http_post_form, HttpResponse

_FIVE_MIN_MS = 5 * 60 * 1000


@dataclass
class ClaudeCredentials:
    access_token: str
    refresh_token: str
    expires_at_ms: int
    subscription_type: str
    rate_limit_tier: str

    def is_expired(self, now_ms: Optional[int] = None) -> bool:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        return now >= (self.expires_at_ms - _FIVE_MIN_MS)


@dataclass
class CodexCredentials:
    access_token: str
    refresh_token: str
    id_token: str
    account_id: str


def claude_credentials_path() -> Path:
    return Path.home() / ".claude" / ".credentials.json"


def load_claude_credentials(path: Optional[Path] = None) -> Optional[ClaudeCredentials]:
    # env override first (matches Claude Code behavior)
    env_tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    p = path or claude_credentials_path()
    if env_tok and not path:
        return ClaudeCredentials(access_token=env_tok, refresh_token="",
                                 expires_at_ms=2**62, subscription_type="", rate_limit_tier="")
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        o = data.get("claudeAiOauth") or {}
        if not o.get("accessToken"):
            return None
        return ClaudeCredentials(
            access_token=o["accessToken"],
            refresh_token=o.get("refreshToken", ""),
            expires_at_ms=int(o.get("expiresAt", 0)),
            subscription_type=o.get("subscriptionType", ""),
            rate_limit_tier=o.get("rateLimitTier", ""),
        )
    except (OSError, ValueError, KeyError):
        return None


def codex_auth_candidates() -> list[Path]:
    paths = []
    home = Path.home()
    if os.environ.get("CODEX_HOME"):
        paths.append(Path(os.environ["CODEX_HOME"]) / "auth.json")
    paths.append(home / ".config" / "codex" / "auth.json")
    paths.append(home / ".codex" / "auth.json")
    return paths


def load_codex_credentials(path: Optional[Path] = None) -> Optional[CodexCredentials]:
    candidates = [path] if path else codex_auth_candidates()
    for p in candidates:
        if p and p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                t = data.get("tokens") or {}
                if not t.get("access_token"):
                    continue
                return CodexCredentials(
                    access_token=t["access_token"],
                    refresh_token=t.get("refresh_token", ""),
                    id_token=t.get("id_token", ""),
                    account_id=t.get("account_id", ""),
                )
            except (OSError, ValueError, KeyError):
                continue
    return None


CLAUDE_REFRESH_URL = "https://console.anthropic.com/v1/oauth/token"
CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # public Claude Code OAuth client id


def refresh_claude_token(creds: ClaudeCredentials,
                         poster: Callable[..., HttpResponse] = http_post_form) -> Optional[str]:
    """Returns a new access token or None on failure. Persisting is the caller's job."""
    if not creds.refresh_token:
        return None
    resp = poster(CLAUDE_REFRESH_URL, {
        "grant_type": "refresh_token",
        "refresh_token": creds.refresh_token,
        "client_id": CLAUDE_CLIENT_ID,
    }, {"Accept": "application/json"})
    if resp.status != 200:
        return None
    try:
        return resp.json().get("access_token")
    except ValueError:
        return None
