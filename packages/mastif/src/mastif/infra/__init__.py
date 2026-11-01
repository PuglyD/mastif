"""Infrastructure: settings, logging and version information for mastif applications.

This layer sits just above the kernel (ADR-0001). It does I/O (files, environment
variables, git), so it can't live in the pure kernel, but every higher layer may use it.

- `config`: build one Dynaconf `Settings` object and pass it explicitly. `section`
  reads typed parts of it.
- `logs`: Rich console, rotating file, tables rendered as tables, TRACE/SUCCESS levels.
- `version`: distribution version plus git information (embedded at build, or live).
- `bootstrap`: the one call an application makes at start-up.

Examples:
    >>> from mastif.infra import create_settings, section
    >>> create_settings(defaults={"station": {"name": "bench-01"}}).station.name
    'bench-01'
"""

from mastif.infra.bootstrap import Runtime, bootstrap
from mastif.infra.config import Settings, as_dict, config_files, create_settings, section
from mastif.infra.errors import ConfigError, InfraError, VersionError
from mastif.infra.logs import (
    SUCCESS,
    TRACE,
    Loggers,
    MastifLogger,
    RichTableHandler,
    TableAwareFormatter,
    configure_logging,
    resolve_logging_config,
)
from mastif.infra.version import GitInfo, PackageVersion, VersionInfo

__all__ = [
    "SUCCESS",
    "TRACE",
    "ConfigError",
    "GitInfo",
    "InfraError",
    "Loggers",
    "MastifLogger",
    "PackageVersion",
    "RichTableHandler",
    "Runtime",
    "Settings",
    "TableAwareFormatter",
    "VersionError",
    "VersionInfo",
    "as_dict",
    "bootstrap",
    "config_files",
    "configure_logging",
    "create_settings",
    "resolve_logging_config",
    "section",
]
