from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol

from ..core.model import ProviderUsage, ProviderStatus, UsageWindow


def parse_reset(value) -> Optional[datetime]:
    """Accept ISO 'resets_at' strings (with Z) -> aware datetime, else None."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Provider(Protocol):
    id: str
    display_name: str
    def is_configured(self) -> bool: ...
    def fetch(self) -> ProviderUsage: ...


def unauthenticated(provider_id: str, display_name: str, icon: str, hint: str) -> ProviderUsage:
    return ProviderUsage(provider_id=provider_id, display_name=display_name, icon=icon,
                         plan=None, status=ProviderStatus.UNAUTHENTICATED,
                         error_message=hint, windows=[], credits=None, last_updated=None)


def errored(provider_id: str, display_name: str, icon: str, message: str) -> ProviderUsage:
    return ProviderUsage(provider_id=provider_id, display_name=display_name, icon=icon,
                         plan=None, status=ProviderStatus.ERROR,
                         error_message=message, windows=[], credits=None, last_updated=None)
