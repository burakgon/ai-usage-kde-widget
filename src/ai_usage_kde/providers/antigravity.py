from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from ..core.auth import SecretToolStore
from ..core.environment import LoginShellEnvironment
from ..core.http import HttpResponse, http_post_form, http_post_json
from ..core.model import FailureKind, ProviderStatus, ProviderUsage, UsageWindow
from ..core.parsing import non_empty, number, provider_datetime, title_case_identifier
from ..core.storage import atomic_write_private
from .base import errored, unauthenticated


PROVIDER_ID = "antigravity"
DISPLAY = "Antigravity"
ICON = "provider-antigravity.svg"
SECRET_SERVICE = "gemini"
SECRET_USERNAME = "antigravity"
CLOUD_BASES = (
    "https://daily-cloudcode-pa.googleapis.com",
    "https://cloudcode-pa.googleapis.com",
)
SUMMARY_PATH = "/v1internal:retrieveUserQuotaSummary"
MODELS_PATH = "/v1internal:fetchAvailableModels"
PLAN_PATH = "/v1internal:loadCodeAssist"
REFRESH_URL = "https://oauth2.googleapis.com/token"
_OAUTH_MODULE_MARKER = "platform/cloudCode/common/oauthClient.js"
_OAUTH_PAIR = re.compile(
    r"""["'](?P<client_id>\d+-[A-Za-z0-9_-]+"""
    r"""\.apps\.googleusercontent\.com)["']\s*,\s*"""
    r"""[A-Za-z_$][A-Za-z0-9_$]*\s*=\s*"""
    r"""["'](?P<client_secret>[A-Za-z0-9._~-]{16,})["']"""
)


@dataclass
class AntigravityCredentials:
    access_token: Optional[str]
    refresh_token: Optional[str]
    expires_at: Optional[datetime]


@dataclass(frozen=True)
class AntigravityOAuthClient:
    client_id: str
    client_secret: str


class AntigravityOAuthClientStore:
    """Resolve the installed IDE's public OAuth client metadata at runtime."""

    def __init__(
        self,
        environment: Optional[LoginShellEnvironment] = None,
        paths: Optional[tuple[Path, ...]] = None,
    ):
        self.environment = environment or LoginShellEnvironment()
        self.paths = paths
        self._loaded = False
        self._client: Optional[AntigravityOAuthClient] = None

    def load(self) -> Optional[AntigravityOAuthClient]:
        if self._loaded:
            return self._client
        self._loaded = True
        for path in self.paths or self._candidate_paths():
            try:
                source = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if client := self.parse(source):
                self._client = client
                break
        return self._client

    @staticmethod
    def parse(source: str) -> Optional[AntigravityOAuthClient]:
        marker = source.find(_OAUTH_MODULE_MARKER)
        if marker < 0:
            return None
        match = _OAUTH_PAIR.search(source, marker, marker + 16_384)
        if match is None:
            return None
        return AntigravityOAuthClient(
            match.group("client_id"),
            match.group("client_secret"),
        )

    def _candidate_paths(self) -> tuple[Path, ...]:
        roots = [
            Path("/opt/antigravity-ide"),
            Path("/usr/share/antigravity-ide"),
            Path("/usr/lib/antigravity-ide"),
            Path("/usr/lib64/antigravity-ide"),
            Path.home() / ".local/share/antigravity-ide",
        ]
        executable = shutil.which(
            "antigravity-ide",
            path=self.environment.search_path(),
        )
        if executable:
            resolved = Path(executable).resolve()
            roots.extend((
                resolved.parent.parent,
                resolved.parent.parent / "share/antigravity-ide",
            ))
        paths = [
            root / "resources/app/out/main.js"
            for root in roots
        ]
        return tuple(dict.fromkeys(paths))


class AntigravityAuthStore:
    def __init__(
        self,
        environment: Optional[LoginShellEnvironment] = None,
        secret_store: Optional[SecretToolStore] = None,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self.environment = environment or LoginShellEnvironment()
        self.secrets = secret_store or SecretToolStore()
        self._now = now or (lambda: datetime.now(timezone.utc))

    def cache_path(self) -> Path:
        configured = self.environment.value("XDG_CACHE_HOME")
        root = Path(configured).expanduser() if configured else Path.home() / ".cache"
        return root / "ai-usage-kde" / "antigravity-auth.json"

    def load(self) -> Optional[AntigravityCredentials]:
        raw = self.secrets.lookup(SECRET_SERVICE, SECRET_USERNAME)
        return self.decode(raw) if raw is not None else None

    def usable_access_token(self, credentials: AntigravityCredentials) -> Optional[str]:
        access = non_empty(credentials.access_token)
        if access and (
            credentials.expires_at is None
            or (credentials.expires_at - self._utc_now()).total_seconds() > 60
        ):
            return access
        refresh = non_empty(credentials.refresh_token)
        if refresh is None:
            return None
        try:
            document = json.loads(self.cache_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(document, dict):
            return None
        expiration = provider_datetime(document.get("expires_at"))
        if (
            document.get("refresh_fingerprint") != self._fingerprint(refresh)
            or expiration is None
            or (expiration - self._utc_now()).total_seconds() <= 60
        ):
            return None
        return non_empty(document.get("access_token"))

    def cache(self, access_token: str, expires_in: float, refresh_token: str) -> bool:
        document = {
            "access_token": access_token,
            "expires_at": (
                self._utc_now() + timedelta(seconds=expires_in)
            ).isoformat(),
            "refresh_fingerprint": self._fingerprint(refresh_token),
        }
        return atomic_write_private(
            self.cache_path(),
            json.dumps(document, separators=(",", ":"), sort_keys=True),
        )

    @classmethod
    def decode(cls, raw: str) -> Optional[AntigravityCredentials]:
        text = raw.strip()
        prefix = "go-keyring-base64:"
        if text.startswith(prefix):
            try:
                text = base64.b64decode(text[len(prefix):]).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return None
        if text.startswith("Bearer "):
            return AntigravityCredentials(non_empty(text[7:]), None, None)
        try:
            value = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return AntigravityCredentials(non_empty(text), None, None)
        if isinstance(value, str):
            return AntigravityCredentials(non_empty(value), None, None)
        if not isinstance(value, dict):
            return None
        return cls._token_from(value)

    @classmethod
    def _token_from(cls, root: dict) -> Optional[AntigravityCredentials]:
        source = root.get("token") if isinstance(root.get("token"), dict) else root
        access = next((
            value for key in ("access_token", "accessToken", "id_token", "idToken")
            if (value := non_empty(source.get(key)))
        ), None)
        refresh = next((
            value for key in ("refresh_token", "refreshToken")
            if (value := non_empty(source.get(key)))
        ), None)
        expiration = next((
            value for key in ("expiry", "expires_at", "expiresAt")
            if (value := provider_datetime(source.get(key))) is not None
        ), None)
        if access or refresh:
            return AntigravityCredentials(access, refresh, expiration)
        for key in ("tokens", "oauth", "oauth2", "credentials", "auth"):
            if isinstance(root.get(key), dict):
                nested = cls._token_from(root[key])
                if nested:
                    return nested
        return None

    @staticmethod
    def _fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _utc_now(self) -> datetime:
        value = self._now()
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )


class AntigravityProvider:
    id = PROVIDER_ID
    display_name = DISPLAY

    def __init__(
        self,
        auth_store: Optional[AntigravityAuthStore] = None,
        oauth_client_store: Optional[AntigravityOAuthClientStore] = None,
        json_poster: Callable[..., HttpResponse] = http_post_json,
        form_poster: Callable[..., HttpResponse] = http_post_form,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._auth = auth_store or AntigravityAuthStore(now=self._now)
        self._oauth = oauth_client_store or AntigravityOAuthClientStore(
            self._auth.environment
        )
        self._post_json = json_poster
        self._post_form = form_poster

    def is_configured(self) -> bool:
        return self._auth.load() is not None

    def fetch(self) -> ProviderUsage:
        credentials = self._auth.load()
        if credentials is None:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Not logged in. Sign in through Antigravity.",
            )
        token = self._auth.usable_access_token(credentials)
        if token is None and credentials.refresh_token:
            token = self._refresh(credentials.refresh_token)
        if token is None:
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Antigravity session expired. Sign in again.",
            )
        outcome, summary = self._cloud(SUMMARY_PATH, token, "antigravity")
        if outcome == "authentication" and credentials.refresh_token:
            refreshed = self._refresh(credentials.refresh_token)
            if refreshed:
                token = refreshed
                outcome, summary = self._cloud(SUMMARY_PATH, token, "antigravity")
        if outcome == "authentication":
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Antigravity session expired. Sign in again.",
            )
        _, plan_response = self._cloud(PLAN_PATH, token, "agy")
        plan = self._plan(plan_response)
        if outcome == "success" and summary is not None:
            mapped = self._map_summary(summary, plan, self._utc_now())
            if mapped is not None:
                return mapped
        model_outcome, models = self._cloud(MODELS_PATH, token, "antigravity")
        if model_outcome == "success" and models is not None:
            mapped = self._map_legacy(models, plan, self._utc_now())
            if mapped is not None:
                return mapped
            return errored(
                PROVIDER_ID, DISPLAY, ICON,
                "Antigravity quota response changed.",
                FailureKind.INVALID_RESPONSE,
            )
        if model_outcome == "authentication":
            return unauthenticated(
                PROVIDER_ID, DISPLAY, ICON,
                "Antigravity session expired. Sign in again.",
            )
        return errored(
            PROVIDER_ID, DISPLAY, ICON,
            "Antigravity could not be reached.",
            FailureKind.TRANSIENT,
        )

    def _cloud(
        self,
        path: str,
        access_token: str,
        user_agent: str,
    ) -> tuple[str, Optional[HttpResponse]]:
        for base in CLOUD_BASES:
            try:
                response = self._post_json(
                    base + path,
                    {},
                    {
                        "Accept": "application/json",
                        "Authorization": f"Bearer {access_token}",
                        "User-Agent": user_agent,
                    },
                )
            except Exception:
                continue
            if response.status in (401, 403):
                return "authentication", response
            if 200 <= response.status < 300:
                return "success", response
        return "unavailable", None

    def _refresh(self, refresh_token: str) -> Optional[str]:
        client = self._oauth.load()
        if client is None:
            return None
        try:
            response = self._post_form(
                REFRESH_URL,
                [
                    ("client_id", client.client_id),
                    ("client_secret", client.client_secret),
                    ("refresh_token", refresh_token),
                    ("grant_type", "refresh_token"),
                ],
                {},
            )
            body = response.json()
        except Exception:
            return None
        token = non_empty(body.get("access_token")) if isinstance(body, dict) else None
        if not 200 <= response.status < 300 or token is None:
            return None
        expires_in = number(body.get("expires_in")) or 3600
        self._auth.cache(token, expires_in, refresh_token)
        return token

    @staticmethod
    def _map_summary(
        response: HttpResponse,
        plan: Optional[str],
        now: datetime,
    ) -> Optional[ProviderUsage]:
        try:
            root = response.json()
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(root, dict):
            return None
        container = root.get("response") if isinstance(root.get("response"), dict) else root
        groups = container.get("groups") if isinstance(container, dict) else None
        if not isinstance(groups, list):
            return None
        kinds = {
            "gemini-5h": ("session", "Session"),
            "gemini-weekly": ("weekly", "Weekly"),
            "3p-5h": ("claude_pool", "Claude"),
            "3p-weekly": ("claude_pool_weekly", "Claude Weekly"),
        }
        windows: list[UsageWindow] = []
        seen: set[str] = set()
        for group in groups:
            buckets = group.get("buckets") if isinstance(group, dict) else None
            for bucket in buckets if isinstance(buckets, list) else []:
                if not isinstance(bucket, dict):
                    continue
                details = kinds.get(non_empty(bucket.get("bucketId")) or "")
                remaining = number(bucket.get("remainingFraction"))
                if details is None or remaining is None or details[0] in seen:
                    continue
                seen.add(details[0])
                windows.append(UsageWindow(
                    details[1],
                    details[0],
                    round(min(max((1 - remaining) * 100, 0), 100)),
                    provider_datetime(bucket.get("resetTime")),
                ))
        order = {"session": 0, "weekly": 1, "claude_pool": 2, "claude_pool_weekly": 3}
        windows.sort(key=lambda item: order.get(item.kind, 99))
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

    @staticmethod
    def _map_legacy(
        response: HttpResponse,
        plan: Optional[str],
        now: datetime,
    ) -> Optional[ProviderUsage]:
        try:
            root = response.json()
        except (ValueError, UnicodeDecodeError):
            return None
        models = root.get("models") if isinstance(root, dict) else None
        if not isinstance(models, dict):
            return None
        worst: dict[str, tuple[float, Optional[datetime]]] = {}
        for raw in models.values():
            if not isinstance(raw, dict) or raw.get("isInternal") is True:
                continue
            label = non_empty(raw.get("displayName")) or non_empty(raw.get("label"))
            quota = raw.get("quotaInfo")
            if label is None or not isinstance(quota, dict):
                continue
            kind = "session" if "gemini" in label.lower() else "claude_pool"
            remaining = number(quota.get("remainingFraction"))
            remaining = remaining if remaining is not None else 0
            if kind not in worst or remaining < worst[kind][0]:
                worst[kind] = (remaining, provider_datetime(quota.get("resetTime")))
        if not worst:
            return None
        captions = {"session": "Session", "claude_pool": "Claude"}
        windows = [
            UsageWindow(
                captions[kind],
                kind,
                round(min(max((1 - value[0]) * 100, 0), 100)),
                value[1],
            )
            for kind, value in sorted(
                worst.items(),
                key=lambda item: {"session": 0, "claude_pool": 1}[item[0]],
            )
        ]
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

    @staticmethod
    def _plan(response: Optional[HttpResponse]) -> Optional[str]:
        if response is None:
            return None
        try:
            root = response.json()
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(root, dict):
            return None
        tier = root.get("paidTier") if isinstance(root.get("paidTier"), dict) else root.get("currentTier")
        raw = non_empty(tier.get("name")) if isinstance(tier, dict) else None
        if raw is None:
            return None
        for name in ("Ultra", "Pro", "Free"):
            if name.lower() in raw.lower():
                return name
        return title_case_identifier(raw)

    def _utc_now(self) -> datetime:
        value = self._now()
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )
