"""Built-in transports: how bytes and messages reach instruments and DUTs.

Drivers normally don't construct these. They annotate an ``__init__`` parameter with
the type they want (`StreamTransport`, `LineIO`, `Scpi`, `DatagramChannel`), and the
station builds it from the ``transport:`` block of the station profile (see `build_io`).

Example:
    >>> from mastif.resources.transports import Scpi, TcpConfig, build_io
    >>> isinstance(build_io(Scpi, TcpConfig(host="10.0.0.5", port=5025)), Scpi)
    True
"""

from mastif.resources.transports.config import (
    LineSettings,
    SerialConfig,
    TcpConfig,
    TransportConfig,
    UdpConfig,
    VisaConfig,
)
from mastif.resources.transports.datagram import DatagramChannel
from mastif.resources.transports.factory import IO_TYPES, build_io
from mastif.resources.transports.lineio import LineIO, StreamLineIO, VisaLineIO
from mastif.resources.transports.scpi import Scpi
from mastif.resources.transports.stream import (
    BufferedStream,
    SerialTransport,
    StreamTransport,
    TcpTransport,
)

__all__ = [
    "IO_TYPES",
    "BufferedStream",
    "DatagramChannel",
    "LineIO",
    "LineSettings",
    "Scpi",
    "SerialConfig",
    "SerialTransport",
    "StreamLineIO",
    "StreamTransport",
    "TcpConfig",
    "TcpTransport",
    "TransportConfig",
    "UdpConfig",
    "VisaConfig",
    "VisaLineIO",
    "build_io",
]
