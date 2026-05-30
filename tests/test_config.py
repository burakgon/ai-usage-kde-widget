from PySide6.QtCore import QSettings

from ai_usage_kde.core.config import Config


def _isolated_settings(tmp_path):
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                     "ai-usage-kde-test", "ai-usage-kde-test")


def test_defaults(tmp_path):
    cfg = Config(_isolated_settings(tmp_path))
    assert cfg.refresh_seconds() == 180
    assert cfg.badge_enabled() is True
    assert cfg.enabled_providers() == ["claude", "codex"]


def test_roundtrip(tmp_path):
    cfg = Config(_isolated_settings(tmp_path))
    cfg.set_refresh_seconds(300)
    cfg.set_badge_enabled(False)
    assert cfg.refresh_seconds() == 300
    assert cfg.badge_enabled() is False


def test_refresh_seconds_floor_is_180(tmp_path):
    cfg = Config(_isolated_settings(tmp_path))
    cfg.set_refresh_seconds(5)        # below safe floor
    assert cfg.refresh_seconds() == 180


def test_autostart_file_write_and_remove(tmp_path):
    cfg = Config(_isolated_settings(tmp_path))
    target = tmp_path / "autostart" / "ai-usage-kde.desktop"
    cfg.set_autostart(True, desktop_path=target, exec_cmd="ai-usage-kde")
    assert target.exists()
    assert "Exec=ai-usage-kde" in target.read_text()
    cfg.set_autostart(False, desktop_path=target, exec_cmd="ai-usage-kde")
    assert not target.exists()
