import sys

if "--json" in sys.argv:
    from .cli import print_json
    raise SystemExit(print_json())

print("ai-usage-kde: a usage snapshot helper for the AI Usage KDE plasmoid.\n"
      "Run with --json to print the current Claude Code / Codex usage as JSON.",
      file=sys.stderr)
raise SystemExit(2)
