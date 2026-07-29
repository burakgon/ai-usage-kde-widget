from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .catalog import PROVIDER_CATALOG
from .environment import LoginShellEnvironment


def provider_descriptors(
    environment: LoginShellEnvironment,
) -> tuple:
    descriptors = []
    for descriptor in PROVIDER_CATALOG:
        indicators = list(descriptor.installation_indicators)
        if descriptor.provider_id == "claude":
            if config_dir := environment.value("CLAUDE_CONFIG_DIR"):
                indicators.insert(0, config_dir)
        elif descriptor.provider_id == "codex":
            if codex_home := environment.value("CODEX_HOME"):
                indicators.insert(0, codex_home)
        descriptors.append((
            descriptor.provider_id,
            descriptor.executable_names,
            tuple(dict.fromkeys(indicators)),
        ))
    return tuple(descriptors)


def detect_installed_providers(
    environment: LoginShellEnvironment | None = None,
    *,
    exists: Callable[[Path], bool] = Path.exists,
    executable: Callable[[Path], bool] | None = None,
) -> set[str]:
    environment = environment or LoginShellEnvironment()
    search_path_reader = getattr(environment, "search_path", None)
    search_path = (
        search_path_reader()
        if callable(search_path_reader)
        else environment.value("PATH") or ""
    )
    path_entries = [
        Path(os.path.expanduser(entry))
        for entry in search_path.split(os.pathsep)
        if entry
    ]
    is_executable = executable or _is_executable_file

    installed: set[str] = set()
    for provider_id, executable_names, installation_indicators in provider_descriptors(environment):
        has_executable = any(
            is_executable(directory / name)
            for directory in path_entries
            for name in executable_names
        )
        has_indicator = any(
            exists(Path(os.path.expanduser(path)))
            for path in installation_indicators
        )
        if has_executable or has_indicator:
            installed.add(provider_id)
    return installed


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)
