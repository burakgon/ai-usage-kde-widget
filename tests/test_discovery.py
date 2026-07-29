from types import SimpleNamespace

from ai_usage_kde.core.discovery import detect_installed_providers
from ai_usage_kde.core.environment import LoginShellEnvironment


class _Environment:
    def __init__(self, values):
        self.values = values

    def value(self, name):
        return self.values.get(name)


def test_login_shell_environment_prefers_process_and_parses_markers():
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "startup noise\n"
                "__AI_USAGE_ENV_BEGIN__\0"
                "CLAUDE_CONFIG_DIR=/profiles/work\0"
                "CODEX_HOME=/profiles/codex\0"
                "PATH=/login/bin:/process/bin\0"
                "__AI_USAGE_ENV_END__\0"
                "more noise"
            ),
            stderr="",
        )

    environment = LoginShellEnvironment(
        environ={
            "PATH": "/process/bin",
            "SHELL": "/bin/sh",
            "HOME": "/tmp/home",
        },
        runner=runner,
    )
    assert environment.value("PATH") == "/process/bin"
    assert calls == []
    assert environment.search_path() == "/process/bin:/login/bin"
    assert len(calls) == 1
    assert environment.value("CLAUDE_CONFIG_DIR") == "/profiles/work"
    assert environment.value("CODEX_HOME") == "/profiles/codex"
    assert len(calls) == 1
    assert environment.value("UNSUPPORTED_SECRET") is None


def test_detects_executables_and_installation_indicators(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    claude.write_text("#!/bin/sh\n", encoding="utf-8")
    claude.chmod(0o755)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()

    installed = detect_installed_providers(_Environment({
        "PATH": str(bin_dir),
        "CODEX_HOME": str(codex_home),
    }))
    assert installed == {"claude", "codex"}


def test_detects_executable_from_login_shell_path(tmp_path):
    bin_dir = tmp_path / "login-bin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    claude.write_text("#!/bin/sh\n", encoding="utf-8")
    claude.chmod(0o755)

    def runner(args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "__AI_USAGE_ENV_BEGIN__\0"
                f"PATH={bin_dir}\0"
                "__AI_USAGE_ENV_END__\0"
            ),
            stderr="",
        )

    environment = LoginShellEnvironment(
        environ={
            "PATH": "/usr/bin",
            "SHELL": "/bin/sh",
            "HOME": str(tmp_path),
        },
        runner=runner,
    )
    exists_in_test = lambda path: path.exists() and tmp_path in path.parents
    assert detect_installed_providers(
        environment,
        exists=exists_in_test,
    ) == {"claude"}


def test_non_executable_file_does_not_count_as_cli(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("not executable", encoding="utf-8")
    environment = _Environment({
        "PATH": str(bin_dir),
        "CLAUDE_CONFIG_DIR": str(tmp_path / "missing-claude"),
        "CODEX_HOME": str(tmp_path / "missing-codex"),
    })
    exists_in_test = lambda path: path.exists() and tmp_path in path.parents
    assert detect_installed_providers(environment, exists=exists_in_test) == set()


def test_custom_claude_directory_is_an_installation_indicator(tmp_path):
    config_dir = tmp_path / "claude-profile"
    config_dir.mkdir()
    environment = _Environment({
        "PATH": "",
        "CLAUDE_CONFIG_DIR": str(config_dir),
    })
    exists_in_test = lambda path: path.exists() and tmp_path in path.parents
    assert detect_installed_providers(environment, exists=exists_in_test) == {"claude"}


def test_detects_all_reference_cli_names_in_catalog_order(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in (
        "claude",
        "codex",
        "cursor-agent",
        "agy-ide",
        "github-copilot",
        "devin",
        "grok",
    ):
        executable = bin_dir / name
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
    installed = detect_installed_providers(_Environment({"PATH": str(bin_dir)}))
    assert installed == {
        "claude", "codex", "cursor", "antigravity", "copilot", "devin", "grok"
    }
