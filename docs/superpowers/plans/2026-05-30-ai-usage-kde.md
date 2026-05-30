# ai-usage-kde Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A native KDE Plasma system-tray app that shows live Claude Code & Codex subscription usage (5h/7d windows, plan, credits) plus a local Claude token/cost breakdown.

**Architecture:** Backend logic is plain, Qt-free Python (data model, pricing, JSONL parser, providers, auth) so it unit-tests without a display. Only the bridge (`Controller`), `config`, and `tray` use Qt (PySide6). HTTP is injected as a callable for testability. The UI is QML using the system's `org.kde.desktop` Breeze style + Kirigami; a frameless popup anchors to the tray icon.

**Tech Stack:** Python 3.14, PySide6 6.11 (system pacman package, matches system Qt 6.11.1 so it sees Kirigami/qqc2-desktop-style), QML/QtQuick Controls 2 + Kirigami, pytest. Stdlib `urllib`/`json` for networking (no `requests` dependency).

---

## Conventions

- **Repo root:** `/home/burakgon/Developer/ai-usage-linux` (git, branch `master`).
- **Package layout:** `src/` layout, importable package `ai_usage_kde`.
- **Run tests with:** `QT_QPA_PLATFORM=offscreen python -m pytest -q` (offscreen so Qt tests need no display).
- **Commits:** plain messages; the product name "Claude Code" is fine in messages; **never** add `Co-Authored-By`/`Generated with` or any AI-authorship trailer.
- **Threshold colors** (used in UI + badge): `< 60%` `#3daee9` (normal), `60–85%` `#f67400` (warning), `≥ 85%` `#da4453` (critical).

## File Structure

```
pyproject.toml                         # package metadata + pytest config
README.md
src/ai_usage_kde/
  __init__.py                          # version
  __main__.py                          # python -m ai_usage_kde -> main.main()
  main.py                              # QApplication bootstrap, QML load, tray wiring
  core/
    __init__.py
    model.py                           # Qt-free dataclasses + threshold helper
    pricing.py                         # (under usage/, see below)
    auth.py                            # token discovery + refresh (Qt-free)
    config.py                          # QSettings wrapper + autostart .desktop
    controller.py                      # QObject bridge to QML (Qt)
    tray.py                            # QSystemTrayIcon + badge painter (Qt)
    http.py                            # tiny injectable http_get (Qt-free)
  providers/
    __init__.py
    base.py                            # Provider protocol + ProviderUsage builders
    claude.py                          # oauth/usage -> ProviderUsage (Qt-free)
    codex.py                           # wham/usage  -> ProviderUsage (Qt-free)
  usage/
    __init__.py
    pricing.py                         # model price table + cost()
    local_claude.py                    # ~/.claude/projects parser + cache (Qt-free)
  qml/
    Main.qml  ProviderSection.qml  UsageBar.qml  LocalBlock.qml  Settings.qml
  resources/
    claude.svg  codex.svg  app-icon.svg
tests/
  conftest.py
  fixtures/  (claude_usage.json, codex_usage.json, claude_credentials.json,
              codex_auth.json, transcript_sample.jsonl)
  test_model.py test_pricing.py test_local_claude.py test_auth.py
  test_claude_provider.py test_codex_provider.py test_config.py
  test_controller.py test_tray.py
```

---

## Task 0: Environment & scaffolding

**Files:**
- Create: `pyproject.toml`, `src/ai_usage_kde/__init__.py`, `tests/conftest.py`, `README.md`

- [ ] **Step 1: Install system PySide6 (requires the user — needs sudo)**

This must use the *system* package so PySide6 links the same Qt 6.11.1 that owns the Kirigami / `org.kde.desktop` QML modules. A pip/venv PySide6 bundles its own Qt and will NOT find them.

Ask the user to run (or run via the session `!` prefix):
```bash
sudo pacman -S --needed pyside6 pyside6-tools
```
Expected: `pyside6 6.11.1` installed.

- [ ] **Step 2: Verify the toolchain**

Run:
```bash
QT_QPA_PLATFORM=offscreen python3 -c "import PySide6,PySide6.QtCore,PySide6.QtQuick; from PySide6 import QtWidgets; print('PySide6', PySide6.__version__)"
```
Expected: prints `PySide6 6.11.1` with no import error.

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "ai-usage-kde"
version = "0.1.0"
description = "KDE Plasma system-tray usage tracker for Claude Code and Codex"
requires-python = ">=3.11"
# PySide6 is provided by the system package (pacman), intentionally NOT a pip dep.
dependencies = []

[project.scripts]
ai-usage-kde = "ai_usage_kde.main:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
ai_usage_kde = ["qml/*.qml", "resources/*.svg"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 4: Create package marker + version**

`src/ai_usage_kde/__init__.py`:
```python
"""ai-usage-kde: KDE tray usage tracker for Claude Code and Codex."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Create `tests/conftest.py`**

```python
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
```

- [ ] **Step 6: Create `README.md` (brief)**

```markdown
# ai-usage-kde

A native KDE Plasma system-tray tracker for Claude Code and Codex subscription
usage: 5-hour and 7-day window utilization, plan/credits, and a local Claude
token/cost breakdown.

## Requirements
- KDE Plasma 6, Qt 6.11, system `pyside6` package (`sudo pacman -S pyside6`).

## Run
    QT_QUICK_CONTROLS_STYLE=org.kde.desktop python -m ai_usage_kde

## Develop / test
    QT_QPA_PLATFORM=offscreen python -m pytest
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/ai_usage_kde/__init__.py tests/conftest.py README.md
git commit -m "chore: scaffold ai-usage-kde package and pytest setup"
```

---

## Task 1: Data model (`core/model.py`)

**Files:**
- Create: `src/ai_usage_kde/core/model.py`, `src/ai_usage_kde/core/__init__.py`
- Test: `tests/test_model.py`

- [ ] **Step 1: Write the failing test**

`tests/test_model.py`:
```python
from datetime import datetime, timezone

from ai_usage_kde.core.model import (
    UsageWindow, Credits, ProviderUsage, ProviderStatus, threshold_color,
)


def test_threshold_color_bands():
    assert threshold_color(0) == "#3daee9"
    assert threshold_color(59.9) == "#3daee9"
    assert threshold_color(60) == "#f67400"
    assert threshold_color(84.9) == "#f67400"
    assert threshold_color(85) == "#da4453"
    assert threshold_color(150) == "#da4453"


def test_provider_usage_session_percent_picks_session_window():
    w_session = UsageWindow(caption="Session · 5h", kind="session", used_percent=42.0,
                            resets_at=datetime(2026, 5, 30, tzinfo=timezone.utc))
    w_week = UsageWindow(caption="Weekly · 7d", kind="weekly", used_percent=18.0, resets_at=None)
    p = ProviderUsage(provider_id="claude", display_name="Claude Code", icon="claude.svg",
                      plan="Max 20x", status=ProviderStatus.OK, error_message=None,
                      windows=[w_session, w_week], credits=None, last_updated=None)
    assert p.session_percent() == 42.0


def test_provider_usage_session_percent_none_when_no_session():
    p = ProviderUsage(provider_id="codex", display_name="Codex", icon="codex.svg",
                      plan=None, status=ProviderStatus.UNAUTHENTICATED, error_message=None,
                      windows=[], credits=None, last_updated=None)
    assert p.session_percent() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_model.py -q`
Expected: FAIL (`ModuleNotFoundError: ai_usage_kde.core.model`).

- [ ] **Step 3: Write minimal implementation**

`src/ai_usage_kde/core/__init__.py`:
```python
```
(empty file)

`src/ai_usage_kde/core/model.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ProviderStatus(str, Enum):
    OK = "ok"
    UNAUTHENTICATED = "unauthenticated"
    ERROR = "error"
    STALE = "stale"


def threshold_color(percent: float) -> str:
    """Breeze color band for a utilization percent."""
    if percent >= 85:
        return "#da4453"  # critical
    if percent >= 60:
        return "#f67400"  # warning
    return "#3daee9"      # normal


@dataclass
class UsageWindow:
    caption: str
    kind: str               # "session" | "weekly" | "weekly_opus" | "weekly_sonnet" | "code_review"
    used_percent: float
    resets_at: Optional[datetime]


@dataclass
class Credits:
    used: float
    cap: float
    currency: str = "USD"


@dataclass
class ProviderUsage:
    provider_id: str
    display_name: str
    icon: str
    plan: Optional[str]
    status: ProviderStatus
    error_message: Optional[str]
    windows: list[UsageWindow] = field(default_factory=list)
    credits: Optional[Credits] = None
    last_updated: Optional[datetime] = None

    def session_percent(self) -> Optional[float]:
        for w in self.windows:
            if w.kind == "session":
                return w.used_percent
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_model.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai_usage_kde/core/__init__.py src/ai_usage_kde/core/model.py tests/test_model.py
git commit -m "feat: add usage data model and threshold color helper"
```

---

## Task 2: Pricing table + cost (`usage/pricing.py`)

**Files:**
- Create: `src/ai_usage_kde/usage/__init__.py`, `src/ai_usage_kde/usage/pricing.py`
- Test: `tests/test_pricing.py`

- [ ] **Step 1: Write the failing test**

`tests/test_pricing.py`:
```python
import pytest

from ai_usage_kde.usage.pricing import cost_usd, model_family


@pytest.mark.parametrize("name,family", [
    ("claude-opus-4-7", "opus"),
    ("claude-sonnet-4-5", "sonnet"),
    ("claude-3-5-haiku-20241022", "haiku"),
    ("<synthetic>", None),
    ("something-unknown", None),
])
def test_model_family(name, family):
    assert model_family(name) == family


def test_cost_opus_known_values():
    # opus: input 15, output 75, cache_write 18.75, cache_read 1.50 per 1e6 tokens
    c = cost_usd("claude-opus-4-7",
                 input_tokens=1_000_000, output_tokens=1_000_000,
                 cache_creation_input_tokens=1_000_000, cache_read_input_tokens=1_000_000)
    assert c == pytest.approx(15 + 75 + 18.75 + 1.50, rel=1e-9)


def test_cost_unknown_model_is_zero():
    assert cost_usd("<synthetic>", input_tokens=10, output_tokens=10,
                    cache_creation_input_tokens=0, cache_read_input_tokens=0) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pricing.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/ai_usage_kde/usage/__init__.py`:
```python
```
(empty file)

`src/ai_usage_kde/usage/pricing.py`:
```python
from __future__ import annotations

from typing import Optional

# USD per 1,000,000 tokens. Public Anthropic API list prices (subscription users
# don't actually pay these — used only for an "API-equivalent" estimate).
# cache_write = 1.25x input, cache_read = 0.1x input (Anthropic's cache pricing).
_PRICES = {
    "opus":   {"input": 15.0, "output": 75.0, "cache_write": 18.75, "cache_read": 1.50},
    "sonnet": {"input": 3.0,  "output": 15.0, "cache_write": 3.75,  "cache_read": 0.30},
    "haiku":  {"input": 1.0,  "output": 5.0,  "cache_write": 1.25,  "cache_read": 0.10},
}


def model_family(model: str) -> Optional[str]:
    m = (model or "").lower()
    for fam in ("opus", "sonnet", "haiku"):
        if fam in m:
            return fam
    return None


def cost_usd(model: str, *, input_tokens: int, output_tokens: int,
             cache_creation_input_tokens: int, cache_read_input_tokens: int) -> float:
    fam = model_family(model)
    if fam is None:
        return 0.0
    p = _PRICES[fam]
    million = 1_000_000.0
    return (
        input_tokens / million * p["input"]
        + output_tokens / million * p["output"]
        + cache_creation_input_tokens / million * p["cache_write"]
        + cache_read_input_tokens / million * p["cache_read"]
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pricing.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai_usage_kde/usage/__init__.py src/ai_usage_kde/usage/pricing.py tests/test_pricing.py
git commit -m "feat: add per-model pricing table and cost estimate"
```

---

## Task 3: Local Claude parser (`usage/local_claude.py`)

Parses `~/.claude/projects/**/*.jsonl`. Each assistant line looks like:
`{"type":"assistant","timestamp":"2026-05-30T...Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":..,"cache_creation_input_tokens":..,"cache_read_input_tokens":..,"output_tokens":..}}}`.

**Files:**
- Create: `src/ai_usage_kde/usage/local_claude.py`
- Test: `tests/test_local_claude.py`, `tests/fixtures/transcript_sample.jsonl`

- [ ] **Step 1: Write the failing test + fixture**

`tests/fixtures/transcript_sample.jsonl` (exact content):
```
{"type":"user","timestamp":"2026-05-30T10:00:00.000Z","message":{"role":"user","content":"hi"}}
{"type":"assistant","timestamp":"2026-05-30T10:00:01.000Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":1000,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":1000}}}
{"type":"assistant","timestamp":"2026-05-30T11:00:00.000Z","message":{"model":"claude-sonnet-4-5","usage":{"input_tokens":1000000,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":0}}}
{"type":"assistant","timestamp":"2026-05-29T09:00:00.000Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":500,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":500}}}
{"type":"summary","summary":"noise line with no usage"}
```

`tests/test_local_claude.py`:
```python
from datetime import date

from conftest import fixture
from ai_usage_kde.usage.local_claude import aggregate_files


def test_aggregate_today_tokens_and_cost():
    today = date(2026, 5, 30)
    res = aggregate_files([fixture("transcript_sample.jsonl")], today=today)
    # today's assistant lines: opus(1000 in,1000 out) + sonnet(1e6 in)
    assert res.today_tokens == 1000 + 1000 + 1_000_000
    # cost: opus (1000/1e6*15 + 1000/1e6*75) + sonnet (1e6/1e6*3) = 0.015+0.075+3.0
    assert round(res.today_cost_usd, 6) == round(0.015 + 0.075 + 3.0, 6)


def test_model_split_by_tokens_today():
    today = date(2026, 5, 30)
    res = aggregate_files([fixture("transcript_sample.jsonl")], today=today)
    # opus tokens today = 2000, sonnet = 1_000_000 -> sonnet dominates
    assert round(res.model_split["sonnet"], 4) == round(1_000_000 / 1_002_000, 4)
    assert round(res.model_split["opus"], 4) == round(2_000 / 1_002_000, 4)


def test_last7days_has_two_dated_buckets():
    today = date(2026, 5, 30)
    res = aggregate_files([fixture("transcript_sample.jsonl")], today=today)
    by_date = {d.date: d for d in res.last7days}
    assert by_date[date(2026, 5, 30)].tokens == 1_002_000
    assert by_date[date(2026, 5, 29)].tokens == 1000  # opus 500 in + 500 out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_local_claude.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/ai_usage_kde/usage/local_claude.py`:
```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from .pricing import cost_usd, model_family


@dataclass
class DayBucket:
    date: date
    tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class LocalClaudeUsage:
    today_tokens: int = 0
    today_cost_usd: float = 0.0
    model_split: dict[str, float] = field(default_factory=dict)   # family -> fraction of today's tokens
    last7days: list[DayBucket] = field(default_factory=list)


def _parse_ts(line_obj: dict) -> Optional[date]:
    ts = line_obj.get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def aggregate_files(paths: Iterable[Path], *, today: date) -> LocalClaudeUsage:
    cutoff = today - timedelta(days=6)  # 7-day window inclusive of today
    day_tokens: dict[date, int] = {}
    day_cost: dict[date, float] = {}
    today_family_tokens: dict[str, int] = {}

    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw or '"usage"' not in raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    msg = obj.get("message") or {}
                    usage = msg.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    d = _parse_ts(obj)
                    if d is None or d < cutoff or d > today:
                        continue
                    inp = int(usage.get("input_tokens", 0) or 0)
                    out = int(usage.get("output_tokens", 0) or 0)
                    cw = int(usage.get("cache_creation_input_tokens", 0) or 0)
                    cr = int(usage.get("cache_read_input_tokens", 0) or 0)
                    total = inp + out + cw + cr
                    model = msg.get("model", "")
                    c = cost_usd(model, input_tokens=inp, output_tokens=out,
                                 cache_creation_input_tokens=cw, cache_read_input_tokens=cr)
                    day_tokens[d] = day_tokens.get(d, 0) + total
                    day_cost[d] = day_cost.get(d, 0.0) + c
                    if d == today:
                        fam = model_family(model) or "other"
                        today_family_tokens[fam] = today_family_tokens.get(fam, 0) + total
        except (OSError, UnicodeDecodeError):
            continue

    today_tokens = day_tokens.get(today, 0)
    split = {}
    if today_tokens > 0:
        split = {fam: n / today_tokens for fam, n in today_family_tokens.items()}

    last7 = [DayBucket(date=cutoff + timedelta(days=i),
                       tokens=day_tokens.get(cutoff + timedelta(days=i), 0),
                       cost_usd=day_cost.get(cutoff + timedelta(days=i), 0.0))
             for i in range(7)]

    return LocalClaudeUsage(
        today_tokens=today_tokens,
        today_cost_usd=day_cost.get(today, 0.0),
        model_split=split,
        last7days=last7,
    )


def claude_projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def find_transcripts(root: Optional[Path] = None) -> list[Path]:
    root = root or claude_projects_dir()
    if not root.exists():
        return []
    return sorted(root.glob("**/*.jsonl"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_local_claude.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai_usage_kde/usage/local_claude.py tests/test_local_claude.py tests/fixtures/transcript_sample.jsonl
git commit -m "feat: parse local Claude transcripts into token/cost aggregates"
```

> Note: incremental mtime/size caching is added in Task 8 (controller) where it is wired; the pure parser stays stateless for testability.

---

## Task 4: HTTP helper + Auth (`core/http.py`, `core/auth.py`)

**Files:**
- Create: `src/ai_usage_kde/core/http.py`, `src/ai_usage_kde/core/auth.py`
- Test: `tests/test_auth.py`, `tests/fixtures/claude_credentials.json`, `tests/fixtures/codex_auth.json`

- [ ] **Step 1: Write the failing test + fixtures**

`tests/fixtures/claude_credentials.json`:
```json
{"claudeAiOauth":{"accessToken":"acc-123","refreshToken":"ref-456","expiresAt":4102444800000,"scopes":["user"],"subscriptionType":"max","rateLimitTier":"default_max_20x"}}
```

`tests/fixtures/codex_auth.json`:
```json
{"tokens":{"access_token":"cx-acc-1","refresh_token":"cx-ref-1","id_token":"cx-id-1","account_id":"acct-uuid-1"}}
```

`tests/test_auth.py`:
```python
import time

from conftest import fixture
from ai_usage_kde.core.auth import (
    ClaudeCredentials, CodexCredentials, load_claude_credentials, load_codex_credentials,
)


def test_load_claude_credentials_reads_fields():
    c = load_claude_credentials(path=fixture("claude_credentials.json"))
    assert isinstance(c, ClaudeCredentials)
    assert c.access_token == "acc-123"
    assert c.refresh_token == "ref-456"
    assert c.subscription_type == "max"
    assert c.is_expired(now_ms=0) is False  # expiresAt is far future


def test_claude_credentials_expiry_detection():
    c = ClaudeCredentials(access_token="a", refresh_token="r", expires_at_ms=1000,
                          subscription_type="max", rate_limit_tier="x")
    # expired if now >= expires - 5 min skew
    assert c.is_expired(now_ms=1000) is True
    assert c.is_expired(now_ms=0) is True          # within 5-min skew of 1000ms
    assert c.is_expired(now_ms=-10_000_000) is False


def test_load_claude_credentials_missing_returns_none(tmp_path):
    assert load_claude_credentials(path=tmp_path / "nope.json") is None


def test_load_codex_credentials_reads_nested_tokens():
    c = load_codex_credentials(path=fixture("codex_auth.json"))
    assert isinstance(c, CodexCredentials)
    assert c.access_token == "cx-acc-1"
    assert c.account_id == "acct-uuid-1"


def test_load_codex_credentials_missing_returns_none(tmp_path):
    assert load_codex_credentials(path=tmp_path / "nope.json") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/ai_usage_kde/core/http.py`:
```python
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class HttpError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def http_get(url: str, headers: dict[str, str], timeout: float = 15.0) -> HttpResponse:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(status=resp.status, body=resp.read(),
                                headers={k.lower(): v for k, v in resp.headers.items()})
    except urllib.error.HTTPError as e:
        return HttpResponse(status=e.code, body=e.read() or b"",
                            headers={k.lower(): v for k, v in (e.headers or {}).items()})


def http_post_form(url: str, data: dict[str, str], headers: dict[str, str],
                   timeout: float = 15.0) -> HttpResponse:
    payload = json.dumps(data).encode("utf-8")
    h = {"Content-Type": "application/json", **headers}
    req = urllib.request.Request(url, data=payload, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(status=resp.status, body=resp.read(),
                                headers={k.lower(): v for k, v in resp.headers.items()})
    except urllib.error.HTTPError as e:
        return HttpResponse(status=e.code, body=e.read() or b"", headers={})
```

`src/ai_usage_kde/core/auth.py`:
```python
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .http import http_post_form, HttpResponse

_FIVE_MIN_MS = 5 * 60 * 1000


@dataclass
class ClaudeCredentials:
    access_token: str
    refresh_token: str
    expires_at_ms: int
    subscription_type: str
    rate_limit_tier: str

    def is_expired(self, now_ms: Optional[int] = None) -> bool:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        return now >= (self.expires_at_ms - _FIVE_MIN_MS)


@dataclass
class CodexCredentials:
    access_token: str
    refresh_token: str
    id_token: str
    account_id: str


def claude_credentials_path() -> Path:
    return Path.home() / ".claude" / ".credentials.json"


def load_claude_credentials(path: Optional[Path] = None) -> Optional[ClaudeCredentials]:
    # env override first (matches Claude Code behavior)
    env_tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    p = path or claude_credentials_path()
    if env_tok and not path:
        return ClaudeCredentials(access_token=env_tok, refresh_token="",
                                 expires_at_ms=2**62, subscription_type="", rate_limit_tier="")
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        o = data.get("claudeAiOauth") or {}
        if not o.get("accessToken"):
            return None
        return ClaudeCredentials(
            access_token=o["accessToken"],
            refresh_token=o.get("refreshToken", ""),
            expires_at_ms=int(o.get("expiresAt", 0)),
            subscription_type=o.get("subscriptionType", ""),
            rate_limit_tier=o.get("rateLimitTier", ""),
        )
    except (OSError, ValueError, KeyError):
        return None


def codex_auth_candidates() -> list[Path]:
    paths = []
    home = Path.home()
    if os.environ.get("CODEX_HOME"):
        paths.append(Path(os.environ["CODEX_HOME"]) / "auth.json")
    paths.append(home / ".config" / "codex" / "auth.json")
    paths.append(home / ".codex" / "auth.json")
    return paths


def load_codex_credentials(path: Optional[Path] = None) -> Optional[CodexCredentials]:
    candidates = [path] if path else codex_auth_candidates()
    for p in candidates:
        if p and p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                t = data.get("tokens") or {}
                if not t.get("access_token"):
                    continue
                return CodexCredentials(
                    access_token=t["access_token"],
                    refresh_token=t.get("refresh_token", ""),
                    id_token=t.get("id_token", ""),
                    account_id=t.get("account_id", ""),
                )
            except (OSError, ValueError, KeyError):
                continue
    return None


CLAUDE_REFRESH_URL = "https://console.anthropic.com/v1/oauth/token"
CLAUDE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # public Claude Code OAuth client id


def refresh_claude_token(creds: ClaudeCredentials,
                         poster: Callable[..., HttpResponse] = http_post_form) -> Optional[str]:
    """Returns a new access token or None on failure. Persisting is the caller's job."""
    if not creds.refresh_token:
        return None
    resp = poster(CLAUDE_REFRESH_URL, {
        "grant_type": "refresh_token",
        "refresh_token": creds.refresh_token,
        "client_id": CLAUDE_CLIENT_ID,
    }, {"Accept": "application/json"})
    if resp.status != 200:
        return None
    try:
        return resp.json().get("access_token")
    except ValueError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_auth.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai_usage_kde/core/http.py src/ai_usage_kde/core/auth.py tests/test_auth.py tests/fixtures/claude_credentials.json tests/fixtures/codex_auth.json
git commit -m "feat: add http helper and Claude/Codex credential loading + refresh"
```

> Note: `CLAUDE_REFRESH_URL`/`CLAUDE_CLIENT_ID` must be verified against a live Claude Code refresh during Task 11 manual testing; they are isolated here so a correction touches one place.

---

## Task 5: Provider base + Claude provider (`providers/base.py`, `providers/claude.py`)

**Files:**
- Create: `src/ai_usage_kde/providers/__init__.py`, `base.py`, `claude.py`
- Test: `tests/test_claude_provider.py`, `tests/fixtures/claude_usage.json`

- [ ] **Step 1: Write the failing test + fixture**

`tests/fixtures/claude_usage.json` (shape from openusage `plugins/claude/plugin.js`):
```json
{"five_hour":{"utilization":42,"resets_at":"2026-05-30T16:00:00Z"},"seven_day":{"utilization":18,"resets_at":"2026-06-02T03:00:00Z"},"seven_day_omelette":{"utilization":55,"resets_at":"2026-06-02T03:00:00Z"},"extra_usage":{"is_enabled":true,"used_credits":3.2,"monthly_limit":50}}
```

`tests/test_claude_provider.py`:
```python
import json

from conftest import fixture
from ai_usage_kde.core.http import HttpResponse
from ai_usage_kde.core.model import ProviderStatus
from ai_usage_kde.providers.claude import ClaudeProvider


def _fake_getter(status=200, body=None):
    payload = json.dumps(body if body is not None
                         else json.loads(fixture("claude_usage.json").read_text())).encode()
    captured = {}

    def getter(url, headers, timeout=15.0):
        captured["url"] = url
        captured["headers"] = headers
        return HttpResponse(status=status, body=payload, headers={})
    getter.captured = captured
    return getter


def test_claude_fetch_maps_windows_and_credits():
    p = ClaudeProvider(creds=_DummyCreds(), getter=_fake_getter())
    usage = p.fetch()
    assert usage.status == ProviderStatus.OK
    kinds = {w.kind: w.used_percent for w in usage.windows}
    assert kinds["session"] == 42
    assert kinds["weekly"] == 18
    assert kinds["weekly_opus"] == 55
    assert usage.credits.used == 3.2 and usage.credits.cap == 50


def test_claude_fetch_sets_required_headers():
    getter = _fake_getter()
    ClaudeProvider(creds=_DummyCreds(), getter=getter).fetch()
    h = getter.captured["headers"]
    assert h["Authorization"] == "Bearer acc-123"
    assert h["anthropic-beta"] == "oauth-2025-04-20"
    assert h["User-Agent"].startswith("claude-code/")


def test_claude_fetch_401_is_error_status():
    p = ClaudeProvider(creds=_DummyCreds(), getter=_fake_getter(status=401))
    usage = p.fetch()
    assert usage.status in (ProviderStatus.ERROR, ProviderStatus.UNAUTHENTICATED)


class _DummyCreds:
    access_token = "acc-123"
    refresh_token = "ref"
    subscription_type = "max"
    rate_limit_tier = "default_max_20x"
    def is_expired(self, now_ms=None):
        return False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_claude_provider.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/ai_usage_kde/providers/__init__.py`:
```python
```
(empty file)

`src/ai_usage_kde/providers/base.py`:
```python
from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol

from ..core.model import ProviderUsage, ProviderStatus, UsageWindow


def parse_reset(value) -> Optional[datetime]:
    """Accept ISO 'resets_at' strings (with Z) -> aware datetime, else None."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Provider(Protocol):
    id: str
    display_name: str
    def is_configured(self) -> bool: ...
    def fetch(self) -> ProviderUsage: ...


def unauthenticated(provider_id: str, display_name: str, icon: str, hint: str) -> ProviderUsage:
    return ProviderUsage(provider_id=provider_id, display_name=display_name, icon=icon,
                         plan=None, status=ProviderStatus.UNAUTHENTICATED,
                         error_message=hint, windows=[], credits=None, last_updated=None)


def errored(provider_id: str, display_name: str, icon: str, message: str) -> ProviderUsage:
    return ProviderUsage(provider_id=provider_id, display_name=display_name, icon=icon,
                         plan=None, status=ProviderStatus.ERROR,
                         error_message=message, windows=[], credits=None, last_updated=None)
```

`src/ai_usage_kde/providers/claude.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from ..core.http import http_get, HttpResponse
from ..core.model import Credits, ProviderStatus, ProviderUsage, UsageWindow
from .base import errored, parse_reset, unauthenticated

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
# Track a current Claude Code version; a real UA is required to avoid 429 buckets.
CLAUDE_CODE_VERSION = "2.1.69"
ICON = "claude.svg"
DISPLAY = "Claude Code"
PROVIDER_ID = "claude"

_PLAN_LABELS = {"default_max_20x": "Max 20x", "default_max_5x": "Max 5x", "default_pro": "Pro"}


def _plan_label(creds) -> Optional[str]:
    tier = getattr(creds, "rate_limit_tier", "") or ""
    if tier in _PLAN_LABELS:
        return _PLAN_LABELS[tier]
    sub = getattr(creds, "subscription_type", "") or ""
    return sub.capitalize() if sub else None


class ClaudeProvider:
    id = PROVIDER_ID
    display_name = DISPLAY

    def __init__(self, creds=None, getter: Callable[..., HttpResponse] = http_get):
        self._creds = creds
        self._get = getter

    def is_configured(self) -> bool:
        return self._creds is not None

    def fetch(self) -> ProviderUsage:
        if self._creds is None:
            return unauthenticated(PROVIDER_ID, DISPLAY, ICON,
                                   "Not signed in — log in via Claude Code.")
        headers = {
            "Authorization": f"Bearer {self._creds.access_token.strip()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": f"claude-code/{CLAUDE_CODE_VERSION}",
        }
        resp = self._get(USAGE_URL, headers=headers)
        if resp.status in (401, 403):
            return errored(PROVIDER_ID, DISPLAY, ICON,
                           "Re-authenticate in Claude Code.")
        if resp.status != 200:
            return errored(PROVIDER_ID, DISPLAY, ICON, f"Usage request failed ({resp.status}).")
        try:
            data = resp.json()
        except ValueError:
            return errored(PROVIDER_ID, DISPLAY, ICON, "Couldn't read usage.")
        return self._map(data)

    def _map(self, data: dict) -> ProviderUsage:
        windows: list[UsageWindow] = []

        def add(key, kind, caption):
            w = data.get(key)
            if isinstance(w, dict) and w.get("utilization") is not None:
                windows.append(UsageWindow(caption=caption, kind=kind,
                                           used_percent=float(w["utilization"]),
                                           resets_at=parse_reset(w.get("resets_at"))))

        add("five_hour", "session", "Session · 5h")
        add("seven_day", "weekly", "Weekly · 7d")
        add("seven_day_omelette", "weekly_opus", "Weekly · Opus")

        credits = None
        ex = data.get("extra_usage")
        if isinstance(ex, dict) and ex.get("is_enabled"):
            credits = Credits(used=float(ex.get("used_credits", 0)),
                              cap=float(ex.get("monthly_limit", 0)), currency="USD")

        return ProviderUsage(
            provider_id=PROVIDER_ID, display_name=DISPLAY, icon=ICON,
            plan=_plan_label(self._creds), status=ProviderStatus.OK, error_message=None,
            windows=windows, credits=credits, last_updated=datetime.now(timezone.utc),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_claude_provider.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai_usage_kde/providers/__init__.py src/ai_usage_kde/providers/base.py src/ai_usage_kde/providers/claude.py tests/test_claude_provider.py tests/fixtures/claude_usage.json
git commit -m "feat: add Claude provider mapping oauth/usage to UsageWindows"
```

---

## Task 6: Codex provider (`providers/codex.py`)

**Files:**
- Create: `src/ai_usage_kde/providers/codex.py`
- Test: `tests/test_codex_provider.py`, `tests/fixtures/codex_usage.json`

- [ ] **Step 1: Write the failing test + fixture**

`tests/fixtures/codex_usage.json` (shape from openusage `plugins/codex/plugin.js`):
```json
{"rate_limit":{"primary_window":{"used_percent":67,"reset_at":"2026-05-30T15:00:00Z"},"secondary_window":{"used_percent":31,"reset_at":"2026-06-02T00:00:00Z"}},"plan_type":"plus","credits":{"balance":12.5,"has_credits":true},"code_review_rate_limit":{"primary_window":{"used_percent":10,"reset_at":"2026-06-02T00:00:00Z"}}}
```

`tests/test_codex_provider.py`:
```python
import json

from conftest import fixture
from ai_usage_kde.core.http import HttpResponse
from ai_usage_kde.core.model import ProviderStatus
from ai_usage_kde.providers.codex import CodexProvider


def _getter(status=200):
    payload = fixture("codex_usage.json").read_text().encode()
    captured = {}

    def g(url, headers, timeout=15.0):
        captured["headers"] = headers
        return HttpResponse(status=status, body=payload, headers={})
    g.captured = captured
    return g


class _Creds:
    access_token = "cx-acc-1"
    account_id = "acct-1"


def test_codex_unconfigured_is_unauthenticated():
    u = CodexProvider(creds=None).fetch()
    assert u.status == ProviderStatus.UNAUTHENTICATED


def test_codex_fetch_maps_windows_plan_credits():
    u = CodexProvider(creds=_Creds(), getter=_getter()).fetch()
    kinds = {w.kind: w.used_percent for w in u.windows}
    assert kinds["session"] == 67
    assert kinds["weekly"] == 31
    assert kinds["code_review"] == 10
    assert u.plan == "Plus"
    assert u.credits.used == 12.5


def test_codex_sets_account_header():
    g = _getter()
    CodexProvider(creds=_Creds(), getter=g).fetch()
    assert g.captured["headers"]["Authorization"] == "Bearer cx-acc-1"
    assert g.captured["headers"]["ChatGPT-Account-Id"] == "acct-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_codex_provider.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/ai_usage_kde/providers/codex.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from ..core.http import http_get, HttpResponse
from ..core.model import Credits, ProviderStatus, ProviderUsage, UsageWindow
from .base import errored, parse_reset, unauthenticated

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
ICON = "codex.svg"
DISPLAY = "Codex"
PROVIDER_ID = "codex"


def _plan_label(plan_type: Optional[str]) -> Optional[str]:
    if not plan_type:
        return None
    return {"plus": "Plus", "pro": "Pro", "team": "Team", "free": "Free"}.get(
        plan_type.lower(), plan_type.capitalize())


class CodexProvider:
    id = PROVIDER_ID
    display_name = DISPLAY

    def __init__(self, creds=None, getter: Callable[..., HttpResponse] = http_get):
        self._creds = creds
        self._get = getter

    def is_configured(self) -> bool:
        return self._creds is not None

    def fetch(self) -> ProviderUsage:
        if self._creds is None:
            return unauthenticated(PROVIDER_ID, DISPLAY, ICON,
                                   "Not signed in — log in via the Codex CLI.")
        headers = {
            "Authorization": f"Bearer {self._creds.access_token}",
            "Accept": "application/json",
            "User-Agent": "ai-usage-kde",
        }
        if getattr(self._creds, "account_id", ""):
            headers["ChatGPT-Account-Id"] = self._creds.account_id
        resp = self._get(USAGE_URL, headers=headers)
        if resp.status in (401, 403):
            return errored(PROVIDER_ID, DISPLAY, ICON, "Re-authenticate in the Codex CLI.")
        if resp.status != 200:
            return errored(PROVIDER_ID, DISPLAY, ICON, f"Usage request failed ({resp.status}).")
        try:
            data = resp.json()
        except ValueError:
            return errored(PROVIDER_ID, DISPLAY, ICON, "Couldn't read usage.")
        return self._map(data)

    def _map(self, data: dict) -> ProviderUsage:
        windows: list[UsageWindow] = []
        rl = data.get("rate_limit") or {}

        def add(window: dict, kind: str, caption: str):
            if isinstance(window, dict) and window.get("used_percent") is not None:
                windows.append(UsageWindow(caption=caption, kind=kind,
                                           used_percent=float(window["used_percent"]),
                                           resets_at=parse_reset(window.get("reset_at"))))

        add(rl.get("primary_window") or {}, "session", "Session · 5h")
        add(rl.get("secondary_window") or {}, "weekly", "Weekly · 7d")
        cr = (data.get("code_review_rate_limit") or {}).get("primary_window") or {}
        add(cr, "code_review", "Code review · 7d")

        credits = None
        c = data.get("credits")
        if isinstance(c, dict) and c.get("has_credits"):
            credits = Credits(used=float(c.get("balance", 0)), cap=0.0, currency="USD")

        return ProviderUsage(
            provider_id=PROVIDER_ID, display_name=DISPLAY, icon=ICON,
            plan=_plan_label(data.get("plan_type")), status=ProviderStatus.OK,
            error_message=None, windows=windows, credits=credits,
            last_updated=datetime.now(timezone.utc),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_codex_provider.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai_usage_kde/providers/codex.py tests/test_codex_provider.py tests/fixtures/codex_usage.json
git commit -m "feat: add Codex provider mapping wham/usage to UsageWindows"
```

---

## Task 7: Config + autostart (`core/config.py`)

**Files:**
- Create: `src/ai_usage_kde/core/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/ai_usage_kde/core/config.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai_usage_kde/core/config.py tests/test_config.py
git commit -m "feat: add QSettings config and autostart .desktop management"
```

---

## Task 8: Controller bridge (`core/controller.py`)

The `Controller` is a `QObject` exposed to QML. It refreshes providers off-thread,
caches local-Claude parsing by file `(size, mtime)`, exposes a JSON-able snapshot,
and computes the tray badge (max session %). Refresh is injectable for testing.

**Files:**
- Create: `src/ai_usage_kde/core/controller.py`
- Test: `tests/test_controller.py`

- [ ] **Step 1: Write the failing test**

`tests/test_controller.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_controller.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/ai_usage_kde/core/controller.py`:
```python
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot, Property, QThreadPool, QRunnable

from .model import ProviderUsage, ProviderStatus, threshold_color
from ..usage.local_claude import aggregate_files, LocalClaudeUsage


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def build_snapshot(usages: list[ProviderUsage], local: Optional[LocalClaudeUsage]) -> dict:
    providers = []
    for u in usages:
        providers.append({
            "provider_id": u.provider_id,
            "display_name": u.display_name,
            "icon": u.icon,
            "plan": u.plan,
            "status": u.status.value,
            "error_message": u.error_message,
            "last_updated": _iso(u.last_updated),
            "credits": (None if u.credits is None else
                        {"used": u.credits.used, "cap": u.credits.cap,
                         "currency": u.credits.currency}),
            "windows": [{
                "caption": w.caption, "kind": w.kind,
                "used_percent": w.used_percent,
                "color": threshold_color(w.used_percent),
                "resets_at": _iso(w.resets_at),
            } for w in u.windows],
        })
    local_d = None
    if local is not None:
        local_d = {
            "today_tokens": local.today_tokens,
            "today_cost_usd": local.today_cost_usd,
            "model_split": local.model_split,
            "last7days": [{"date": b.date.isoformat(), "tokens": b.tokens,
                           "cost_usd": b.cost_usd} for b in local.last7days],
        }
    return {"providers": providers, "local_claude": local_d}


class _FetchJob(QRunnable):
    def __init__(self, fn): super().__init__(); self._fn = fn
    def run(self): self._fn()


class Controller(QObject):
    snapshotChanged = Signal()
    badgeChanged = Signal()

    def __init__(self, providers, local_paths_fn: Callable[[], list[Path]],
                 today_fn: Callable[[], date] = date.today, parent=None):
        super().__init__(parent)
        self._providers = providers
        self._local_paths_fn = local_paths_fn
        self._today_fn = today_fn
        self._usages: list[ProviderUsage] = []
        self._local: Optional[LocalClaudeUsage] = None
        self._snapshot_json = "{}"
        self._pool = QThreadPool.globalInstance()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_async)

    # ---- exposed to QML ----
    @Property(str, notify=snapshotChanged)
    def snapshotJson(self) -> str:
        return self._snapshot_json

    @Slot()
    def refresh_async(self):
        self._pool.start(_FetchJob(self.refresh_blocking))

    # ---- core ----
    def refresh_blocking(self):
        usages = []
        for p in self._providers:
            try:
                usages.append(p.fetch())
            except Exception as exc:  # never let one provider kill refresh
                from .model import ProviderUsage as PU
                usages.append(PU(provider_id=getattr(p, "id", "?"),
                                 display_name=getattr(p, "display_name", "?"),
                                 icon="", plan=None, status=ProviderStatus.ERROR,
                                 error_message=str(exc), windows=[], credits=None,
                                 last_updated=None))
        self._usages = usages
        self._local = self._compute_local()
        self._snapshot_json = json.dumps(build_snapshot(self._usages, self._local))
        self.snapshotChanged.emit()
        self.badgeChanged.emit()

    def _compute_local(self) -> Optional[LocalClaudeUsage]:
        paths = self._local_paths_fn()
        if not paths:
            return None
        return aggregate_files(paths, today=self._today_fn())

    def badge_percent(self) -> int:
        best = 0.0
        for u in self._usages:
            sp = u.session_percent()
            if sp is not None:
                best = max(best, sp)
        return int(round(best))

    def badge_color(self) -> str:
        return threshold_color(self.badge_percent())

    def start(self, interval_seconds: int):
        self._timer.start(max(180, interval_seconds) * 1000)
        self.refresh_async()

    def stop(self):
        self._timer.stop()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_controller.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai_usage_kde/core/controller.py tests/test_controller.py
git commit -m "feat: add Controller bridge with off-thread refresh and snapshot"
```

---

## Task 9: Tray icon + badge painter (`core/tray.py`)

**Files:**
- Create: `src/ai_usage_kde/core/tray.py`
- Test: `tests/test_tray.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tray.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_tray.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/ai_usage_kde/core/tray.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_tray.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ai_usage_kde/core/tray.py tests/test_tray.py
git commit -m "feat: add system tray icon with dynamically painted percent badge"
```

---

## Task 10: QML UI (popup components)

All QML is verified manually in Task 11 (a running Plasma session). Keep each
component small and bound to `controller.snapshotJson` (parsed once in `Main.qml`).

**Files:**
- Create: `src/ai_usage_kde/qml/UsageBar.qml`, `LocalBlock.qml`, `ProviderSection.qml`, `Main.qml`, `Settings.qml`

- [ ] **Step 1: `UsageBar.qml`**

```qml
import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    property string caption: ""
    property real percent: 0
    property string color: "#3daee9"
    property string resetText: ""
    spacing: 2
    Layout.fillWidth: true

    RowLayout {
        Layout.fillWidth: true
        Text { text: root.caption; color: "#bdc3c7"; font.pixelSize: 11 }
        Item { Layout.fillWidth: true }
        Text { text: Math.round(root.percent) + "%"; color: root.color
               font.pixelSize: 11; font.bold: true }
    }
    Rectangle {
        Layout.fillWidth: true; height: 6; radius: 3; color: "#45494d"
        Rectangle {
            width: parent.width * Math.min(1, root.percent / 100)
            height: parent.height; radius: 3; color: root.color
            Behavior on width { NumberAnimation { duration: 250 } }
        }
    }
    Text {
        visible: root.resetText.length > 0
        text: root.resetText; color: "#7f8c8d"; font.pixelSize: 9
    }
}
```

- [ ] **Step 2: `LocalBlock.qml`**

```qml
import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property var local: null   // {today_tokens, today_cost_usd, model_split, last7days}
    visible: local !== null
    Layout.fillWidth: true
    radius: 7; color: "#222629"
    implicitHeight: col.implicitHeight + 16

    function fmtTokens(n) {
        if (n >= 1e6) return (n / 1e6).toFixed(2) + "M"
        if (n >= 1e3) return (n / 1e3).toFixed(1) + "k"
        return "" + n
    }
    function splitText() {
        if (!local || !local.model_split) return ""
        var parts = []
        for (var k in local.model_split)
            parts.push(k.charAt(0).toUpperCase() + k.slice(1) + " "
                       + Math.round(local.model_split[k] * 100) + "%")
        return parts.join(" · ")
    }

    ColumnLayout {
        id: col
        anchors.fill: parent; anchors.margins: 8; spacing: 4
        Text { text: "LOCAL · THIS MACHINE"; color: "#717a80"
               font.pixelSize: 8.5; font.letterSpacing: 0.5 }
        RowLayout {
            Layout.fillWidth: true
            Text { text: "Today"; color: "#bdc3c7"; font.pixelSize: 11 }
            Item { Layout.fillWidth: true }
            Text { text: root.local ? root.fmtTokens(root.local.today_tokens)
                         + " tok   ~$" + root.local.today_cost_usd.toFixed(2) : ""
                   color: "#fcfcfc"; font.pixelSize: 11; font.bold: true }
        }
        Text { text: root.splitText(); color: "#7f8c8d"; font.pixelSize: 10 }
        RowLayout {
            Layout.fillWidth: true; spacing: 2; Layout.topMargin: 4
            Repeater {
                model: root.local ? root.local.last7days : []
                Rectangle {
                    Layout.fillWidth: true
                    height: 20
                    color: "transparent"
                    Rectangle {
                        anchors.bottom: parent.bottom; width: parent.width; radius: 1
                        color: "#3a6c86"
                        property real maxTok: {
                            var m = 1
                            var d = root.local ? root.local.last7days : []
                            for (var i = 0; i < d.length; i++) m = Math.max(m, d[i].tokens)
                            return m
                        }
                        height: Math.max(2, 20 * (modelData.tokens / maxTok))
                    }
                }
            }
        }
    }
}
```

- [ ] **Step 3: `ProviderSection.qml`**

```qml
import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    property var provider: ({})
    property var local: null      // only for claude
    spacing: 6
    Layout.fillWidth: true

    RowLayout {
        Layout.fillWidth: true; spacing: 8
        Rectangle {
            width: 22; height: 22; radius: 6
            color: root.provider.provider_id === "claude" ? "#d97757" : "#10a37f"
            Text { anchors.centerIn: parent
                   text: root.provider.provider_id === "claude" ? "C" : "O"
                   color: "white"; font.bold: true; font.pixelSize: 12 }
        }
        Text { text: root.provider.display_name || ""; color: "#fcfcfc"
               font.pixelSize: 12.5; font.bold: true }
        Item { Layout.fillWidth: true }
        Text {
            visible: !!root.provider.plan
            text: root.provider.plan || ""; color: "#cfd6dc"; font.pixelSize: 9
            leftPadding: 7; rightPadding: 7; topPadding: 2; bottomPadding: 2
            background: Rectangle { radius: 9; color: "#3a3f44" }
        }
    }

    // status message when not OK
    Text {
        visible: root.provider.status && root.provider.status !== "ok"
        text: root.provider.error_message || ""
        color: "#f67400"; font.pixelSize: 10; Layout.fillWidth: true; wrapMode: Text.WordWrap
    }

    Repeater {
        model: root.provider.windows || []
        UsageBar {
            caption: modelData.caption
            percent: modelData.used_percent
            color: modelData.color
            resetText: {
                var t = modelData.resets_at ? "resets " + Qt.formatDateTime(
                          new Date(modelData.resets_at), "ddd hh:mm") : ""
                if (root.provider.credits && modelData.kind === "weekly")
                    t += (t ? " · " : "") + "extra $" + root.provider.credits.used.toFixed(2)
                         + (root.provider.credits.cap > 0 ? " / $" + root.provider.credits.cap : "")
                return t
            }
        }
    }

    LocalBlock { local: root.local }
}
```

- [ ] **Step 4: `Main.qml`**

```qml
import QtQuick
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: win
    width: 300
    height: content.implicitHeight + 24
    flags: Qt.Popup | Qt.FramelessWindowHint
    color: "#2a2e32"

    property var snapshot: ({ providers: [], local_claude: null })
    function reload() {
        try { snapshot = JSON.parse(controller.snapshotJson) }
        catch (e) { snapshot = ({ providers: [], local_claude: null }) }
    }
    Connections { target: controller; function onSnapshotChanged() { win.reload() } }
    Component.onCompleted: reload()

    Rectangle {
        anchors.fill: parent; color: "transparent"
        border.color: "#15181a"; radius: 11
        ColumnLayout {
            id: content
            anchors.fill: parent; anchors.margins: 12; spacing: 10

            RowLayout {
                Layout.fillWidth: true
                Text { text: "AI Usage"; color: "#fcfcfc"; font.pixelSize: 13; font.bold: true }
                Item { Layout.fillWidth: true }
                Text { text: "⟳"; color: "#7f8c8d"; font.pixelSize: 14
                       MouseArea { anchors.fill: parent; onClicked: controller.refresh_async() } }
                Text { text: "⚙"; color: "#7f8c8d"; font.pixelSize: 14
                       MouseArea { anchors.fill: parent; onClicked: settingsLoader.toggle() } }
            }

            Repeater {
                model: win.snapshot.providers
                ProviderSection {
                    provider: modelData
                    local: modelData.provider_id === "claude" ? win.snapshot.local_claude : null
                    Layout.fillWidth: true
                }
            }
        }
    }

    Loader {
        id: settingsLoader
        function toggle() { source = source == "" ? "Settings.qml" : "" }
    }
}
```

- [ ] **Step 5: `Settings.qml`**

```qml
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: root
    modal: true
    width: 260
    padding: 14
    anchors.centerIn: Overlay.overlay
    visible: true

    ColumnLayout {
        anchors.fill: parent; spacing: 10
        Label { text: "Settings"; font.bold: true }
        RowLayout {
            Layout.fillWidth: true
            Label { text: "Refresh (s)"; Layout.fillWidth: true }
            SpinBox { from: 180; to: 3600; stepSize: 60
                      value: controller.refreshSeconds
                      onValueModified: controller.setRefreshSeconds(value) }
        }
        CheckBox { text: "Show % badge on tray icon"
                   checked: controller.badgeEnabled
                   onToggled: controller.setBadgeEnabled(checked) }
        CheckBox { text: "Start automatically on login"
                   checked: controller.autostartEnabled
                   onToggled: controller.setAutostart(checked) }
    }
}
```

- [ ] **Step 6: Commit**

```bash
git add src/ai_usage_kde/qml/
git commit -m "feat: add QML popup UI (provider sections, usage bars, local block, settings)"
```

> Note: `Settings.qml` references `controller.refreshSeconds`, `badgeEnabled`,
> `autostartEnabled`, `setRefreshSeconds`, `setBadgeEnabled`, `setAutostart` —
> these `Property`/`Slot` members are added to `Controller` in Task 11 Step 1.

---

## Task 11: App bootstrap + wiring (`main.py`, `__main__.py`) + manual run

**Files:**
- Modify: `src/ai_usage_kde/core/controller.py` (add config-backed Q properties/slots)
- Create: `src/ai_usage_kde/main.py`, `src/ai_usage_kde/__main__.py`
- Create: `src/ai_usage_kde/resources/claude.svg`, `codex.svg`, `app-icon.svg`

- [ ] **Step 1: Extend `Controller` with config-backed members for Settings.qml**

Add to `Controller.__init__` (after `self._timer ...`):
```python
        from .config import Config
        self._config = Config()
```
Add these members to `Controller` (anywhere in the class body):
```python
    refreshSecondsChanged = Signal()
    badgeEnabledChanged = Signal()
    autostartChanged = Signal()

    @Property(int, notify=refreshSecondsChanged)
    def refreshSeconds(self):
        return self._config.refresh_seconds()

    @Slot(int)
    def setRefreshSeconds(self, value):
        self._config.set_refresh_seconds(value)
        self._timer.start(self._config.refresh_seconds() * 1000)
        self.refreshSecondsChanged.emit()

    @Property(bool, notify=badgeEnabledChanged)
    def badgeEnabled(self):
        return self._config.badge_enabled()

    @Slot(bool)
    def setBadgeEnabled(self, value):
        self._config.set_badge_enabled(value)
        self.badgeEnabledChanged.emit()
        self.badgeChanged.emit()

    @Property(bool, notify=autostartChanged)
    def autostartEnabled(self):
        return bool(self._config._s.value("autostart", False, type=bool))

    @Slot(bool)
    def setAutostart(self, value):
        self._config.set_autostart(value)
        self.autostartChanged.emit()
```

- [ ] **Step 2: Run the existing controller tests to confirm no regression**

Run: `python -m pytest tests/test_controller.py -q`
Expected: PASS (3 passed). (Construction now also builds a `Config()` with default QSettings — fine under offscreen.)

- [ ] **Step 3: Create minimal SVG resources**

`src/ai_usage_kde/resources/app-icon.svg`:
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#3daee9"/><text x="32" y="42" font-size="30" font-family="sans-serif" font-weight="bold" fill="#fff" text-anchor="middle">U</text></svg>
```
`src/ai_usage_kde/resources/claude.svg`:
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#d97757"/><text x="32" y="42" font-size="30" font-family="sans-serif" font-weight="bold" fill="#fff" text-anchor="middle">C</text></svg>
```
`src/ai_usage_kde/resources/codex.svg`:
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#10a37f"/><text x="32" y="42" font-size="30" font-family="sans-serif" font-weight="bold" fill="#fff" text-anchor="middle">O</text></svg>
```

- [ ] **Step 4: Create `main.py`**

```python
from __future__ import annotations

import os
import sys
from pathlib import Path

# Native Breeze look for QtQuick Controls before any Qt import that builds a style.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "org.kde.desktop")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QIcon, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtCore import QCoreApplication

from .core.auth import load_claude_credentials, load_codex_credentials
from .core.config import Config
from .core.controller import Controller
from .core.tray import Tray, render_badge_pixmap
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

    controller = Controller(providers=_build_providers(),
                            local_paths_fn=find_transcripts)

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", controller)
    engine.addImportPath(str(HERE / "qml"))
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        print("Failed to load QML", file=sys.stderr)
        return 1
    popup = engine.rootObjects()[0]

    def toggle_popup():
        if popup.isVisible():
            popup.hide()
        else:
            pos = tray.geometry()
            popup.setX(int(pos.x() + pos.width() / 2 - popup.width() / 2))
            popup.setY(int(pos.y() - popup.height() - 8) if pos.y() > 400
                       else int(pos.y() + pos.height() + 8))
            popup.show()
            popup.raise_()

    cfg = Config()
    app_icon = QIcon(str(HERE / "resources" / "app-icon.svg"))

    tray = Tray(on_toggle=toggle_popup,
                on_refresh=controller.refresh_async,
                on_settings=lambda: (toggle_popup()),
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
```

- [ ] **Step 5: Create `__main__.py`**

```python
from .main import main

raise SystemExit(main())
```

- [ ] **Step 6: Manual run — verify it launches and shows live data**

Run:
```bash
QT_QUICK_CONTROLS_STYLE=org.kde.desktop python -m ai_usage_kde
```
Expected, in a Plasma session:
- A tray icon appears (badge shows the highest session % once data loads).
- Left-click toggles the popup anchored at the tray icon.
- Claude section shows Session/Weekly bars with live percentages and the local
  block (today tokens + ~$). Codex shows "Not signed in" (no `~/.codex` here).
- Right-click → Refresh / Settings / Quit work.

If Claude shows "Re-authenticate", verify `CLAUDE_REFRESH_URL`/`CLAUDE_CLIENT_ID`
in `core/auth.py` against a current token, then re-run.

- [ ] **Step 7: Commit**

```bash
git add src/ai_usage_kde/main.py src/ai_usage_kde/__main__.py src/ai_usage_kde/resources/ src/ai_usage_kde/core/controller.py
git commit -m "feat: wire app bootstrap, tray badge updates and popup positioning"
```

---

## Task 12: Full test sweep + README finalize

- [ ] **Step 1: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 2: Document the manual verification result in README**

Append a "Status" section to `README.md` noting verified providers (Claude live,
Codex pending CLI login) and the run command.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: finalize README with run and verification notes"
```

---

## Self-Review (completed during planning)

- **Spec coverage:** tray app (T9/T11), Python/PySide6 + QML/Kirigami (T10/T11),
  layout A (T10), live usage Claude (T5) + Codex (T6), local Claude tokens (T3),
  thresholds (T1), tray badge max-session (T8/T9), 180s refresh + floor (T7/T8),
  autostart (T7/T11), error handling per status (T5/T6 + ProviderSection), config
  (T7), testing with fixtures (all). Codex local parsing intentionally deferred per spec.
- **Placeholder scan:** no TODO/TBD; every code step is complete; cross-task type
  names checked (`ProviderUsage`, `UsageWindow`, `ProviderStatus`, `Credits`,
  `LocalClaudeUsage`, `Config`, `Controller`, `render_badge_pixmap`).
- **Type consistency:** Settings.qml members are defined in T11 Step 1 (noted in T10).
  `aggregate_files(paths, today=...)` signature consistent across T3/T8.
- **Known impl-time risks (flagged in tasks):** exact Claude refresh URL/client id
  (T4/T11), Opus codename `seven_day_omelette` (T5). **Wayland popup placement (T11):**
  on Plasma Wayland a client cannot set absolute window coordinates, so the manual
  `setX/setY` anchoring won't work. Fallback for T11: drop manual positioning and show
  the popup centered (or use `Qt.Tool` + let the compositor place it); confirm which
  session type (`echo $XDG_SESSION_TYPE`) during the manual run and pick accordingly.
```
