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
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
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

    last7 = []
    for i in range(7):
        d = cutoff + timedelta(days=i)
        last7.append(DayBucket(date=d, tokens=day_tokens.get(d, 0),
                               cost_usd=day_cost.get(d, 0.0)))

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
