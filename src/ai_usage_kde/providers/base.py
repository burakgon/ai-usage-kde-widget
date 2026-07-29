from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol

from ..core.model import FailureKind, ProviderUsage, ProviderStatus
from ..core.parsing import provider_datetime


def parse_reset(value) -> Optional[datetime]:
    return provider_datetime(value)


class Provider(Protocol):
    id: str
    display_name: str
    def is_configured(self) -> bool: ...
    def fetch(self) -> ProviderUsage: ...


def unauthenticated(provider_id: str, display_name: str, icon: str, hint: str) -> ProviderUsage:
    return ProviderUsage(provider_id=provider_id, display_name=display_name, icon=icon,
                         plan=None, status=ProviderStatus.UNAUTHENTICATED,
                         error_message=hint, failure_kind=FailureKind.AUTHENTICATION,
                         windows=[], billing_usage=None,
                         last_updated=None, retry_at=None)


def errored(
    provider_id: str,
    display_name: str,
    icon: str,
    message: str,
    kind: FailureKind = FailureKind.TRANSIENT,
) -> ProviderUsage:
    return ProviderUsage(provider_id=provider_id, display_name=display_name, icon=icon,
                         plan=None, status=ProviderStatus.ERROR,
                         error_message=message, failure_kind=kind,
                         windows=[], billing_usage=None,
                         last_updated=None, retry_at=None)


def rate_limited(
    provider_id: str,
    display_name: str,
    icon: str,
    message: str,
    retry_at: datetime,
) -> ProviderUsage:
    return ProviderUsage(
        provider_id=provider_id,
        display_name=display_name,
        icon=icon,
        plan=None,
        status=ProviderStatus.RATE_LIMITED,
        error_message=message,
        failure_kind=FailureKind.RATE_LIMITED,
        windows=[],
        billing_usage=None,
        last_updated=None,
        retry_at=retry_at,
    )
