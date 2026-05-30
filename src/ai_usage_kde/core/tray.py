from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon
from PySide6.QtWidgets import QSystemTrayIcon, QMenu


def render_badge_pixmap(percent: int, color: str, size: int = 64) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    # rounded background
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRect(0, 0, size, size), size * 0.22, size * 0.22)
    # percent text
    p.setPen(QColor("#ffffff"))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(size * (0.5 if percent < 100 else 0.4)))
    p.setFont(f)
    p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, str(int(percent)))
    p.end()
    return pm


class Tray(QSystemTrayIcon):
    def __init__(self, on_toggle: Callable[[], None], on_refresh: Callable[[], None],
                 on_settings: Callable[[], None], on_quit: Callable[[], None], parent=None):
        super().__init__(parent)
        self._on_toggle = on_toggle
        menu = QMenu()
        menu.addAction("Refresh now", on_refresh)
        menu.addAction("Settings…", on_settings)
        menu.addSeparator()
        menu.addAction("Quit", on_quit)
        self.setContextMenu(menu)
        self.activated.connect(self._activated)
        self.setToolTip("AI Usage")

    def _activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._on_toggle()

    def update_badge(self, percent: int, color: str, enabled: bool):
        if enabled:
            self.setIcon(QIcon(render_badge_pixmap(percent, color)))
        # when disabled, main.py sets the static app icon instead
