"""Build the I/O object a driver asks for, from the transport config in the profile.

Why this exists:
    A driver states what kind of I/O it wants by annotating an ``__init__`` parameter
    (``io: Scpi``). The station profile states where the device is (``transport: {kind:
    tcp, ...}``). This module connects the two. Drivers therefore never construct
    sockets themselves, which keeps them short and lets tests inject fakes in exactly
    the same place.

Where it fits:
    The driver builder (`mastif.resources.driver.build_resource`) calls `build_io` for
    each I/O parameter. `IO_TYPES` lists the types that can be injected.

What can be built from what:

    ===================  =====================================
    requested type       transport kinds
    ===================  =====================================
    ``StreamTransport``  tcp, serial
    ``LineIO``           tcp, serial, visa
    ``Scpi``             tcp, serial, visa
    ``DatagramChannel``  udp
    ===================  =====================================
"""

import logging

from mastif.resources.errors import DriverDefinitionError
from mastif.resources.transports.config import (
    SerialConfig,
    TcpConfig,
    TransportConfig,
    UdpConfig,
    VisaConfig,
)
from mastif.resources.transports.datagram import DatagramChannel
from mastif.resources.transports.lineio import LineIO, StreamLineIO, VisaLineIO
from mastif.resources.transports.scpi import Scpi
from mastif.resources.transports.stream import SerialTransport, StreamTransport, TcpTransport

IO_TYPES: tuple[type, ...] = (StreamTransport, LineIO, Scpi, DatagramChannel)
"""Types a driver may request as ``__init__`` parameters, built from its transport config."""


def _stream(config: TransportConfig, logger: logging.Logger | None) -> StreamTransport | None:
    """Build a byte stream for stream-capable configs, else return ``None``.

    Example:
        ``_stream(TcpConfig(host="h", port=1), None)`` returns a `TcpTransport`.
    """
    if isinstance(config, TcpConfig):
        return TcpTransport(config, logger)
    if isinstance(config, SerialConfig):
        return SerialTransport(config, logger)
    return None


def _line_io(config: TransportConfig, logger: logging.Logger | None) -> LineIO | None:
    """Build line I/O for line-capable configs, else return ``None``.

    Example:
        ``_line_io(VisaConfig(resource="GPIB0::5::INSTR"), None)`` returns a `VisaLineIO`.
    """
    if isinstance(config, VisaConfig):
        return VisaLineIO(config, logger)
    stream = _stream(config, logger)
    if stream is not None and isinstance(config, TcpConfig | SerialConfig):
        return StreamLineIO(stream, config)
    return None


def build_io(want: type, config: TransportConfig, logger: logging.Logger | None = None) -> object:
    """Build an unopened I/O object of the requested type from a transport config.

    Every object returned has ``open()`` and ``close()``. The station calls them around
    the driver's own lifecycle, so the driver finds its I/O ready in ``open()``.

    Args:
        want: One of `IO_TYPES`.
        config: The transport config from the station profile.
        logger: Where the I/O object traces traffic.

    Returns:
        The I/O object, not yet opened.

    Raises:
        DriverDefinitionError: If ``want`` can't be built from this transport kind,
            e.g. ``Scpi`` over UDP.

    Example:
        >>> io = build_io(Scpi, TcpConfig(host="10.0.0.5", port=5025))
        >>> type(io).__name__, type(io.io).__name__
        ('Scpi', 'StreamLineIO')
        >>> build_io(Scpi, UdpConfig(host="10.0.0.5", port=9000))
        Traceback (most recent call last):
        ...
        mastif.resources.errors.DriverDefinitionError: cannot provide Scpi over a 'udp' transport
    """
    built: object | None = None
    if want is StreamTransport:
        built = _stream(config, logger)
    elif want is LineIO:
        built = _line_io(config, logger)
    elif want is Scpi:
        line = _line_io(config, logger)
        built = Scpi(line) if line is not None else None
    elif want is DatagramChannel and isinstance(config, UdpConfig):
        built = DatagramChannel(config, logger)
    if built is None:
        raise DriverDefinitionError(
            f"cannot provide {want.__name__} over a {config.kind!r} transport"
        )
    return built
