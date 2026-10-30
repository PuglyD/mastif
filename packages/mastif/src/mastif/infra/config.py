"""Application settings: one Dynaconf object, built once and passed to whatever needs it.

Why this exists:
    A test application has a lot of configuration:

    - station names
    - default timeouts
    - limits files
    - operator options
    - org-specific knobs

    It lives in several files, and some values need overriding per machine (an
    environment variable on one station) or per stage (development vs production).
    Dynaconf already solves loading, merging and overriding well. What mastif adds is a
    disciplined way to use it:

    - **Build it once, at the composition root.** That is the application's entry
      point, e.g. the CLI or a service. `create_settings` does the building.
    - **Pass it explicitly** (dependency injection) to the classes and functions that
      need it. There is no importable global, so tests can build their own settings,
      and two settings objects never interfere.
    - **Read typed sections** where structure matters. `section` validates one part of
      the settings into a Pydantic model and reports every invalid field.

Where it fits:
    `mastif.infra` is the layer just above the kernel (ADR-0001). The station accepts
    ``settings=`` and injects it into any driver whose ``__init__`` has a parameter
    annotated `Settings` (ADR-0011, ADR-0023). Logging can be configured from the same
    settings (`mastif.infra.logs`).

How loading works:
    Sources are applied in this order; later sources override earlier ones, and nested
    sections are **merged** rather than replaced:

    1. ``defaults``: a mapping you pass, e.g. code-level defaults.
    2. Files in ``config_dir``: every ``*.toml``, ``*.yaml``, ``*.yml``, ``*.json`` and
       ``*.ini``, in sorted filename order. Prefix names to control the order:
       ``00-base.toml``, ``10-site.yaml``.
    3. ``files``: explicit extra files, in the order given.
    4. ``.env`` (if ``load_dotenv``) and environment variables starting with
       ``<envvar_prefix>_``. A double underscore reaches into sections:
       ``MASTIF_STATION__RETRIES=5`` sets ``station.retries``.

    With ``environments=True``, files must put keys under ``[default]``,
    ``[development]``, ``[production]`` (etc.) sections, and the active one is chosen by
    ``env=`` or ``<prefix>_ENV``. Keys outside those sections are ignored. That is
    Dynaconf's behaviour, so this option is off by default.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dynaconf import Dynaconf
from pydantic import BaseModel, ValidationError

from mastif.infra.errors import ConfigError

Settings = Dynaconf
"""The type to annotate parameters with: ``def __init__(self, settings: Settings)``."""

CONFIG_SUFFIXES: tuple[str, ...] = (".toml", ".yaml", ".yml", ".json", ".ini")
"""File suffixes recognised by `config_files` when scanning a configuration directory."""
DEFAULT_ENVVAR_PREFIX: str = "MASTIF"
"""Default prefix for environment-variable overrides in `create_settings`."""

# Options mastif passes to Dynaconf that Dynaconf also exposes as settings.
_DYNACONF_OPTION_KEYS = frozenset(
    {"LOAD_DOTENV", "ENVVAR_PREFIX", "ENVIRONMENTS", "MERGE_ENABLED", "SETTINGS_FILES", "ENV"}
)


def config_files(config_dir: str | Path) -> list[Path]:
    """List the config files in a directory, in the order they are loaded.

    Only the top level of the directory is scanned, and files are sorted by name, so the
    load order is deterministic and visible. Number the names to control precedence.

    Args:
        config_dir: The directory to scan.

    Returns:
        Config files with a supported suffix, sorted by filename.

    Raises:
        ConfigError: If the directory doesn't exist.

    Examples:
        >>> import tempfile, pathlib
        >>> d = pathlib.Path(tempfile.mkdtemp())
        >>> for name in ("10-site.yaml", "00-base.toml", "notes.txt"):
        ...     _ = (d / name).write_text("")
        >>> for p in config_files(d):
        ...     print(p.name)
        00-base.toml
        10-site.yaml
    """
    path = Path(config_dir)
    if not path.is_dir():
        raise ConfigError(f"config directory {str(path)!r} does not exist")
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix in CONFIG_SUFFIXES)


def create_settings(
    config_dir: str | Path | None = None,
    *,
    files: Sequence[str | Path] = (),
    defaults: Mapping[str, Any] | None = None,
    envvar_prefix: str = DEFAULT_ENVVAR_PREFIX,
    environments: bool = False,
    env: str | None = None,
    load_dotenv: bool = False,
) -> Settings:
    """Build the application's settings object. Call once, at start-up, then pass it on.

    Args:
        config_dir: Directory whose config files are loaded (see `config_files`). ``None``
            loads no directory.
        files: Extra files loaded after the directory, in order. Use these for
            machine-specific overrides.
        defaults: Lowest-precedence values, applied before any file.
        envvar_prefix: Environment variables starting with ``<prefix>_`` override
            settings. Orgs usually choose their own, e.g. ``"ACME"``.
        environments: Enable ``[default]``/``[development]``/``[production]`` sections.
        env: The active environment when ``environments`` is on (otherwise taken from
            ``<prefix>_ENV``, defaulting to ``development``).
        load_dotenv: Also read a ``.env`` file from the working directory.

    Returns:
        A Dynaconf settings object: dotted access (``settings.station.retries``),
        ``settings.get("key", default)``, case-insensitive top-level keys.

    Raises:
        ConfigError: If the directory or an explicit file doesn't exist, or a file can't
            be parsed.

    Examples:
        >>> s = create_settings(defaults={"station": {"retries": 2, "name": "bench-01"}})
        >>> s.station.retries, s.get("missing", "fallback")
        (2, 'fallback')
    """
    sources: list[Path] = []
    if config_dir is not None:
        sources.extend(config_files(config_dir))
    for f in files:
        p = Path(f)
        if not p.is_file():
            raise ConfigError(f"config file {str(p)!r} does not exist")
        sources.append(p)
    options: dict[str, Any] = {
        "settings_files": [str(s) for s in sources],
        "envvar_prefix": envvar_prefix,
        "environments": environments,
        "load_dotenv": load_dotenv,
        "merge_enabled": True,
    }
    if env is not None:
        options["env"] = env
    # Dynaconf treats upper-case keyword arguments as lowest-precedence default values.
    options.update({str(k).upper(): v for k, v in (defaults or {}).items()})
    settings = Dynaconf(**options)
    try:
        settings.as_dict()  # Dynaconf loads lazily; force it so bad files fail here.
    except Exception as exc:
        raise ConfigError(f"cannot load settings: {type(exc).__name__}: {exc}") from exc
    return settings


def _plain(value: Any) -> Any:
    """Convert Dynaconf's box types into plain dicts and lists, recursively.

    Examples:
        >>> _plain({"a": [{"b": 1}]})
        {'a': [{'b': 1}]}
    """
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def section[M: BaseModel](settings: Settings, key: str, model: type[M]) -> M:
    """Read one part of the settings as a validated, typed Pydantic model.

    Raw Dynaconf access is convenient but untyped: a typo in a key just reads as
    missing. For settings a component depends on, declare a model and read it through
    this function. Mistakes then fail at start-up, with every bad field listed.

    Args:
        settings: The settings object.
        key: Dotted path to the section, e.g. ``"station"`` or ``"engine.retries"``.
        model: The Pydantic model to validate it into.

    Returns:
        The validated model.

    Raises:
        ConfigError: If the section is missing or doesn't validate.

    Examples:
        >>> from pydantic import BaseModel
        >>> class StationSettings(BaseModel):
        ...     name: str
        ...     retries: int = 1
        >>> s = create_settings(defaults={"station": {"name": "bench-01", "retries": "3"}})
        >>> section(s, "station", StationSettings)
        StationSettings(name='bench-01', retries=3)
        >>> section(s, "engine", StationSettings)
        Traceback (most recent call last):
        ...
        mastif.infra.errors.ConfigError: setting 'engine' is missing
    """
    raw = settings.get(key)
    if raw is None:
        raise ConfigError(f"setting {key!r} is missing")
    try:
        return model.model_validate(_plain(raw))
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors()
        )
        raise ConfigError(f"setting {key!r} is invalid: {details}") from exc


def as_dict(settings: Settings) -> dict[str, Any]:
    """Return every setting as a plain dict, e.g. to record in a run manifest.

    Dynaconf's internal keys are excluded, and top-level keys are lowercase.

    Args:
        settings: The settings object.

    Returns:
        A JSON-friendly dict.

    Examples:
        >>> as_dict(create_settings(defaults={"station": {"name": "b1"}}))
        {'station': {'name': 'b1'}}
    """
    return {
        str(k).lower(): _plain(v)
        for k, v in settings.as_dict().items()
        if str(k).upper() not in _DYNACONF_OPTION_KEYS and not str(k).endswith("_FOR_DYNACONF")
    }
