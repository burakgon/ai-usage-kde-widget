import os
from pathlib import Path

# Force the Basic Controls style so compilation needs only QGuiApplication (no QtWidgets/Breeze).
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent
from PySide6.QtCore import QUrl

QML_DIR = Path(__file__).resolve().parent.parent / "src" / "ai_usage_kde" / "qml"


def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def _check(filename):
    _app()
    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR))
    comp = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / filename)))
    assert not comp.isError(), filename + ":\n" + "\n".join(e.toString() for e in comp.errors())


def test_usagebar_compiles():
    _check("UsageBar.qml")

def test_localblock_compiles():
    _check("LocalBlock.qml")

def test_providersection_compiles():
    _check("ProviderSection.qml")

def test_main_compiles():
    _check("Main.qml")

def test_settings_compiles():
    _check("Settings.qml")
