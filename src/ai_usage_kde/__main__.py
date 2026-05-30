import sys

if "--json" in sys.argv:
    from .cli import print_json
    raise SystemExit(print_json())
else:
    from .main import main
    raise SystemExit(main())
