"""Connection settings for the built-in transports, as they appear in a station profile.

Why this exists:
    A driver should describe *what to say* to a device. Where the device is (an IP
    address, a COM port, a VISA resource string) is a fact about one station, and it
    belongs in that station's profile. These models are those facts, validated before
    anything is opened. A typo in a profile is then reported with the resource name
    instead of surfacing as a socket error at run time.

Where it fits:
    A driver's ``Config`` declares a ``transport`` field of one of these types (or the
    `TransportConfig` union to accept several). The station builds the matching
    transport object from it and injects it into the driver (see
    `mastif.resources.transports.factory`). In YAML the ``kind`` field selects the
    model::

        transport: {kind: tcp, host: 10.0.0.5, port: 5025}
        transport: {kind: serial, port: COM3, baudrate: 115200}
        transport: {kind: udp, host: 192.168.1.50, port: 9000}
        transport: {kind: visa, resource: "USB0::0x1234::0x5678::A123::INSTR"}
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LineSettings(BaseModel):
    """How text lines are framed and encoded on a stream or message-based instrument.

    Shared by the TCP, serial and VISA configs, because line-based protocols (SCPI,
    consoles, simple ASCII command sets) run over all three.

    Attributes:
        read_termination: Characters marking the end of an incoming line.
        write_termination: Characters appended to every outgoing line.
        encoding: Text encoding of the line content.
        timeout: Seconds to wait for a reply before raising `TransportTimeout`.

    Example:
        >>> LineSettings().read_termination == "\\n"
        True
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    read_termination: str = "\n"
    write_termination: str = "\n"
    encoding: str = "ascii"
    timeout: float = Field(default=2.0, gt=0)


class TcpConfig(LineSettings):
    """A TCP socket connection, e.g. a LAN instrument on a raw SCPI port.

    Attributes:
        kind: Always ``"tcp"``; selects this model in YAML.
        host: Hostname or IP address.
        port: TCP port (5025 is the usual raw-SCPI port).
        connect_timeout: Seconds to wait for the connection itself.

    Example:
        >>> TcpConfig(host="10.0.0.5", port=5025).kind
        'tcp'
    """

    kind: Literal["tcp"] = "tcp"
    host: str
    port: int = Field(ge=1, le=65535)
    connect_timeout: float = Field(default=5.0, gt=0)


class SerialConfig(LineSettings):
    """A serial port, e.g. a DUT console or an RS-232 instrument.

    ``port`` may also be a pyserial URL such as ``"loop://"`` (a loopback for tests) or
    ``"socket://host:port"``. Requires the ``serial`` extra (``pip install mastif[serial]``).

    Attributes:
        kind: Always ``"serial"``.
        port: Device name (``COM3``, ``/dev/ttyUSB0``) or pyserial URL.
        baudrate: Line speed in bits per second.
        bytesize: Data bits per character.
        parity: ``"N"``, ``"E"``, ``"O"``, ``"M"`` or ``"S"``.
        stopbits: 1, 1.5 or 2.

    Example:
        >>> SerialConfig(port="COM3", baudrate=115200).parity
        'N'
    """

    kind: Literal["serial"] = "serial"
    port: str
    baudrate: int = Field(default=9600, gt=0)
    bytesize: Literal[5, 6, 7, 8] = 8
    parity: Literal["N", "E", "O", "M", "S"] = "N"
    stopbits: float = 1

    @field_validator("stopbits")
    @classmethod
    def _valid_stopbits(cls, v: float) -> float:
        """Allow only the stop-bit counts serial hardware supports.

        Args:
            v: Requested stop bits.

        Returns:
            The value unchanged.

        Raises:
            ValueError: If not 1, 1.5 or 2 (reported as a validation error).

        Example:
            >>> SerialConfig(port="COM3", stopbits=1.5).stopbits
            1.5
        """
        if v not in (1, 1.5, 2):
            raise ValueError("stopbits must be 1, 1.5 or 2")
        return v


class UdpConfig(BaseModel):
    """A UDP peer, for message-based DUT protocols.

    Attributes:
        kind: Always ``"udp"``.
        host: The DUT's address.
        port: The DUT's UDP port.
        local_host: Local interface to bind; ``"0.0.0.0"`` means all interfaces.
        local_port: Local port to bind; ``0`` lets the OS choose. Set it when the DUT
            replies to a fixed port.

    Example:
        >>> UdpConfig(host="192.168.1.50", port=9000).local_port
        0
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["udp"] = "udp"
    host: str
    port: int = Field(ge=1, le=65535)
    local_host: str = "0.0.0.0"
    local_port: int = Field(default=0, ge=0, le=65535)


class VisaConfig(LineSettings):
    """A VISA resource (USB-TMC, GPIB, VXI-11, HiSLIP...) through pyvisa.

    Requires the ``visa`` extra (``pip install mastif[visa]``) and a VISA backend.

    Attributes:
        kind: Always ``"visa"``.
        resource: The VISA resource string.
        backend: pyvisa backend selector, e.g. ``"@py"``; empty for the system default.

    Example:
        >>> VisaConfig(resource="TCPIP0::10.0.0.5::INSTR").backend
        ''
    """

    kind: Literal["visa"] = "visa"
    resource: str
    backend: str = ""


type TransportConfig = Annotated[
    TcpConfig | SerialConfig | UdpConfig | VisaConfig, Field(discriminator="kind")
]
"""Any built-in transport config, selected by its ``kind`` field."""
