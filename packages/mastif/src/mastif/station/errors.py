"""Errors about a station's configuration and composition.

Why this exists:
    A broken station profile (an unknown driver, a typo in a config key, a role
    pointing at nothing, a DUT channel left unmapped) should be reported **before any
    hardware is touched**, with the resource name in the message. These errors are
    raised while loading a profile, building the station, or resolving roles. They are
    kept separate from `ResourceError`, which is about devices misbehaving at run time.

Example:
    >>> raise RoleError("no role 'psu_main'; known roles: dut, psu_aux")
    Traceback (most recent call last):
    ...
    mastif.station.errors.RoleError: no role 'psu_main'; known roles: dut, psu_aux
"""

from mastif.kernel.errors import MastifError


class StationError(MastifError):
    """The station profile is invalid, or the station can't be built from it.

    Example:
        >>> str(StationError("resource 'bench_psu': unknown config key 'chanel'"))
        "resource 'bench_psu': unknown config key 'chanel'"
    """


class RoleError(StationError):
    """A task asked for a role the station doesn't have, or one that can't serve its contract.

    Example:
        >>> issubclass(RoleError, StationError)
        True
    """
