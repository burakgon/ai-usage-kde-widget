import os
import subprocess
import sys
from datetime import datetime, timezone

from conftest import SRC
from ai_usage_kde.core.environment import LoginShellEnvironment
from ai_usage_kde.core.model import (
    BillingUsage,
    ProviderStatus,
    ProviderUsage,
    UsageWindow,
)
from ai_usage_kde.core.snapshot import build_snapshot, collect_snapshot


def _usage(provider_id, percent, billing=None):
    return ProviderUsage(
        provider_id=provider_id,
        display_name=provider_id.title(),
        icon=f"{provider_id}.svg",
        plan="Plan",
        status=ProviderStatus.OK,
        error_message=None,
        windows=[UsageWindow("Session · 5h", "session", percent, None)],
        billing_usage=billing,
        last_updated=datetime.now(timezone.utc),
        retry_at=None,
    )


def test_build_snapshot_serializes_color_billing_and_retry_fields():
    snapshot = build_snapshot(
        [_usage("claude", 42.0, BillingUsage.bounded_spend(5, 10))],
    )
    provider = snapshot["providers"][0]
    window = provider["windows"][0]
    assert window["used_percent"] == 42.0 and window["color"] == "#3daee9"
    assert provider["billing_usage"] == {
        "kind": "bounded_spend",
        "used_amount": 5,
        "limit_amount": 10,
        "currency_code": "USD",
    }
    assert provider["retry_at"] is None
    assert "credits" not in provider
    assert snapshot["schema_version"] == 2
    assert snapshot["installed_provider_ids"] == ["claude"]
    assert len(snapshot["catalog"]) == 7


def test_collect_snapshot_with_stub_providers():
    class Stub:
        id = "x"
        display_name = "X"

        def fetch(self):
            return _usage("x", 90.0)

    snapshot = collect_snapshot(providers=[Stub()])
    assert snapshot["providers"][0]["provider_id"] == "x"
    assert snapshot["providers"][0]["windows"][0]["color"] == "#da4453"


def test_provider_failure_is_isolated():
    class Broken:
        id = "broken"
        display_name = "Broken"

        def fetch(self):
            raise OSError("offline")

    class Healthy:
        id = "healthy"
        display_name = "Healthy"

        def fetch(self):
            return _usage("healthy", 20)

    snapshot = collect_snapshot(providers=[Broken(), Healthy()])
    by_id = {item["provider_id"]: item for item in snapshot["providers"]}
    assert by_id["broken"]["status"] == "error"
    assert by_id["healthy"]["status"] == "ok"


def test_default_collection_hides_uninstalled_providers():
    environment = LoginShellEnvironment(environ={"PATH": "/usr/bin"})
    snapshot = collect_snapshot(
        installed_provider_ids=set(),
        environment=environment,
    )
    assert snapshot["schema_version"] == 2
    assert snapshot["providers"] == []
    assert snapshot["installed_provider_ids"] == []


def test_installed_but_signed_out_claude_remains_visible(tmp_path):
    environment = LoginShellEnvironment(environ={
        "PATH": "/usr/bin",
        "CLAUDE_CONFIG_DIR": str(tmp_path / "missing-profile"),
    })
    snapshot = collect_snapshot(
        installed_provider_ids={"claude"},
        environment=environment,
    )
    assert len(snapshot["providers"]) == 1
    assert snapshot["providers"][0]["provider_id"] == "claude"
    assert snapshot["providers"][0]["status"] == "unauthenticated"


def test_json_cli_is_qt_free():
    code = "import sys, ai_usage_kde.cli; sys.exit(1 if 'PySide6' in sys.modules else 0)"
    environment = {**os.environ, "PYTHONPATH": str(SRC)}
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "cli pulled in PySide6:\n" + result.stderr
