import json

import pytest

from ai_usage_kde import cli
from ai_usage_kde.core.catalog import PROVIDER_IDS, catalog_json
from ai_usage_kde.core.http import HttpResponse
from ai_usage_kde.core.snapshot import collect_snapshot
from ai_usage_kde.core.update import check_for_update, is_newer


def test_catalog_has_reference_order_defaults_and_metrics():
    catalog = catalog_json()
    assert tuple(item["provider_id"] for item in catalog) == PROVIDER_IDS
    assert PROVIDER_IDS == (
        "claude", "codex", "cursor", "antigravity", "copilot", "devin", "grok"
    )
    assert catalog[0]["default_metric"] == "weekly"
    assert catalog[2]["default_metric"] == "total_usage"
    assert catalog[4]["default_metric"] == "credits"


def test_cli_provider_filter_is_forwarded(monkeypatch, capsys):
    captured = {}

    def collect(**kwargs):
        captured.update(kwargs)
        return {"schema_version": 2, "providers": []}

    monkeypatch.setattr(cli, "collect_snapshot", collect)
    assert cli.main(["--providers=codex,claude,codex"]) == 0
    assert captured["provider_ids"] == ["codex", "claude"]
    assert json.loads(capsys.readouterr().out)["schema_version"] == 2


def test_cli_catalog_does_not_collect_provider_usage(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "collect_snapshot",
        lambda **kwargs: pytest.fail("catalog must not contact providers"),
    )
    assert cli.main(["--catalog"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 2
    assert len(payload["catalog"]) == 7
    assert payload["providers"] == []


def test_untracked_installed_provider_is_not_instantiated(monkeypatch):
    import ai_usage_kde.core.snapshot as snapshot

    monkeypatch.setattr(
        snapshot,
        "provider_factory",
        lambda *args: pytest.fail("untracked provider must not be instantiated"),
    )
    payload = collect_snapshot(
        installed_provider_ids={"claude"},
        provider_ids=[],
    )
    assert payload["installed_provider_ids"] == ["claude"]
    assert payload["providers"] == []


def test_semver_and_update_check():
    assert is_newer("v2.1.0", "2.0.0")
    assert is_newer("2.0.0", "2.0.0-rc.2")
    assert is_newer("2.0.0-rc.10", "2.0.0-rc.2")
    assert not is_newer("1.9.9", "2.0.0")

    result = check_for_update(
        "2.0.0",
        getter=lambda *args, **kwargs: HttpResponse(
            200,
            b'{"tag_name":"v2.1.0","html_url":"https://github.com/example/release"}',
            {},
        ),
    )
    assert result["update_available"] is True
    assert result["latest_version"] == "2.1.0"
    assert result["release_url"] == "https://github.com/example/release"

    no_releases = check_for_update(
        "2.0.0",
        getter=lambda *args, **kwargs: HttpResponse(404, b"{}", {}),
    )
    assert no_releases["error"] is None
    assert no_releases["update_available"] is False
    assert no_releases["latest_version"] == "2.0.0"
