"""Tests for `mastif.resources.transports.telnet` against a real localhost Telnet server.

Telnet mixes option negotiation (``IAC`` sequences) into the data stream, so these
tests use a small but real Telnet server on a localhost socket rather than a fake
stream. They pin down that:

- negotiation never reaches the driver, and the client refuses every option
- negotiation arriving in the middle of a reply is removed without splitting the line
- an ``IAC`` byte the driver sends arrives as data (doubled on the wire)
- an optional login is performed during ``open``, with a clear timeout if a prompt
  never appears
- `StreamLineIO`, `Scpi` and ``mastif.line-shell`` work over Telnet unchanged
- connection failures and a server hanging up surface as `TransportError`
"""

import socket
import threading
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from mastif.resources import TransportError, TransportTimeout
from mastif.resources.channels import LineShell
from mastif.resources.transports import (
    DatagramChannel,
    LineIO,
    Scpi,
    StreamLineIO,
    StreamTransport,
    TelnetConfig,
    TelnetTransport,
    build_io,
)
from mastif.resources.transports.telnet import load_telnetlib

IAC, DONT, DO, WONT, WILL = 255, 254, 253, 252, 251
ECHO, SGA, NAWS = 1, 3, 31
GREETING = bytes([IAC, WILL, ECHO, IAC, WILL, SGA, IAC, DO, NAWS])

type Responder = Callable[[bytes], bytes | None]


class TelnetServer:
    """A one-connection Telnet server on localhost, driven by a responder function.

    It sends a negotiation greeting, optionally asks for a login, then answers each
    received line (CRLF-terminated, negotiation removed) with ``respond(line)``. A
    ``None`` reply makes the server hang up.

    Attributes:
        port: The listening port.
        negotiation: ``(command, option)`` pairs the client sent.
        lines: Data lines received after login.
        raw_data: Every data byte received, with ``IAC IAC`` unescaped.
    """

    def __init__(
        self,
        respond: Responder,
        login: tuple[bytes, bytes] | None = None,
        login_prompt: bytes = b"login: ",
    ) -> None:
        """Start listening and serving in a background thread."""
        self.respond = respond
        self.login = login
        self.login_prompt = login_prompt
        self.negotiation: list[tuple[int, int]] = []
        self.lines: list[bytes] = []
        self.raw_data = bytearray()
        self._pending = bytearray()
        self._data = bytearray()
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        """Accept one client and run the login and the command loop."""
        try:
            conn, _ = self._sock.accept()
        except OSError:
            return
        with conn:
            try:
                conn.sendall(GREETING)
                if self.login is not None:
                    user, password = self.login
                    conn.sendall(self.login_prompt)
                    if self._read_line(conn) != user:
                        return
                    conn.sendall(b"Password: ")
                    if self._read_line(conn) != password:
                        conn.sendall(b"\r\nLogin incorrect\r\n")
                        return
                    conn.sendall(b"\r\nWelcome\r\n")
                while (line := self._read_line(conn)) is not None:
                    self.lines.append(line)
                    reply = self.respond(line)
                    if reply is None:
                        return
                    conn.sendall(reply)
            except OSError:
                return

    def _read_line(self, conn: socket.socket) -> bytes | None:
        """Read until CRLF, recording and removing negotiation; ``None`` at EOF."""
        while (idx := self._data.find(b"\r\n")) < 0:
            chunk = conn.recv(1024)
            if not chunk:
                return None
            self._pending += chunk
            self._parse()
        line = bytes(self._data[:idx])
        del self._data[: idx + 2]
        return line

    def _parse(self) -> None:
        """Split pending bytes into data and negotiation, keeping partial sequences."""
        buf = self._pending
        i = 0
        while i < len(buf):
            if buf[i] != IAC:
                self._data.append(buf[i])
                self.raw_data.append(buf[i])
                i += 1
            elif i + 1 >= len(buf):
                break
            elif buf[i + 1] == IAC:
                self._data.append(IAC)
                self.raw_data.append(IAC)
                i += 2
            elif buf[i + 1] in (DO, DONT, WILL, WONT):
                if i + 2 >= len(buf):
                    break
                self.negotiation.append((buf[i + 1], buf[i + 2]))
                i += 3
            else:
                i += 2
        del buf[:i]

    def close(self) -> None:
        """Stop listening and wait for the serving thread."""
        self._sock.close()
        self._thread.join(timeout=2)


@pytest.fixture
def telnet_server():
    """Start `TelnetServer` instances on demand and close them after the test.

    Yields:
        A function taking `TelnetServer` arguments and returning a started server.
    """
    servers: list[TelnetServer] = []

    def start(respond: Responder, **kwargs: Any) -> TelnetServer:
        server = TelnetServer(respond, **kwargs)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()


def instrument(line: bytes) -> bytes | None:
    """Answer like a small SCPI instrument, with negotiation inside one reply."""
    if line == b"*IDN?":
        return b"ACME,SW-8,T100,1.0\r\n"
    if line == b"MEAS?":
        return b"1." + bytes([IAC, DO, SGA]) + b"5\r\n"
    if line == b"BYE":
        return None
    return b"OK\r\n"


def test_negotiation_is_stripped_and_every_option_refused(telnet_server):
    """Option negotiation never reaches the driver, and the client declines every option.

    A command client must not agree to options it doesn't implement (server-side echo,
    terminal size...). Leaking negotiation bytes into data would corrupt the first reply
    of every session.
    """
    server = telnet_server(instrument)
    tn = TelnetTransport(TelnetConfig(host="127.0.0.1", port=server.port))
    tn.open()

    tn.write(b"*IDN?\r\n")
    reply = tn.read_until(b"\r\n")
    tn.close()
    server.close()

    assert reply == b"ACME,SW-8,T100,1.0"
    assert {(DONT, ECHO), (DONT, SGA), (WONT, NAWS)} <= set(server.negotiation)


def test_negotiation_inside_a_reply_is_removed_without_splitting_the_line(telnet_server):
    """A negotiation sequence in the middle of a reply disappears from the data.

    Servers may negotiate at any moment, not just at connect time. The driver must still
    see one clean line, or numeric parsing fails intermittently.
    """
    server = telnet_server(instrument)
    io = StreamLineIO(
        TelnetTransport(TelnetConfig(host="127.0.0.1", port=server.port)),
        TelnetConfig(host="127.0.0.1"),
    )
    io.open()

    assert io.query("MEAS?") == "1.5"
    io.close()


def test_scpi_over_telnet_with_login(telnet_server):
    """`build_io` gives a working `Scpi` over Telnet, logging in during ``open``.

    This is the whole path a driver relies on: profile config, login, skipping the
    welcome banner (``ready_prompt``), line framing with CRLF, and SCPI identification.
    Without the ready prompt, the banner would be read as the reply to ``*IDN?``.
    """
    server = telnet_server(instrument, login=(b"admin", b"s3cret"))
    cfg = TelnetConfig(
        host="127.0.0.1",
        port=server.port,
        login_prompt="login: ",
        username="admin",
        password=SecretStr("s3cret"),
        ready_prompt="Welcome\r\n",
    )
    scpi = build_io(Scpi, cfg)
    assert isinstance(scpi, Scpi)
    scpi.open()

    identity = scpi.identify()
    scpi.close()

    assert (identity.vendor, identity.model, identity.serial) == ("ACME", "SW-8", "T100")


def test_iac_byte_sent_by_the_driver_arrives_as_data(telnet_server):
    """A 0xFF byte in outgoing data is escaped, so the server receives it as data.

    Without escaping, a binary payload containing 0xFF would be read by the server as
    the start of a command and corrupt the frame.
    """
    server = telnet_server(instrument)
    tn = TelnetTransport(TelnetConfig(host="127.0.0.1", port=server.port))
    tn.open()

    tn.write(b"\xffA\r\n")
    tn.read_until(b"\r\n")
    tn.close()
    server.close()

    assert server.lines[0] == b"\xffA"


def test_missing_login_prompt_times_out_clearly(telnet_server):
    """If the expected login prompt never appears, ``open`` raises `TransportTimeout`.

    A wrong ``login_prompt`` in a profile is a common mistake; the error must name the
    prompt it waited for instead of hanging or failing later on the first command.
    """
    server = telnet_server(instrument, login=(b"admin", b"x"), login_prompt=b"User: ")
    cfg = TelnetConfig(
        host="127.0.0.1",
        port=server.port,
        login_prompt="login: ",
        username="admin",
        connect_timeout=0.3,
    )
    tn = TelnetTransport(cfg)

    with pytest.raises(TransportTimeout, match="'login: ' prompt"):
        tn.open()
    assert not tn.is_open


def test_line_shell_runs_over_telnet(telnet_server):
    """``mastif.line-shell`` accepts a Telnet transport and runs commands through it.

    Terminal servers and lab boxes often expose their console over Telnet; the same DUT
    channel must work there as over serial.
    """

    def shell(line: bytes) -> bytes | None:
        return (b"" if not line else line + b"\r\n" + b"2.1\r\n") + b"# "

    server = telnet_server(shell)
    cfg = LineShell.Config.model_validate(
        {"transport": {"kind": "telnet", "host": "127.0.0.1", "port": server.port}, "prompt": "# "}
    )
    stream = build_io(StreamTransport, cfg.transport)
    assert isinstance(stream, TelnetTransport)
    stream.open()
    sh = LineShell(cfg, stream)
    sh.open()

    result = sh.execute("version")
    stream.close()

    assert result.output == "2.1"


def test_connection_refused_is_transport_error():
    """Connecting to a closed port raises `TransportError` naming the endpoint.

    The station turns this into a clear "can't reach <resource>" before any test runs.
    """
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    with pytest.raises(TransportError, match=f"telnet://127.0.0.1:{port}: cannot connect"):
        TelnetTransport(TelnetConfig(host="127.0.0.1", port=port, connect_timeout=1)).open()


def test_server_hanging_up_is_transport_error(telnet_server):
    """A server that closes the connection mid-conversation raises `TransportError`.

    It must not be mistaken for a slow reply (a timeout), because retrying won't help.
    """
    server = telnet_server(instrument)
    tn = TelnetTransport(TelnetConfig(host="127.0.0.1", port=server.port))
    tn.open()

    tn.write(b"BYE\r\n")
    with pytest.raises(TransportError) as caught:
        tn.read_until(b"\r\n", timeout=2)
    tn.close()

    # Depending on the OS, a hang-up arrives as an orderly close or as a reset.
    assert not isinstance(caught.value, TransportTimeout)
    assert "closed by peer" in str(caught.value) or "receive failed" in str(caught.value)


def test_telnet_config_defaults_and_login_validation():
    """`TelnetConfig` defaults to port 23 and CRLF, and rejects half-specified logins.

    A user name without a prompt to answer (or the reverse) is always a profile mistake,
    so it fails when the profile loads, not at the bench. Passwords never show in reprs.
    """
    cfg = TelnetConfig(host="h", login_prompt="login: ", username="u", password=SecretStr("pw"))

    assert (cfg.port, cfg.read_termination, cfg.write_termination) == (23, "\r\n", "\r\n")
    assert "pw" not in repr(cfg)
    with pytest.raises(ValidationError, match="together"):
        TelnetConfig(host="h", login_prompt="login: ")
    with pytest.raises(ValidationError, match="needs login_prompt"):
        TelnetConfig(host="h", password=SecretStr("pw"))


@pytest.mark.parametrize(
    ("want", "expected"),
    [(StreamTransport, TelnetTransport), (LineIO, StreamLineIO), (Scpi, Scpi)],
)
def test_build_io_over_telnet(want, expected):
    """Streams, line I/O and SCPI can all be built from a Telnet config.

    Args:
        want: The I/O type a driver asks for.
        expected: The class `build_io` must return.
    """
    assert isinstance(build_io(want, TelnetConfig(host="10.0.0.9")), expected)


def test_build_io_rejects_datagrams_over_telnet():
    """Telnet is a stream; asking for a datagram channel over it is a definition error."""
    from mastif.resources import DriverDefinitionError

    with pytest.raises(DriverDefinitionError, match="over a 'telnet' transport"):
        build_io(DatagramChannel, TelnetConfig(host="10.0.0.9"))


def test_telnetlib_loads_without_warnings():
    """The ``telnetlib`` module loads on every supported Python without a warning.

    The test suite turns warnings into errors, so this also guards the 3.12 path, where
    the stdlib module emits a deprecation warning that mastif suppresses on purpose.
    """
    assert hasattr(load_telnetlib(), "Telnet")
