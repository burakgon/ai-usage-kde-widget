from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings

_REFRESH_FLOOR = 180
_DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Name=AI Usage
Comment=Claude Code and Codex usage in the system tray
Exec={exec_cmd}
Icon=ai-usage-kde
X-GNOME-Autostart-enabled=true
Categories=Utility;
"""


class Config:
    def __init__(self, settings: Optional[QSettings] = None):
        self._s = settings or QSettings("ai-usage-kde", "ai-usage-kde")

    def refresh_seconds(self) -> int:
        return max(_REFRESH_FLOOR, int(self._s.value("refresh_seconds", _REFRESH_FLOOR)))

    def set_refresh_seconds(self, value: int) -> None:
        self._s.setValue("refresh_seconds", max(_REFRESH_FLOOR, int(value)))

    def badge_enabled(self) -> bool:
        return self._s.value("badge_enabled", True, type=bool)

    def set_badge_enabled(self, value: bool) -> None:
        self._s.setValue("badge_enabled", bool(value))

    def enabled_providers(self) -> list[str]:
        raw = self._s.value("enabled_providers", ["claude", "codex"])
        if isinstance(raw, str):
            return [raw]
        return list(raw)

    def default_autostart_path(self) -> Path:
        return Path.home() / ".config" / "autostart" / "ai-usage-kde.desktop"

    def set_autostart(self, enabled: bool, *, desktop_path: Optional[Path] = None,
                      exec_cmd: str = "ai-usage-kde") -> None:
        path = desktop_path or self.default_autostart_path()
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_DESKTOP_TEMPLATE.format(exec_cmd=exec_cmd), encoding="utf-8")
        elif path.exists():
            path.unlink()
        self._s.setValue("autostart", bool(enabled))

    def autostart_enabled(self) -> bool:
        return self._s.value("autostart", False, type=bool)
