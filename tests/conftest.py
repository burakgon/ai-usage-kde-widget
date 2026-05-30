import os
import sys
from pathlib import Path

# Headless Qt for any test that touches PySide6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture(name: str) -> Path:
    return FIXTURES / name
