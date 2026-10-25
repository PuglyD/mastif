"""Unit tests for `mastif.infra.config`.

Settings are loaded once and passed everywhere, so these tests pin down:

- the load order: defaults < directory files (sorted) < explicit files < environment
- nested sections merge, rather than being replaced
- missing and broken files fail with `ConfigError`
- typed sections report every invalid field
- the flat-dict export excludes Dynaconf internals
"""

import pytest
from pydantic import BaseModel

from mastif.infra.config import as_dict, config_files, create_settings, section
from mastif.infra.errors import ConfigError


class StationSettings(BaseModel):
    """A typed section used by these tests."""

    name: str
    retries: int = 1


def _write(directory, name: str, text: str):
    """Write a config file.

    Args:
        directory: Target directory.
        name: File name.
        text: File contents.

    Returns:
        The file path.
    """
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def test_directory_files_load_in_sorted_order(tmp_path):
    """Later files (by name) override earlier ones, so numbered names control precedence."""
    _write(tmp_path, "10-site.yaml", "station:\n  retries: 5\n")
    _write(tmp_path, "00-base.toml", '[station]\nname = "bench-01"\nretries = 2\n')

    s = create_settings(tmp_path, envvar_prefix="MASTIFTEST_A")

    assert (s.station.name, s.station.retries) == ("bench-01", 5)


def test_config_files_ignores_other_suffixes(tmp_path):
    """Only toml, yaml, yml, json and ini files are settings files."""
    _write(tmp_path, "a.toml", "")
    _write(tmp_path, "readme.md", "")

    assert [p.name for p in config_files(tmp_path)] == ["a.toml"]


def test_defaults_have_lowest_precedence_and_merge(tmp_path):
    """Code defaults fill gaps but never override files; nested sections merge."""
    _write(tmp_path, "a.toml", '[station]\nname = "from-file"\n')

    s = create_settings(
        tmp_path,
        defaults={"station": {"name": "default", "retries": 3}},
        envvar_prefix="MASTIFTEST_B",
    )

    assert (s.station.name, s.station.retries) == ("from-file", 3)


def test_explicit_files_override_directory(tmp_path):
    """Machine-specific files passed explicitly win over the shared directory."""
    shared = tmp_path / "shared"
    shared.mkdir()
    _write(shared, "a.toml", '[station]\nname = "shared"\n')
    local = _write(tmp_path, "local.yaml", "station:\n  name: local\n")

    s = create_settings(shared, files=[local], envvar_prefix="MASTIFTEST_C")

    assert s.station.name == "local"


def test_environment_variables_override_files(tmp_path, monkeypatch):
    """``<PREFIX>_SECTION__KEY`` overrides a nested value from files."""
    _write(tmp_path, "a.toml", "[station]\nretries = 2\n")
    monkeypatch.setenv("MASTIFTEST_D_STATION__RETRIES", "9")

    s = create_settings(tmp_path, envvar_prefix="MASTIFTEST_D")

    assert s.station.retries == 9


def test_missing_directory_is_config_error(tmp_path):
    """A wrong config path fails clearly instead of silently loading nothing."""
    with pytest.raises(ConfigError, match="does not exist"):
        create_settings(tmp_path / "nope")


def test_missing_explicit_file_is_config_error(tmp_path):
    """An explicit file that doesn't exist is an error, not a silent skip."""
    with pytest.raises(ConfigError, match="does not exist"):
        create_settings(files=[tmp_path / "missing.toml"])


def test_unparseable_file_fails_at_creation(tmp_path):
    """Dynaconf loads lazily; mastif forces loading so broken files fail at start-up."""
    _write(tmp_path, "bad.toml", "this is = = not toml")

    with pytest.raises(ConfigError, match="cannot load settings"):
        create_settings(tmp_path, envvar_prefix="MASTIFTEST_E")


def test_section_validates_into_model():
    """A typed section converts and validates values (e.g. "3" becomes 3)."""
    s = create_settings(defaults={"station": {"name": "b1", "retries": "3"}})

    assert section(s, "station", StationSettings) == StationSettings(name="b1", retries=3)


def test_section_reports_every_invalid_field():
    """Invalid sections fail with the key and each bad field named."""
    s = create_settings(defaults={"station": {"retries": "many"}})

    with pytest.raises(ConfigError, match=r"'station' is invalid: name: .*retries: "):
        section(s, "station", StationSettings)


def test_section_supports_dotted_keys():
    """Nested sections can be addressed with dotted paths."""
    s = create_settings(defaults={"engine": {"station": {"name": "b2"}}})

    assert section(s, "engine.station", StationSettings).name == "b2"


def test_as_dict_excludes_dynaconf_internals():
    """The exported dict holds only application settings, ready for a run manifest."""
    assert as_dict(create_settings(defaults={"a": 1})) == {"a": 1}


def test_two_settings_objects_are_independent():
    """No global state: each settings object is separate, so tests never interfere."""
    a = create_settings(defaults={"x": 1})
    b = create_settings(defaults={"x": 2})

    assert (a.x, b.x) == (1, 2)
