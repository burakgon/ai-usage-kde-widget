#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_directory=$(CDPATH= cd -- "$script_directory/.." && pwd)
restart_plasma=false

if [ "${1:-}" = "--restart-plasma" ]; then
    restart_plasma=true
elif [ "$#" -gt 0 ]; then
    echo "Usage: $0 [--restart-plasma]" >&2
    exit 2
fi

for executable in python3 kpackagetool6; do
    if ! command -v "$executable" >/dev/null 2>&1; then
        echo "Required command not found: $executable" >&2
        exit 1
    fi
done

build_directory="$project_directory/build"
if [ -d "$build_directory" ]; then
    rm -rf -- "$build_directory"
fi

python3 -m pip install \
    --user \
    --upgrade \
    --force-reinstall \
    --break-system-packages \
    "$project_directory"

if kpackagetool6 -t Plasma/Applet -s com.bgn.aiusage >/dev/null 2>&1; then
    kpackagetool6 -t Plasma/Applet -u "$project_directory/plasmoid"
else
    kpackagetool6 -t Plasma/Applet -i "$project_directory/plasmoid"
fi

legacy_cache="${XDG_CACHE_HOME:-${HOME}/.cache}/ai-usage-kde/retry-state.json"
if [ -f "$legacy_cache" ]; then
    rm -f -- "$legacy_cache"
fi

if [ "$restart_plasma" = true ]; then
    if systemctl --user is-active plasma-plasmashell.service >/dev/null 2>&1; then
        systemctl --user restart plasma-plasmashell.service
    else
        kquitapp6 plasmashell >/dev/null 2>&1 || true
        kstart plasmashell >/dev/null 2>&1
    fi
fi

echo "AI Usage 2.0.0 installed."
