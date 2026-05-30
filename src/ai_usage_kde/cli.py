from __future__ import annotations

import json

from .core.snapshot import collect_snapshot


def print_json() -> int:
    print(json.dumps(collect_snapshot()))
    return 0
