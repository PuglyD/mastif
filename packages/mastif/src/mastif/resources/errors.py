"""Errors raised by instruments, DUTs, transports and the driver machinery.

Why this exists:
    When something goes wrong at a test station, the next step depends on what went
    wrong. A cable fell out (`TransportError`). An instrument answered nonsense
    (`ProtocolError`). The wrong unit is on the bench (`IdentityMismatch`). The device
    reports a fault (`ResourceFault`). The org's driver code itself is wrong
    (`DriverDefinitionError`). Typed errors let the engine, the operator UI and the org's
    own code react to each case precisely, instead of parsing messages.

Where it fits:
    Drivers raise these errors; they never return sentinel values like ``0.0`` or
    ``None`` to mean "failed". The station's resource manager raises them while opening
    resources. The engine turns any exception escaping a test task into an ERROR
    verdict, because it says nothing about the device's quality, only that the test
    couldn't finish.

Hierarchy::

    MastifError
    └── ResourceError
        ├── DriverDefinitionError      the driver/contract code is wrong
        │   └── ContractMismatch       driver doesn't implement a contract it claims
        ├── DriverNotFound             no registered driver has the requested id
        ├── TransportError             bytes couldn't be moved (connection, I/O)
        │   └── TransportTimeout       no answer in time
        ├── ProtocolError              bytes moved, but the reply made no sense
        ├── IdentityMismatch           a different device than expected is connected
        └── ResourceFault              the device reports a fault or failed health check
"""

from mastif.kernel.errors import MastifError


class ResourceError(MastifError):
    """Base class for every instrument, DUT and transport error.

    Catch this when you want to handle any hardware-side failure in one place, for
    example to put the station into a safe state.

    Example:
        >>> try:
        ...     raise TransportTimeout("no reply from 10.0.0.5:5025 within 2.0 s")
        ... except ResourceError as exc:
        ...     print(type(exc).__name__)
        TransportTimeout
    """


class DriverDefinitionError(ResourceError):
    """A driver or DUT class is defined incorrectly.

    Raised when the class is decorated, i.e. when the org's module is imported. The
    mistake therefore shows up in the org's own unit tests, not at a test station.

    Example:
        >>> raise DriverDefinitionError("acme.psu-x: Config must subclass DriverConfig")
        Traceback (most recent call last):
        ...
        mastif.resources.errors.DriverDefinitionError: acme.psu-x: Config must subclass DriverConfig
    """


class ContractMismatch(DriverDefinitionError):
    """A driver claims to provide a contract but is missing some of its methods.

    Example:
        >>> raise ContractMismatch("acme.psu-x: PowerSupply: output: missing")
        Traceback (most recent call last):
        ...
        mastif.resources.errors.ContractMismatch: acme.psu-x: PowerSupply: output: missing
    """


class DriverNotFound(ResourceError):
    """A station profile names a driver id that no registered driver has.

    Usually a typo in the profile, or the org's SDK package isn't installed.

    Example:
        >>> raise DriverNotFound("no driver 'acme.psu-y'; known: acme.psu-x")
        Traceback (most recent call last):
        ...
        mastif.resources.errors.DriverNotFound: no driver 'acme.psu-y'; known: acme.psu-x
    """


class TransportError(ResourceError):
    """Bytes could not be moved: the connection failed, was refused or dropped.

    Example:
        >>> raise TransportError("connection to 10.0.0.5:5025 refused")
        Traceback (most recent call last):
        ...
        mastif.resources.errors.TransportError: connection to 10.0.0.5:5025 refused
    """


class TransportTimeout(TransportError):
    """No (complete) reply arrived within the allowed time.

    Example:
        >>> issubclass(TransportTimeout, TransportError)
        True
    """


class ProtocolError(ResourceError):
    """A reply arrived but could not be understood, or the device reported a command error.

    For example, a number was expected and text came back, or a SCPI error queue held an
    entry.

    Example:
        >>> raise ProtocolError("MEAS:CURR? returned 'OVLD', expected a number")
        Traceback (most recent call last):
        ...
        mastif.resources.errors.ProtocolError: MEAS:CURR? returned 'OVLD', expected a number
    """


class IdentityMismatch(ResourceError):
    """The connected device is not the one the station profile expects.

    Raised before any other operation, so a test never drives the wrong instrument or
    measures the wrong unit.

    Example:
        >>> raise IdentityMismatch("bench_psu: serial is 'B999', expected 'A123'")
        Traceback (most recent call last):
        ...
        mastif.resources.errors.IdentityMismatch: bench_psu: serial is 'B999', expected 'A123'
    """


class ResourceFault(ResourceError):
    """The device reports a fault, or its health check failed.

    Example:
        >>> raise ResourceFault("bench_psu: over-temperature protection tripped")
        Traceback (most recent call last):
        ...
        mastif.resources.errors.ResourceFault: bench_psu: over-temperature protection tripped
    """
