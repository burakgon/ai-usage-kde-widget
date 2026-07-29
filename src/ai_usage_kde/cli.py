from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from . import __version__
from .core.catalog import PROVIDER_IDS
from .core.snapshot import catalog_snapshot, collect_snapshot
from .core.update import check_for_update


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="ai-usage-kde",
        description="Read local AI CLI sessions and print subscription usage as JSON.",
    )
    result.add_argument("--json", action="store_true", help="Print JSON (the default).")
    result.add_argument(
        "--providers",
        metavar="IDS",
        help="Comma-separated tracked provider IDs.",
    )
    result.add_argument(
        "--catalog",
        action="store_true",
        help="Print the provider catalog without reading credentials or using the network.",
    )
    result.add_argument(
        "--check-update",
        action="store_true",
        help="Check the latest GitHub release without reading provider credentials.",
    )
    result.add_argument("--version", action="version", version=__version__)
    return result


def _provider_ids(value: str | None, argument_parser: argparse.ArgumentParser):
    if value is None:
        return None
    ids = [item.strip() for item in value.split(",") if item.strip()]
    invalid = [item for item in ids if item not in PROVIDER_IDS]
    if invalid:
        argument_parser.error(f"unsupported provider(s): {', '.join(invalid)}")
    return list(dict.fromkeys(ids))


def main(argv: Sequence[str] | None = None) -> int:
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    if args.check_update:
        payload = {
            "schema_version": 2,
            "update": check_for_update(__version__),
        }
    elif args.catalog:
        payload = catalog_snapshot()
    else:
        payload = collect_snapshot(
            provider_ids=_provider_ids(args.providers, argument_parser),
        )
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


def print_json() -> int:
    """Console-script compatibility entry point."""
    return main()
