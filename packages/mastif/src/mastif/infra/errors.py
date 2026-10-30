"""Errors raised by mastif's infrastructure layer: configuration, logging setup, versions.

Why this exists:
    Infrastructure problems happen at start-up: a config file that doesn't parse, a
    required setting that's missing, a logging config pointing at a handler that doesn't
    exist, a package whose version can't be read. They need their own types, so that an
    application's entry point can report "your configuration is wrong" clearly, instead
    of crashing with a library traceback, and so they're never confused with hardware or
    test failures.

Where it fits:
    `mastif.infra` sits just above the kernel (ADR-0001). These errors derive from
    `MastifError` (ADR-0002), so ``except MastifError`` at an entry point still catches
    everything mastif raises.

Hierarchy::

    MastifError
    └── InfraError
        ├── ConfigError     settings can't be loaded, or a section is missing or invalid
        └── VersionError    a distribution's version can't be read
"""

from mastif.kernel.errors import MastifError


class InfraError(MastifError):
    """Base class for infrastructure errors (configuration, logging, versions).

    Examples:
        >>> issubclass(ConfigError, InfraError) and issubclass(InfraError, MastifError)
        True
    """


class ConfigError(InfraError):
    """Settings couldn't be loaded, or a requested section is missing or invalid.

    The message names the file or the setting key, and lists every invalid field.

    Examples:
        >>> raise ConfigError("setting 'station' is missing")
        Traceback (most recent call last):
        ...
        mastif.infra.errors.ConfigError: setting 'station' is missing
    """


class VersionError(InfraError):
    """A distribution's version couldn't be read, typically because it isn't installed.

    Examples:
        >>> raise VersionError("distribution 'acme-sdk' is not installed")
        Traceback (most recent call last):
        ...
        mastif.infra.errors.VersionError: distribution 'acme-sdk' is not installed
    """
