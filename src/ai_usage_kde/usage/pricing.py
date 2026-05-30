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
