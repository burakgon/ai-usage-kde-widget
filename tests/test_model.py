from datetime import datetime, timezone

from ai_usage_kde.core.model import (
    BillingUsage, ProviderStatus, ProviderUsage, UsageWindow, threshold_color,
)


def test_threshold_color_bands():
    assert threshold_color(0) == "#3daee9"
    assert threshold_color(59.9) == "#3daee9"
    assert threshold_color(60) == "#f67400"
    assert threshold_color(84.9) == "#f67400"
    assert threshold_color(85) == "#da4453"
    assert threshold_color(150) == "#da4453"


def test_provider_usage_session_percent_picks_session_window():
    w_session = UsageWindow(caption="Session · 5h", kind="session", used_percent=42.0,
                            resets_at=datetime(2026, 5, 30, tzinfo=timezone.utc))
    w_week = UsageWindow(caption="Weekly · 7d", kind="weekly", used_percent=18.0, resets_at=None)
    p = ProviderUsage(provider_id="claude", display_name="Claude Code", icon="claude.svg",
                      plan="Max 20x", status=ProviderStatus.OK, error_message=None,
                      windows=[w_session, w_week], billing_usage=None, last_updated=None)
    assert p.session_percent() == 42.0


def test_provider_usage_session_percent_none_when_no_session():
    p = ProviderUsage(provider_id="codex", display_name="Codex", icon="codex.svg",
                      plan=None, status=ProviderStatus.UNAUTHENTICATED, error_message=None,
                      windows=[], billing_usage=None, last_updated=None)
    assert p.session_percent() is None


def test_billing_usage_constructors_are_unambiguous():
    bounded = BillingUsage.bounded_spend(5, 10)
    assert bounded.kind == "bounded_spend"
    assert bounded.used_amount == 5 and bounded.limit_amount == 10

    balance = BillingUsage.flex_credit_balance(820, 32.8)
    assert balance.kind == "flex_credit_balance"
    assert balance.remaining_credits == 820 and balance.usd_value == 32.8
