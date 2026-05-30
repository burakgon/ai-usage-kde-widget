from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QSize

from ai_usage_kde.core.tray import render_badge_pixmap


def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def test_render_badge_returns_sized_pixmap():
    _app()
    pm = render_badge_pixmap(percent=67, color="#f67400", size=64)
    assert not pm.isNull()
    assert pm.size() == QSize(64, 64)


def test_render_badge_handles_zero():
    _app()
    pm = render_badge_pixmap(percent=0, color="#3daee9", size=22)
    assert not pm.isNull()
