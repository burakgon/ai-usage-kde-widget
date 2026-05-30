from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from .model import ProviderUsage, threshold_color
from ..usage.local_claude import LocalClaudeUsage


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


def collect_snapshot(providers=None, local_paths=None, today: Optional[date] = None) -> dict:
    """Build providers (Claude+Codex), fetch them, parse local Claude tokens, and
    return the snapshot dict. Injectable for tests; defaults hit the real sources."""
    from ..providers.claude import ClaudeProvider
    from ..providers.codex import CodexProvider
    from .auth import load_claude_credentials, load_codex_credentials
    from ..usage.local_claude import find_transcripts, aggregate_files

    if providers is None:
        providers = [
            ClaudeProvider(creds=load_claude_credentials()),
            CodexProvider(creds=load_codex_credentials()),
        ]
    usages = [p.fetch() for p in providers]
    if local_paths is None:
        local_paths = find_transcripts()
    local = aggregate_files(local_paths, today=today or date.today()) if local_paths else None
    return build_snapshot(usages, local)
