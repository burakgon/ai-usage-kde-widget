from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from .catalog import CATALOG_BY_ID, PROVIDER_IDS, catalog_json
from .discovery import detect_installed_providers
from .environment import LoginShellEnvironment
from .model import BillingUsage, FailureKind, ProviderStatus, ProviderUsage, threshold_color


SCHEMA_VERSION = 2


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _billing_dict(billing: Optional[BillingUsage]) -> Optional[dict]:
    if billing is None:
        return None
    result = {"kind": billing.kind}
    for name in (
        "used_amount",
        "limit_amount",
        "currency_code",
        "remaining_credits",
        "usd_value",
    ):
        if (value := getattr(billing, name)) is not None:
            result[name] = value
    return result


def provider_dict(usage: ProviderUsage) -> dict:
    return {
        "provider_id": usage.provider_id,
        "display_name": usage.display_name,
        "icon": usage.icon,
        "plan": usage.plan,
        "status": usage.status.value,
        "failure_kind": (
            usage.failure_kind.value if usage.failure_kind is not None else None
        ),
        "error_message": usage.error_message,
        "retry_at": _iso(usage.retry_at),
        "last_updated": _iso(usage.last_updated),
        "available_metrics": usage.available_metrics,
        "billing_usage": _billing_dict(usage.billing_usage),
        "windows": [
            {
                "caption": window.caption,
                "kind": window.kind,
                "used_percent": window.used_percent,
                "color": threshold_color(window.used_percent),
                "resets_at": _iso(window.resets_at),
            }
            for window in usage.windows
        ],
    }


def build_snapshot(
    usages: Iterable[ProviderUsage],
    *,
    installed_provider_ids: Optional[Iterable[str]] = None,
    generated_at: Optional[datetime] = None,
) -> dict:
    usage_list = list(usages)
    installed = (
        list(installed_provider_ids)
        if installed_provider_ids is not None
        else [usage.provider_id for usage in usage_list]
    )
    installed_set = set(installed)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso(generated_at or _utc_now()),
        "catalog": catalog_json(),
        "installed_provider_ids": [
            provider_id for provider_id in PROVIDER_IDS if provider_id in installed_set
        ],
        "providers": [provider_dict(usage) for usage in usage_list],
    }


def provider_factory(
    provider_id: str,
    environment: Optional[LoginShellEnvironment] = None,
):
    environment = environment or LoginShellEnvironment()
    if provider_id == "claude":
        from .auth import ClaudeAuthStore
        from ..providers.claude import ClaudeProvider

        store = ClaudeAuthStore(environment)
        return ClaudeProvider(creds=store.load(), auth_store=store)
    if provider_id == "codex":
        from .auth import CodexAuthStore
        from ..providers.codex import CodexProvider

        store = CodexAuthStore(environment)
        return CodexProvider(
            creds=store.load_file_candidates(),
            auth_store=store,
            allow_keyring=True,
        )
    if provider_id == "cursor":
        from ..providers.cursor import CursorAuthStore, CursorProvider

        return CursorProvider(auth_store=CursorAuthStore(environment))
    if provider_id == "antigravity":
        from ..providers.antigravity import AntigravityAuthStore, AntigravityProvider

        return AntigravityProvider(auth_store=AntigravityAuthStore(environment))
    if provider_id == "copilot":
        from ..providers.copilot import CopilotAuthStore, CopilotProvider

        return CopilotProvider(auth_store=CopilotAuthStore(environment))
    if provider_id == "devin":
        from ..providers.devin import DevinAuthStore, DevinProvider

        return DevinProvider(auth_store=DevinAuthStore(environment))
    if provider_id == "grok":
        from ..providers.grok import GrokAuthStore, GrokProvider

        return GrokProvider(auth_store=GrokAuthStore(environment))
    raise ValueError(f"Unsupported provider: {provider_id}")


def collect_snapshot(
    providers=None,
    *,
    provider_ids: Optional[Iterable[str]] = None,
    environment: Optional[LoginShellEnvironment] = None,
    installed_provider_ids: Optional[set[str]] = None,
    availability_detector: Callable[..., set[str]] = detect_installed_providers,
) -> dict:
    """Detect, filter, and concurrently refresh tracked installed providers."""
    environment = environment or LoginShellEnvironment()
    if providers is None:
        installed = (
            set(installed_provider_ids)
            if installed_provider_ids is not None
            else availability_detector(environment)
        )
        requested = set(provider_ids) if provider_ids is not None else set(PROVIDER_IDS)
        selected = [
            provider_id
            for provider_id in PROVIDER_IDS
            if provider_id in installed and provider_id in requested
        ]
        provider_list = [
            provider_factory(provider_id, environment)
            for provider_id in selected
        ]
    else:
        provider_list = list(providers)
        installed = {
            getattr(provider, "id", "")
            for provider in provider_list
            if getattr(provider, "id", "")
        }

    if len(provider_list) > 1:
        with ThreadPoolExecutor(max_workers=len(provider_list)) as executor:
            usages = list(executor.map(_safe_fetch, provider_list))
    else:
        usages = [_safe_fetch(provider) for provider in provider_list]
    return build_snapshot(usages, installed_provider_ids=installed)


def catalog_snapshot() -> dict:
    return build_snapshot([], installed_provider_ids=[])


def _safe_fetch(provider) -> ProviderUsage:
    try:
        return provider.fetch()
    except Exception:
        provider_id = getattr(provider, "id", "unknown")
        catalog = CATALOG_BY_ID.get(provider_id)
        display_name = getattr(
            provider,
            "display_name",
            catalog.display_name if catalog else provider_id.title(),
        )
        return ProviderUsage(
            provider_id=provider_id,
            display_name=display_name,
            icon=catalog.icon if catalog else f"provider-{provider_id}.svg",
            plan=None,
            status=ProviderStatus.ERROR,
            error_message=f"{display_name} could not be refreshed.",
            failure_kind=FailureKind.TRANSIENT,
        )
