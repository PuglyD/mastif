"""Unit tests for `mastif.infra.version` and `mastif.infra.bootstrap`.

Every run must record exactly which software produced it, so these tests pin down:

- version parsing and pre-release detection
- git capture from a real temporary repository, including the dirty flag
- the explicit "unavailable" state outside git
- embedded build info taking precedence over live git
- `bootstrap` loading settings, configuring logging and reporting the version, in order
"""

import logging
import shutil
import subprocess
import sys
import types

import pytest

from mastif.infra.bootstrap import bootstrap
from mastif.infra.errors import VersionError
from mastif.infra.version import GitInfo, PackageVersion, VersionInfo

HAS_GIT = shutil.which("git") is not None


@pytest.fixture(autouse=True)
def _restore_logging():
    """Put the root logger back after tests that bootstrap logging."""
    root = logging.getLogger()
    handlers, level, cls = root.handlers[:], root.level, logging.getLoggerClass()
    yield
    for h in root.handlers[:]:
        if h not in handlers:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)
    logging.setLoggerClass(cls)


@pytest.mark.parametrize(
    ("text", "expected", "pre"),
    [
        ("1.2.3", (1, 2, 3), False),
        ("0.4.0.dev0", (0, 4, 0), True),
        ("2.0rc1", (2, 0, 0), True),
        ("7", (7, 0, 0), False),
    ],
)
def test_version_parsing(text, expected, pre):
    """Release numbers are parsed and pre-releases detected.

    Args:
        text: The version string.
        expected: ``(major, minor, patch)``.
        pre: Whether it is a pre-release.
    """
    v = PackageVersion.parse("x", text)

    assert ((v.major, v.minor, v.patch), v.is_prerelease) == (expected, pre)


def test_unknown_distribution_is_version_error():
    """Asking for a package that isn't installed fails clearly; there is no 0.0.0 sentinel."""
    with pytest.raises(VersionError, match="not installed"):
        PackageVersion.of("definitely-not-installed-xyz")


def test_outside_git_is_explicitly_unavailable(tmp_path):
    """Without a repository, git info says 'unavailable' instead of empty strings."""
    assert GitInfo.from_git(tmp_path) == GitInfo.unavailable()


@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_git_capture_reads_commit_and_dirty_flag(tmp_path):
    """Commit, branch, subject and uncommitted changes are captured from a real repo."""

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-b", "main")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=t@example.com",
        "commit",
        "--allow-empty",
        "-m",
        "first commit",
    )
    (tmp_path / "x.txt").write_text("edit")

    info = GitInfo.from_git(tmp_path)

    assert (info.source, info.branch, info.subject, info.dirty) == (
        "runtime",
        "main",
        "first commit",
        True,
    )


def test_embedded_build_info_wins(monkeypatch):
    """Information embedded at build time is preferred over asking git."""
    fake = types.ModuleType("fakepkg._build_info")
    setattr(fake, "BUILD_INFO", {"commit": "abc", "short_commit": "abc", "branch": "release"})  # noqa: B010
    monkeypatch.setitem(sys.modules, "fakepkg", types.ModuleType("fakepkg"))
    monkeypatch.setitem(sys.modules, "fakepkg._build_info", fake)

    info = GitInfo.capture("fakepkg")

    assert (info.source, info.branch) == ("embedded", "release")


def test_summary_mentions_uncommitted_changes():
    """The one-line summary warns when the tree had local edits."""
    info = VersionInfo(
        package=PackageVersion.parse("acme", "1.0.0"),
        git=GitInfo(source="runtime", short_commit="abc", branch="dev", dirty=True),
    )

    assert info.summary() == "acme 1.0.0 | abc on dev | uncommitted changes"


def test_version_info_load_for_installed_package():
    """The mastif distribution itself can report its version and git state."""
    assert VersionInfo.load("mastif").package.distribution == "mastif"


def test_bootstrap_loads_settings_configures_logging_and_version(tmp_path):
    """One call yields settings, configured logging (from logging.yaml) and version info."""
    (tmp_path / "app.toml").write_text('[station]\nname = "bench-01"\n')
    (tmp_path / "logging.yaml").write_text(
        "version: 1\ndisable_existing_loggers: false\nroot: {level: WARNING}\n"
    )

    rt = bootstrap(
        tmp_path, distribution="mastif", envvar_prefix="MASTIFTEST_BOOT", rich_tracebacks=False
    )

    assert rt.settings.station.name == "bench-01"
    assert logging.getLogger().level == logging.WARNING
    assert rt.version is not None and rt.version.package.distribution == "mastif"


def test_bootstrap_log_level_override(tmp_path):
    """``log_level`` overrides the configured root level for a verbose run."""
    rt = bootstrap(
        defaults={"logging": {"version": 1, "disable_existing_loggers": False}},
        log_level="DEBUG",
        rich_tracebacks=False,
    )

    assert rt.version is None and logging.getLogger().level == logging.DEBUG
