from datetime import datetime, timezone

from ai_usage_kde.core.controller import Controller, build_snapshot
from ai_usage_kde.core.model import ProviderUsage, ProviderStatus, UsageWindow


def _usage(pid, session_pct):
    return ProviderUsage(provider_id=pid, display_name=pid.title(), icon=f"{pid}.svg",
                         plan="Plan", status=ProviderStatus.OK, error_message=None,
                         windows=[UsageWindow(caption="Session · 5h", kind="session",
                                              used_percent=session_pct, resets_at=None)],
                         credits=None, last_updated=datetime.now(timezone.utc))


def test_build_snapshot_serializes_windows():
    snap = build_snapshot([_usage("claude", 42.0)], local=None)
    assert snap["providers"][0]["provider_id"] == "claude"
    w = snap["providers"][0]["windows"][0]
    assert w["used_percent"] == 42.0 and w["color"] == "#3daee9"


def test_badge_percent_is_max_session():
    c = Controller(providers=[], local_paths_fn=lambda: [])
    c._usages = [_usage("claude", 42.0), _usage("codex", 67.0)]
    assert c.badge_percent() == 67


def test_refresh_now_populates_from_stub_providers(qtbot_none=None):
    calls = {"n": 0}

    class Stub:
        id = "claude"
        def is_configured(self): return True
        def fetch(self):
            calls["n"] += 1
            return _usage("claude", 50.0)

    c = Controller(providers=[Stub()], local_paths_fn=lambda: [])
    c.refresh_blocking()   # synchronous variant for tests
    assert calls["n"] == 1
    assert c.badge_percent() == 50
