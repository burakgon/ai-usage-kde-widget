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
