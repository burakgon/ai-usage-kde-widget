from __future__ import annotations

import os
import pwd
import subprocess
from collections.abc import Mapping
from typing import Optional, Protocol


_SUPPORTED_NAMES = (
    "CLAUDE_CONFIG_DIR",
    "CODEX_HOME",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "PATH",
)
_BEGIN_MARKER = "__AI_USAGE_ENV_BEGIN__"
_END_MARKER = "__AI_USAGE_ENV_END__"


class ProcessRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        env: Mapping[str, str],
        timeout: float,
    ) -> subprocess.CompletedProcess[str]: ...


def _run_process(
    args: list[str],
    *,
    env: Mapping[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        env=dict(env),
        timeout=timeout,
        check=False,
        capture_output=True,
        text=True,
    )


class LoginShellEnvironment:
    """Read selected values from this process, then from the login shell.

    Plasma helpers do not always inherit the user's interactive PATH. Only a
    fixed allow-list is captured, and startup-file noise is ignored by parsing
    values between NUL-delimited markers.
    """

    def __init__(
        self,
        environ: Optional[Mapping[str, str]] = None,
        runner: ProcessRunner = _run_process,
        timeout: float = 5.0,
    ):
        self._environ = dict(os.environ if environ is None else environ)
        self._runner = runner
        self._timeout = timeout
        self._captured: Optional[dict[str, str]] = None

    def value(self, name: str) -> Optional[str]:
        if name not in _SUPPORTED_NAMES:
            return None
        direct = self._clean(self._environ.get(name))
        if direct is not None:
            return direct
        if self._captured is None:
            self._captured = self._capture()
        return self._captured.get(name)

    def snapshot(self) -> dict[str, str]:
        return {
            name: value
            for name in _SUPPORTED_NAMES
            if (value := self.value(name)) is not None
        }

    def search_path(self) -> str:
        """Merge the process and login-shell PATH values for CLI discovery."""
        direct = self._clean(self._environ.get("PATH"))
        if self._captured is None:
            self._captured = self._capture()
        captured = self._clean(self._captured.get("PATH"))

        entries: list[str] = []
        for value in (direct, captured):
            if value is None:
                continue
            for entry in value.split(os.pathsep):
                if entry and entry not in entries:
                    entries.append(entry)
        return os.pathsep.join(entries)

    def _capture(self) -> dict[str, str]:
        shell = self._shell()
        names = " ".join(_SUPPORTED_NAMES)
        command = (
            f"printf '%s\\0' {_BEGIN_MARKER}; "
            f"for name in {names}; do "
            'value=$(printenv "$name"); '
            'if [ -n "$value" ]; then printf \'%s=%s\\0\' "$name" "$value"; fi; '
            f"done; printf '%s\\0' {_END_MARKER}"
        )
        child_env = {
            key: value
            for key in ("HOME", "USER", "LOGNAME", "SHELL", "TERM")
            if (value := self._environ.get(key))
        }
        child_env.setdefault("HOME", os.path.expanduser("~"))
        child_env.setdefault("SHELL", shell)
        child_env.setdefault("TERM", "dumb")
        child_env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        try:
            result = self._runner(
                [shell, "-ilc", command],
                env=child_env,
                timeout=self._timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return {}
        if result.returncode != 0:
            return {}
        return self.parse(result.stdout)

    def _shell(self) -> str:
        configured = self._clean(self._environ.get("SHELL"))
        if configured and os.path.isfile(configured) and os.access(configured, os.X_OK):
            return configured
        try:
            account_shell = pwd.getpwuid(os.getuid()).pw_shell
        except (KeyError, OSError):
            account_shell = ""
        if account_shell and os.path.isfile(account_shell) and os.access(account_shell, os.X_OK):
            return account_shell
        return "/bin/sh"

    @staticmethod
    def parse(output: str) -> dict[str, str]:
        begin_marker = _BEGIN_MARKER + "\0"
        begin = output.find(begin_marker)
        if begin < 0:
            return {}
        begin += len(begin_marker)
        end = output.find("\0" + _END_MARKER, begin)
        if end < 0:
            end = len(output)
        values: dict[str, str] = {}
        for token in output[begin:end].split("\0"):
            name, separator, value = token.partition("=")
            if separator and name in _SUPPORTED_NAMES and value:
                values[name] = value
        return values

    @staticmethod
    def _clean(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
