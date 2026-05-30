from __future__ import annotations

import os
import sys
from pathlib import Path

# Native Breeze look for QtQuick Controls; must be set before the QML engine builds a style.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "org.kde.desktop")

from PySide6.QtCore import QUrl, QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from .core.config import Config
from .core.controller import Controller
from .core.tray import Tray, render_badge_pixmap
from .core.auth import load_claude_credentials, load_codex_credentials
from .providers.claude import ClaudeProvider
from .providers.codex import CodexProvider
from .usage.local_claude import find_transcripts

HERE = Path(__file__).resolve().parent


def _build_providers():
    return [
        ClaudeProvider(creds=load_claude_credentials()),
        CodexProvider(creds=load_codex_credentials()),
    ]


def main() -> int:
    QCoreApplication.setOrganizationName("ai-usage-kde")
    QCoreApplication.setApplicationName("ai-usage-kde")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    controller = Controller(providers=_build_providers(), local_paths_fn=find_transcripts)

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    engine.addImportPath(str(HERE / "qml"))
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        print("Failed to load QML", file=sys.stderr)
        return 1
    popup = engine.rootObjects()[0]

    def toggle_popup():
        # Wayland can't position client windows; let the compositor place it (v1).
        if popup.isVisible():
            popup.hide()
        else:
            popup.show()
            popup.raise_()
            popup.requestActivate()

    cfg = Config()
    app_icon = QIcon(str(HERE / "resources" / "app-icon.svg"))

    tray = Tray(on_toggle=toggle_popup,
                on_refresh=controller.refresh_async,
                on_settings=toggle_popup,
                on_quit=app.quit)
    tray.setIcon(app_icon)
    tray.show()

    def update_badge():
        if cfg.badge_enabled():
            tray.setIcon(QIcon(render_badge_pixmap(controller.badge_percent(),
                                                   controller.badge_color())))
        else:
            tray.setIcon(app_icon)
    controller.badgeChanged.connect(update_badge)

    controller.start(cfg.refresh_seconds())
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
