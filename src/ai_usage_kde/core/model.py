from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ProviderStatus(str, Enum):
    OK = "ok"
    UNAUTHENTICATED = "unauthenticated"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    STALE = "stale"


class FailureKind(str, Enum):
    AUTHENTICATION = "authentication"
    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    INVALID_RESPONSE = "invalid_response"
    STORAGE = "storage"

    @property
    def preserves_last_good(self) -> bool:
        return self in {
            FailureKind.TRANSIENT,
            FailureKind.RATE_LIMITED,
            FailureKind.INVALID_RESPONSE,
        }


def threshold_color(percent: float) -> str:
    """Breeze color band for a utilization percent."""
    if percent >= 85:
        return "#da4453"  # critical
    if percent >= 60:
        return "#f67400"  # warning
    return "#3daee9"      # normal


@dataclass
class UsageWindow:
    caption: str
    kind: str
    used_percent: float
    resets_at: Optional[datetime]


@dataclass
class BillingUsage:
    kind: str
    used_amount: Optional[float] = None
    limit_amount: Optional[float] = None
    currency_code: Optional[str] = None
    remaining_credits: Optional[int] = None
    usd_value: Optional[float] = None

    @classmethod
    def bounded_spend(
        cls,
        used_amount: float,
        limit_amount: float,
        currency_code: str = "USD",
    ) -> "BillingUsage":
        return cls(
            kind="bounded_spend",
            used_amount=used_amount,
            limit_amount=limit_amount,
            currency_code=currency_code,
        )

    @classmethod
    def unbounded_spend(
        cls,
        used_amount: float,
        currency_code: str = "USD",
    ) -> "BillingUsage":
        return cls(
            kind="unbounded_spend",
            used_amount=used_amount,
            currency_code=currency_code,
        )

    @classmethod
    def flex_credit_balance(
        cls,
        remaining_credits: int,
        usd_value: float,
    ) -> "BillingUsage":
        return cls(
            kind="flex_credit_balance",
            remaining_credits=remaining_credits,
            usd_value=usd_value,
        )


@dataclass
class ProviderUsage:
    provider_id: str
    display_name: str
    icon: str
    plan: Optional[str]
    status: ProviderStatus
    error_message: Optional[str]
    failure_kind: Optional[FailureKind] = None
    windows: list[UsageWindow] = field(default_factory=list)
    billing_usage: Optional[BillingUsage] = None
    last_updated: Optional[datetime] = None
    retry_at: Optional[datetime] = None

    def session_percent(self) -> Optional[float]:
        for w in self.windows:
            if w.kind == "session":
                return w.used_percent
        return None

    @property
    def available_metrics(self) -> list[str]:
        metrics = [window.kind for window in self.windows]
        if self.billing_usage is not None:
            metrics.append(
                "credits"
                if self.billing_usage.kind == "flex_credit_balance"
                else "extra_usage"
            )
        return list(dict.fromkeys(metrics))
