"""Version and build information: exactly which software produced a result.

Why this exists:
    A test record is only traceable if it says which software produced it. "v0.3.0" is
    not enough during development. Two stations can both report 0.3.0 while running
    different commits, or one may have uncommitted local edits. So mastif records:

    - the **distribution version** from the installed package metadata, e.g. ``0.3.0``
      or ``0.4.0.dev0``
    - **git information**: commit, branch, date, author, subject, and whether the working
      tree had uncommitted changes

    Git information comes from one of two places:

    - **Embedded at build time.** A hatch build hook writes a ``_build_info.py`` module
      into the package when a wheel is built, so an installed wheel knows its commit
      even on a station with no git and no source checkout.
    - **Captured at run time** by running ``git`` in a source checkout, which covers
      development work.

    If neither is available, the git info says so explicitly (``source="unavailable"``),
    instead of pretending with empty strings.

Where it fits:
    `mastif.infra.bootstrap` logs a one-line summary at start-up. The planned engine
    records `VersionInfo` in every run manifest. Org SDKs can use the same tools for
    their own packages: point `VersionInfo.load` at their distribution, and copy the
    build hook (``packages/mastif/hatch_build.py``).
"""

import importlib
import importlib.metadata
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mastif.infra.errors import VersionError

_RELEASE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


class PackageVersion(BaseModel):
    """The installed version of a distribution, plus its parsed release numbers.

    Attributes:
        distribution: Distribution name, e.g. ``"mastif"``.
        version: The full version string, e.g. ``"0.4.0.dev0"`` (PEP 440).
        major: First release number.
        minor: Second release number (0 if absent).
        patch: Third release number (0 if absent).

    Example:
        >>> v = PackageVersion.parse("acme-sdk", "1.2.0rc1")
        >>> (v.major, v.minor, v.patch, v.is_prerelease)
        (1, 2, 0, True)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    distribution: str
    version: str
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, distribution: str, version: str) -> "PackageVersion":
        """Build from a version string, parsing its leading release numbers.

        Raises:
            VersionError: If the string doesn't start with a release number.

        Example:
            >>> PackageVersion.parse("x", "2.5").minor
            5
            >>> PackageVersion.parse("x", "banana")
            Traceback (most recent call last):
            ...
            mastif.infra.errors.VersionError: x: cannot parse version 'banana'
        """
        m = _RELEASE.match(version)
        if not m:
            raise VersionError(f"{distribution}: cannot parse version {version!r}")
        major, minor, patch = (int(g) if g else 0 for g in m.groups())
        return cls(
            distribution=distribution, version=version, major=major, minor=minor, patch=patch
        )

    @classmethod
    def of(cls, distribution: str) -> "PackageVersion":
        """Read an installed distribution's version from its package metadata.

        Raises:
            VersionError: If the distribution isn't installed.

        Example:
            >>> PackageVersion.of("mastif").distribution
            'mastif'
        """
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            raise VersionError(f"distribution {distribution!r} is not installed") from None
        return cls.parse(distribution, version)

    @property
    def is_prerelease(self) -> bool:
        """True for dev, alpha, beta and rc versions, which shouldn't run production tests.

        Example:
            >>> PackageVersion.parse("x", "0.4.0.dev0").is_prerelease
            True
        """
        return bool(re.search(r"(dev|a|b|rc)\d*", self.version))


class GitInfo(BaseModel):
    """The state of the source tree a package was built or run from.

    Attributes:
        source: Where the information came from: ``embedded`` (written at build time),
            ``runtime`` (asked from git now) or ``unavailable``.
        commit: Full commit hash.
        short_commit: Abbreviated hash.
        branch: Branch name.
        commit_date: Commit date (ISO 8601).
        author: Commit author name.
        subject: First line of the commit message.
        dirty: True if the tree had uncommitted changes.
        captured_at: When this information was captured (UTC, ISO 8601).

    Example:
        >>> GitInfo.unavailable().source
        'unavailable'
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["embedded", "runtime", "unavailable"]
    commit: str | None = None
    short_commit: str | None = None
    branch: str | None = None
    commit_date: str | None = None
    author: str | None = None
    subject: str | None = None
    dirty: bool | None = None
    captured_at: str | None = None

    @classmethod
    def unavailable(cls) -> "GitInfo":
        """Git information that couldn't be obtained, stated explicitly.

        Example:
            >>> GitInfo.unavailable().commit is None
            True
        """
        return cls(source="unavailable")

    @classmethod
    def from_git(cls, cwd: str | Path | None = None) -> "GitInfo":
        """Ask git about the repository containing ``cwd``.

        Each git command has a short timeout. If git is missing, ``cwd`` isn't a
        repository, or a command fails, the result is `unavailable`. That is a normal
        situation for an installed wheel, not an error.

        Args:
            cwd: A directory inside the repository; defaults to the working directory.

        Returns:
            The git information, or `unavailable`.

        Example:
            >>> import tempfile
            >>> GitInfo.from_git(tempfile.mkdtemp()).source
            'unavailable'
        """

        def git(*args: str) -> str | None:
            """Run one git command and return its stripped output, or ``None`` on failure.

            Example:
                ``git("rev-parse", "HEAD")``
            """
            try:
                out = subprocess.run(
                    ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10
                )
            except (OSError, subprocess.SubprocessError):
                return None
            return out.stdout.strip() if out.returncode == 0 else None

        log = git("log", "-1", "--format=%H%n%h%n%cI%n%an%n%s")
        if log is None:
            return cls.unavailable()
        fields = [*log.splitlines(), "", "", "", "", ""][:5]
        status = git("status", "--porcelain")
        return cls(
            source="runtime",
            commit=fields[0] or None,
            short_commit=fields[1] or None,
            commit_date=fields[2] or None,
            author=fields[3] or None,
            subject=fields[4] or None,
            branch=git("rev-parse", "--abbrev-ref", "HEAD"),
            dirty=None if status is None else bool(status),
            captured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    @classmethod
    def embedded(cls, module: str) -> "GitInfo | None":
        """Read git information embedded at build time, from ``<module>._build_info``.

        Args:
            module: The import name of the package, e.g. ``"mastif"``.

        Returns:
            The embedded information, or ``None`` if the package has no build info (for
            example an editable development install).

        Example:
            >>> GitInfo.embedded("json") is None
            True
        """
        try:
            info = importlib.import_module(f"{module}._build_info")
        except ImportError:
            return None
        data = getattr(info, "BUILD_INFO", None)
        if not isinstance(data, dict):
            return None
        return cls.model_validate({**data, "source": "embedded"})

    @classmethod
    def capture(cls, module: str | None = None, cwd: str | Path | None = None) -> "GitInfo":
        """Return the best available git information: embedded, then runtime, else unavailable.

        Example:
            >>> GitInfo.capture("json").source in {"runtime", "unavailable"}
            True
        """
        if module is not None:
            embedded = cls.embedded(module)
            if embedded is not None:
                return embedded
        return cls.from_git(cwd)


class VersionInfo(BaseModel):
    """Distribution version plus git information: the software identity of a run.

    Attributes:
        package: The installed version.
        git: The source-tree state.

    Example:
        >>> info = VersionInfo(package=PackageVersion.parse("acme-sdk", "1.2.0"),
        ...                    git=GitInfo(source="runtime", short_commit="abc1234",
        ...                                branch="main", dirty=True))
        >>> info.summary()
        'acme-sdk 1.2.0 | abc1234 on main | uncommitted changes'
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    package: PackageVersion
    git: GitInfo

    @classmethod
    def load(
        cls, distribution: str, module: str | None = None, cwd: str | Path | None = None
    ) -> "VersionInfo":
        """Collect version and git information for an installed distribution.

        Args:
            distribution: Distribution name, as in ``pyproject.toml`` (``"acme-sdk"``).
            module: Import name, used to find embedded build info. Defaults to the
                distribution name with ``-`` replaced by ``_``.
            cwd: Directory used for the runtime git fallback.

        Raises:
            VersionError: If the distribution isn't installed.

        Example:
            >>> VersionInfo.load("mastif").package.distribution
            'mastif'
        """
        return cls(
            package=PackageVersion.of(distribution),
            git=GitInfo.capture(module or distribution.replace("-", "_"), cwd),
        )

    def summary(self) -> str:
        """One line for logs and report headers.

        Example:
            >>> VersionInfo(package=PackageVersion.parse("m", "0.1.0"),
            ...             git=GitInfo.unavailable()).summary()
            'm 0.1.0 | git info unavailable'
        """
        parts = [f"{self.package.distribution} {self.package.version}"]
        g = self.git
        if g.source == "unavailable":
            parts.append("git info unavailable")
        else:
            parts.append(f"{g.short_commit or '?'} on {g.branch or '?'}")
            if g.dirty:
                parts.append("uncommitted changes")
        return " | ".join(parts)

    def __str__(self) -> str:
        """Same as `summary`.

        Example:
            ``print(VersionInfo.load("mastif"))``
        """
        return self.summary()
