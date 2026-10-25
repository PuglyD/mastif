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
        transport: {kind: telnet, host: 10.0.0.9}
        transport: {kind: ssh, host: 192.168.1.60, username: root, key_file: ~/.ssh/id_ed25519}
        transport: {kind: native, library: acmedio, search_paths: ["C:/Program Files/Acme"]}
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


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


class TelnetConfig(LineSettings):
    """A Telnet connection, e.g. a switch matrix or a digital I/O box with a Telnet console.

    Telnet is TCP plus a little in-band negotiation, so this is a `TcpConfig` with a
    different default port and line endings, and an optional login. Lines default to
    ``"\\r\\n"``, the Telnet standard (RFC 854). Passwords are `SecretStr`, so they never
    appear in logs or reprs.

    Attributes:
        kind: Always ``"telnet"``.
        host: Hostname or IP address.
        port: TCP port; 23 is the Telnet default.
        connect_timeout: Seconds to wait for the connection, and for each prompt during
            ``open`` (login, password, ready).
        login_prompt: Text the server prints to ask for the user name, e.g. ``"login: "``.
            ``None`` means the server doesn't ask for a login.
        username: User name to send after ``login_prompt``.
        password_prompt: Text the server prints to ask for the password.
        password: Password to send after ``password_prompt``; ``None`` if none is asked.
        ready_prompt: Text the server prints once it is ready for commands, e.g. the end
            of a banner or a ``"> "`` prompt. ``open`` waits for it and discards
            everything before it, so greetings never reach the driver as a reply.
            ``None`` means nothing is waited for.

    Example:
        >>> cfg = TelnetConfig(host="10.0.0.9", login_prompt="login: ", username="admin")
        >>> cfg.port, cfg.write_termination
        (23, '\\r\\n')
        >>> TelnetConfig(host="h", username="admin")
        Traceback (most recent call last):
        ...
        pydantic_core._pydantic_core.ValidationError: 1 validation error for TelnetConfig
        ...
    """

    kind: Literal["telnet"] = "telnet"
    host: str
    port: int = Field(default=23, ge=1, le=65535)
    read_termination: str = "\r\n"
    write_termination: str = "\r\n"
    connect_timeout: float = Field(default=5.0, gt=0)
    login_prompt: str | None = None
    username: str | None = None
    password_prompt: str = "Password: "
    password: SecretStr | None = None
    ready_prompt: str | None = None

    @model_validator(mode="after")
    def _login_is_complete(self) -> Self:
        """Require ``login_prompt`` and ``username`` together, and a login before a password.

        Returns:
            The config unchanged.

        Raises:
            ValueError: If only one of ``login_prompt`` and ``username`` is set, or a
                password is given without them (reported as a validation error).

        Example:
            >>> TelnetConfig(host="h", login_prompt="login: ", username="u").username
            'u'
        """
        if (self.login_prompt is None) != (self.username is None):
            raise ValueError("login_prompt and username must be given together")
        if self.password is not None and self.username is None:
            raise ValueError("a password needs login_prompt and username")
        return self


class SshConfig(LineSettings):
    """An SSH connection, e.g. to a Linux DUT. Needs the ``ssh`` extra (``mastif[ssh]``).

    The same config serves command execution (`SshSession`) and an interactive shell
    stream (`SshStreamTransport`); the `LineSettings` fields apply to the stream.

    Host keys are checked against ``known_hosts``. ``strict`` (the default) refuses
    hosts whose key is not known yet, exactly like ``ssh -o StrictHostKeyChecking=yes``.
    ``accept_new`` trusts a host the first time and remembers it, like OpenSSH's
    ``accept-new``. A host whose key *changed* is always refused.

    If neither ``password`` nor ``key_file`` is given, the SSH agent and the default
    key files (``~/.ssh/id_*``) are tried.

    Attributes:
        kind: Always ``"ssh"``.
        host: Hostname or IP address.
        port: TCP port; 22 is the SSH default.
        username: User to log in as.
        password: Password, if password authentication is used.
        key_file: Path to a private key file (``~`` is expanded).
        key_passphrase: Passphrase of an encrypted ``key_file``.
        known_hosts: ``"strict"`` or ``"accept_new"``.
        known_hosts_file: A known-hosts file to use in addition to the user's own
            (``~/.ssh/known_hosts``). With ``accept_new``, new keys are saved here.
        connect_timeout: Seconds to wait for the connection and the SSH handshake.

    Example:
        >>> cfg = SshConfig(host="192.168.1.60", username="root")
        >>> cfg.port, cfg.known_hosts
        (22, 'strict')
        >>> SshConfig(host="h", username="u", password="pw")
        SshConfig(..., password=SecretStr('**********'), ...)
    """

    kind: Literal["ssh"] = "ssh"
    host: str
    port: int = Field(default=22, ge=1, le=65535)
    username: str
    password: SecretStr | None = None
    key_file: str | None = None
    key_passphrase: SecretStr | None = None
    known_hosts: Literal["strict", "accept_new"] = "strict"
    known_hosts_file: str | None = None
    connect_timeout: float = Field(default=10.0, gt=0)


class NativeConfig(BaseModel):
    """A vendor's native library (a Windows DLL or a shared object), called through ctypes.

    Some instruments are only reachable through the vendor's library: the library talks
    to the hardware, and the driver calls its functions. The library is a fact of the
    station (where it is installed, which version), so its location lives in the
    profile, never in driver code. Vendor libraries are never committed to a
    repository; each station installs its own.

    Attributes:
        kind: Always ``"native"``.
        library: The library's path, or its name (``"acmedio"`` finds ``acmedio.dll``,
            ``libacmedio.so`` or ``libacmedio.dylib`` in ``search_paths``, then on the
            system search path). ``~`` is expanded.
        search_paths: Folders searched for ``library``. On Windows they are also added
            to the DLL search path while the library loads, so the vendor's *dependent*
            DLLs in those folders are found.
        calling_convention: ``"cdecl"`` (the default, and the only one outside Windows)
            or ``"stdcall"`` (the ``WINAPI`` convention of many Windows vendor DLLs).
        thread_confined: Run every call on one dedicated thread. Many vendor libraries
            are not thread-safe or keep per-thread state; leave this on unless the
            vendor documents otherwise.

    Example:
        >>> cfg = NativeConfig(library="acmedio", search_paths=["C:/Program Files/Acme/bin"])
        >>> cfg.calling_convention, cfg.thread_confined
        ('cdecl', True)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["native"] = "native"
    library: str = Field(min_length=1)
    search_paths: tuple[str, ...] = ()
    calling_convention: Literal["cdecl", "stdcall"] = "cdecl"
    thread_confined: bool = True


type TransportConfig = Annotated[
    TcpConfig | SerialConfig | UdpConfig | VisaConfig | TelnetConfig | SshConfig | NativeConfig,
    Field(discriminator="kind"),
]
"""Any built-in transport config, selected by its ``kind`` field."""
