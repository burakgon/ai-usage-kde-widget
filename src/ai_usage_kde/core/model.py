from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ProviderStatus(str, Enum):
    OK = "ok"
    UNAUTHENTICATED = "unauthenticated"
    ERROR = "error"
    STALE = "stale"


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
    kind: str               # "session" | "weekly" | "weekly_opus" | "weekly_sonnet" | "code_review"
    used_percent: float
    resets_at: Optional[datetime]


@dataclass
class Credits:
    used: float
    cap: float
    currency: str = "USD"


@dataclass
class ProviderUsage:
    provider_id: str
    display_name: str
    icon: str
    plan: Optional[str]
    status: ProviderStatus
    error_message: Optional[str]
    windows: list[UsageWindow] = field(default_factory=list)
    credits: Optional[Credits] = None
    last_updated: Optional[datetime] = None

    def session_percent(self) -> Optional[float]:
        for w in self.windows:
            if w.kind == "session":
                return w.used_percent
        return None
