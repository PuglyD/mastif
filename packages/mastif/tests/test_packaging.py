"""Checks on the licence files that ship inside every mastif wheel (ADR-0031).

PEP 639 only lets a package include licence files from its own directory, so each
workspace package keeps a copy of the repository's ``LICENSE`` and ``NOTICE``. These
tests make sure the copies never drift from the originals, and that the package
metadata declares the licence, so every installed wheel states its terms correctly.
"""

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = sorted(p.parent for p in (ROOT / "packages").glob("*/pyproject.toml"))


@pytest.mark.parametrize("package", PACKAGES, ids=lambda p: p.name)
@pytest.mark.parametrize("filename", ["LICENSE", "NOTICE"])
def test_licence_copies_match_the_root(package: Path, filename: str) -> None:
    """Each package's licence file is byte-identical to the repository's.

    The wheel ships the package copy, so an edited copy would ship terms that differ
    from the ones the project actually grants.

    Args:
        package: The workspace package directory.
        filename: The licence file to compare.
    """
    assert (package / filename).read_bytes() == (ROOT / filename).read_bytes()


@pytest.mark.parametrize("package", PACKAGES, ids=lambda p: p.name)
def test_package_metadata_declares_the_licence(package: Path) -> None:
    """Each package declares ``AGPL-3.0-or-later`` and lists both licence files.

    Installers, licence scanners and company policy tools read this metadata, not the
    repository, so it must name the licence exactly.

    Args:
        package: The workspace package directory.
    """
    project = tomllib.loads((package / "pyproject.toml").read_text("utf-8"))["project"]

    assert project["license"] == "AGPL-3.0-or-later"
    assert project["license-files"] == ["LICENSE", "NOTICE"]


def test_licence_is_the_official_agpl_text() -> None:
    """The root ``LICENSE`` is the unmodified GNU AGPL version 3 text.

    The file must be the verbatim FSF publication; this catches accidental edits and
    line-ending conversion.
    """
    text = (ROOT / "LICENSE").read_bytes()

    assert text.startswith(b"                    GNU AFFERO GENERAL PUBLIC LICENSE\n")
    assert b"\r\n" not in text
    assert b"Version 3, 19 November 2007" in text
