import os
import subprocess
import sys
from datetime import datetime, timezone

from conftest import SRC
from ai_usage_kde.core.snapshot import build_snapshot, collect_snapshot
from ai_usage_kde.core.model import ProviderUsage, ProviderStatus, UsageWindow


def _usage(pid, pct):
    return ProviderUsage(provider_id=pid, display_name=pid.title(), icon=f"{pid}.svg",
                         plan="Plan", status=ProviderStatus.OK, error_message=None,
                         windows=[UsageWindow("Session · 5h", "session", pct, None)],
                         credits=None, last_updated=datetime.now(timezone.utc))


def test_build_snapshot_color_and_fields():
    snap = build_snapshot([_usage("claude", 42.0)], local=None)
    w = snap["providers"][0]["windows"][0]
    assert w["used_percent"] == 42.0 and w["color"] == "#3daee9"
    assert snap["local_claude"] is None


def test_collect_snapshot_with_stub_providers():
    class Stub:
        def fetch(self):
            return _usage("x", 90.0)
    snap = collect_snapshot(providers=[Stub()], local_paths=[])
    assert snap["providers"][0]["provider_id"] == "x"
    assert snap["providers"][0]["windows"][0]["color"] == "#da4453"  # 90% -> critical
    assert snap["local_claude"] is None


def test_json_cli_is_qt_free():
    # The --json helper must not import PySide6 (so the plasmoid can call it cheaply).
    code = "import sys, ai_usage_kde.cli; sys.exit(1 if 'PySide6' in sys.modules else 0)"
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode == 0, "cli pulled in PySide6:\n" + r.stderr
