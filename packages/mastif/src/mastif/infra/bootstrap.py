"""Bootstrap: the few lines every mastif application runs first.

Why this exists:
    Every application built on mastif, whether a CLI, a service, an operator UI back-end
    or a notebook, starts the same way:

    1. load the settings
    2. configure logging, from the same config directory or settings
    3. log which software version is running

    Doing that by hand in each application leads to subtle differences, e.g. logging
    configured before settings, or a version never recorded. `bootstrap` does it in one
    call, in the right order, and returns a `Runtime` holding the objects the rest of the
    application receives through dependency injection.

Where it fits:
    This is the *composition root* helper for the infra layer: called once, at the very
    top of an application. Nothing else in mastif calls it, and nothing in mastif reads a
    global settings object. Components receive ``runtime.settings`` explicitly, e.g.
    ``Station.build(..., settings=runtime.settings)``.

Example::

    from mastif.infra.bootstrap import bootstrap

    runtime = bootstrap("C:/stations/bench-01/config", distribution="acme-sdk",
                        log_dir="C:/stations/bench-01/logs", envvar_prefix="ACME")
    station = Station.build(profile, registry, settings=runtime.settings)
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mastif.infra.config import DEFAULT_ENVVAR_PREFIX, Settings, create_settings
from mastif.infra.logs import configure_logging, resolve_logging_config
from mastif.infra.version import VersionInfo


@dataclass(frozen=True)
class Runtime:
    """What an application gets back from `bootstrap`, to pass to its components.

    Attributes:
        settings: The application's settings (a Dynaconf object).
        version: Version and git information of the application's distribution, or
            ``None`` if no distribution was named.

    Example:
        ``runtime.settings.station.name``, ``runtime.version.summary()``
    """

    settings: Settings
    version: VersionInfo | None


def bootstrap(
    config_dir: str | Path | None = None,
    *,
    distribution: str | None = None,
    log_dir: str | Path | None = None,
    log_level: int | str | None = None,
    files: Sequence[str | Path] = (),
    defaults: Mapping[str, Any] | None = None,
    envvar_prefix: str = DEFAULT_ENVVAR_PREFIX,
    environments: bool = False,
    env: str | None = None,
    load_dotenv: bool = False,
    rich_tracebacks: bool = True,
) -> Runtime:
    """Load settings, configure logging and record the version, in that order.

    Args:
        config_dir: The application's config directory (settings files, and optionally
            ``logging.yaml``).
        distribution: Your application's distribution name, e.g. ``"acme-sdk"``, whose
            version and git state are logged and returned.
        log_dir: Where relative log-file names go; defaults to the working directory.
        log_level: Overrides the root log level for this run, e.g. ``"DEBUG"``.
        files: Extra settings files, loaded after ``config_dir``.
        defaults: Lowest-precedence settings.
        envvar_prefix: Prefix for environment-variable overrides.
        environments: Enable ``[default]``/``[production]`` sections in settings files.
        env: The active environment, when ``environments`` is on.
        load_dotenv: Also read ``.env``.
        rich_tracebacks: Install Rich tracebacks for uncaught exceptions.

    Returns:
        The `Runtime`, whose ``settings`` you pass to your components.

    Raises:
        ConfigError: If settings or logging configuration can't be loaded.
        VersionError: If ``distribution`` isn't installed.

    Example:
        >>> rt = bootstrap(defaults={"station": {"name": "bench-01"},
        ...                          "logging": {"version": 1, "disable_existing_loggers": False}},
        ...                rich_tracebacks=False)
        >>> rt.settings.station.name, rt.version is None
        ('bench-01', True)
    """
    settings = create_settings(
        config_dir,
        files=files,
        defaults=defaults,
        envvar_prefix=envvar_prefix,
        environments=environments,
        env=env,
        load_dotenv=load_dotenv,
    )
    configure_logging(
        resolve_logging_config(settings, config_dir),
        log_dir=log_dir,
        level=log_level,
        rich_tracebacks=rich_tracebacks,
    )
    version = VersionInfo.load(distribution) if distribution else None
    log = logging.getLogger("mastif.bootstrap")
    if version is not None:
        log.info("starting %s", version.summary())
    if config_dir is not None:
        log.debug("settings loaded from %s", Path(config_dir).resolve())
    return Runtime(settings=settings, version=version)
