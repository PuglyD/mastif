"""Unit tests for `mastif.resources.transports`.

Transports are where tests meet real I/O, so these tests use real localhost sockets
and pyserial's loopback port where possible. They pin down framing (terminators,
fixed lengths, back-to-back replies), timeouts that raise instead of hanging, error
translation, SCPI parsing, UDP request matching among unsolicited traffic, and which
I/O types can be built from which transport kinds.
"""

import socket
import threading
import time

import pytest
from pydantic import ValidationError

from mastif.resources import DriverDefinitionError, ProtocolError, TransportError, TransportTimeout
from mastif.resources.transports import (
    DatagramChannel,
    LineIO,
    LineSettings,
    Scpi,
    SerialConfig,
    SerialTransport,
    StreamLineIO,
    StreamTransport,
    TcpConfig,
    TcpTransport,
    UdpConfig,
    VisaConfig,
    VisaLineIO,
    build_io,
)
from mastif_testing import FakeDatagramPeer, FakeLineIO, FakeStream


@pytest.fixture
def tcp_server():
    """A one-connection localhost TCP server that sends canned bytes after each receive.

    Yields:
        ``(port, script)`` where ``script`` is a list the test fills with byte strings to
        send back, one per received chunk.
    """
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    script: list[bytes] = []

    def serve():
        conn, _ = server.accept()
        with conn:
            while True:
                try:
                    data = conn.recv(1024)
                except OSError:
                    return
                if not data:
                    return
                if script:
                    conn.sendall(script.pop(0))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield server.getsockname()[1], script
    server.close()


def test_tcp_reads_line_and_keeps_rest_buffered(tcp_server):
    """Two replies arriving in one packet are returned by two reads, none lost."""
    port, script = tcp_server
    script.append(b"first\nsecond\n")
    tcp = TcpTransport(TcpConfig(host="127.0.0.1", port=port))
    tcp.open()

    tcp.write("go\n")
    first, second = tcp.read_until("\n"), tcp.read_until(b"\n")
    tcp.close()

    assert (first, second) == (b"first", b"second")


def test_tcp_read_times_out_instead_of_hanging(tcp_server):
    """A device that never answers raises TransportTimeout after the timeout."""
    port, _ = tcp_server
    tcp = TcpTransport(TcpConfig(host="127.0.0.1", port=port, timeout=0.1))
    tcp.open()

    start = time.monotonic()
    with pytest.raises(TransportTimeout):
        tcp.read_until(b"\n")
    tcp.close()

    assert time.monotonic() - start < 1.0


def test_tcp_connection_refused_is_transport_error():
    """Connecting to a closed port raises TransportError, not a raw OSError."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    with pytest.raises(TransportError, match="cannot connect"):
        TcpTransport(TcpConfig(host="127.0.0.1", port=port, connect_timeout=0.5)).open()


def test_closed_stream_refuses_io():
    """Using a stream before `open` fails with a clear message."""
    with pytest.raises(TransportError, match="not open"):
        FakeStream().write(b"x")


def test_stream_write_encodes_text_without_adding_terminator():
    """Text is encoded, but nothing is appended: binary framing stays intact."""
    s = FakeStream()
    s.open()

    s.write("AB")

    assert s.sent == b"AB"


def test_read_exactly_waits_for_all_bytes():
    """Fixed-length frames split across chunks are reassembled."""
    s = FakeStream()
    s.open()
    s.feed(b"\x01\x02")
    s.feed(b"\x03\x04\x05")

    assert s.read_exactly(4) == b"\x01\x02\x03\x04"


def test_serial_loopback_round_trip():
    """The serial transport works end to end over pyserial's ``loop://`` port."""
    io = StreamLineIO(SerialTransport(SerialConfig(port="loop://", timeout=0.5)), LineSettings())
    io.open()

    reply = io.query("PING")
    io.close()

    assert reply == "PING"


def test_serial_bad_port_is_transport_error():
    """A port that doesn't exist raises TransportError."""
    with pytest.raises(TransportError):
        SerialTransport(SerialConfig(port="definitely-not-a-port")).open()


def test_serial_config_rejects_odd_stopbits():
    """Only 1, 1.5 and 2 stop bits exist on real hardware."""
    with pytest.raises(ValidationError):
        SerialConfig(port="COM1", stopbits=3)


def test_line_io_uses_configured_terminators():
    """`write_line` appends the write terminator and `read_line` strips the read one."""
    s = FakeStream()
    s.open()
    s.feed(b"5.0\r\n")
    io = StreamLineIO(s, LineSettings(write_termination="\r", read_termination="\r\n"))

    reply = io.query("MEAS?")

    assert (s.sent, reply) == (b"MEAS?\r", "5.0")


def test_scpi_query_float_rejects_overflow_marker():
    """SCPI's 9.9E37 overflow marker is a protocol error, never a huge reading."""
    with pytest.raises(ProtocolError, match="overflow"):
        Scpi(FakeLineIO({"MEAS?": "9.9E37"})).query_float("MEAS?")


def test_scpi_identify_tolerates_short_reply():
    """An ``*IDN?`` reply with missing fields yields None for them instead of failing."""
    idn = Scpi(FakeLineIO({"*IDN?": "ACME,PSU-X"})).identify()

    assert (idn.vendor, idn.model, idn.serial) == ("ACME", "PSU-X", None)


def test_scpi_check_errors_raises_after_rejected_command():
    """With ``check_errors``, a command the instrument rejects raises immediately."""
    io = FakeLineIO({"SYST:ERR?": ['-113,"Undefined header"', '0,"No error"']})

    with pytest.raises(ProtocolError, match="Undefined header"):
        Scpi(io, check_errors=True).write("BOGUS")


def test_scpi_wait_requires_one():
    """``*OPC?`` must answer 1; anything else is a protocol error."""
    with pytest.raises(ProtocolError):
        Scpi(FakeLineIO({"*OPC?": "0"})).wait()


def test_datagram_request_matches_reply_among_unsolicited_traffic():
    """A status broadcast arriving before the reply goes to subscribers, not the request."""

    def responder(msg: bytes) -> bytes | None:
        if msg == b"TEMP?":
            peer.push(b"STATUS ok")
            return b"TEMP 41.5"
        return None

    with FakeDatagramPeer(responder) as peer:
        ch = DatagramChannel(UdpConfig(host="127.0.0.1", port=peer.port))
        ch.open()
        seen: list[bytes] = []
        ch.subscribe(seen.append)

        reply = ch.request(b"TEMP?", match=lambda m: m.startswith(b"TEMP "))
        time.sleep(0.05)
        ch.close()

    assert reply == b"TEMP 41.5"
    assert b"STATUS ok" in seen


def test_datagram_request_retries_then_times_out():
    """With no reply, the request is sent 1 + retries times and then raises."""
    with FakeDatagramPeer() as peer:
        ch = DatagramChannel(UdpConfig(host="127.0.0.1", port=peer.port))
        ch.open()

        with pytest.raises(TransportTimeout):
            ch.request(b"X", match=lambda m: True, timeout=0.05, retries=2)
        time.sleep(0.05)
        ch.close()

    assert peer.received == [b"X", b"X", b"X"]


def test_datagram_unsubscribe_stops_delivery():
    """After unsubscribing, the handler no longer receives messages."""
    with FakeDatagramPeer(lambda m: m) as peer:
        ch = DatagramChannel(UdpConfig(host="127.0.0.1", port=peer.port))
        ch.open()
        seen: list[bytes] = []
        stop = ch.subscribe(seen.append)
        ch.request(b"one", match=lambda m: m == b"one")
        stop()
        ch.request(b"two", match=lambda m: m == b"two")
        ch.close()

    assert seen == [b"one"]


def test_datagram_failing_subscriber_does_not_stop_channel():
    """A handler that raises is logged; the channel keeps answering requests."""

    def broken(_: bytes) -> None:
        raise RuntimeError("bug in a monitor")

    with FakeDatagramPeer(lambda m: m) as peer:
        ch = DatagramChannel(UdpConfig(host="127.0.0.1", port=peer.port))
        ch.open()
        ch.subscribe(broken)

        replies = [ch.request(b"a", match=lambda m: m == b"a") for _ in range(2)]
        ch.close()

    assert replies == [b"a", b"a"]


def test_datagram_send_when_closed_raises():
    """Sending on a closed channel fails clearly."""
    with pytest.raises(TransportError, match="not open"):
        DatagramChannel(UdpConfig(host="127.0.0.1", port=9)).send(b"x")


class _FakeVisaResource:
    """Stands in for a pyvisa resource object."""

    def __init__(self, fail_with: str | None = None):
        self.fail_with = fail_with
        self.closed = False
        self.timeout = 0
        self.read_termination = self.write_termination = self.encoding = ""

    def query(self, line: str) -> str:
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        return "ACME,SA-1,S1,2.0"

    def write(self, line: str) -> None: ...

    def read(self) -> str:
        return ""

    def close(self) -> None:
        self.closed = True


class _FakeResourceManager:
    """Stands in for ``pyvisa.ResourceManager``."""

    def __init__(self, resource: _FakeVisaResource):
        self.resource = resource

    def open_resource(self, name: str) -> _FakeVisaResource:
        return self.resource


def test_visa_line_io_applies_settings_and_queries():
    """VISA resources get timeout and terminators from the config, then answer queries."""
    res = _FakeVisaResource()
    io = VisaLineIO(
        VisaConfig(resource="R", timeout=1.5), resource_manager=_FakeResourceManager(res)
    )
    io.open()

    reply = io.query("*IDN?")
    io.close()

    assert (reply, res.timeout, res.closed) == ("ACME,SA-1,S1,2.0", 1500, True)


def test_visa_timeout_text_becomes_transport_timeout():
    """Timeout errors from pyvisa are translated without importing pyvisa."""
    res = _FakeVisaResource(fail_with="VI_ERROR_TMO (-1073807339): Timeout expired")
    io = VisaLineIO(VisaConfig(resource="R"), resource_manager=_FakeResourceManager(res))
    io.open()

    with pytest.raises(TransportTimeout):
        io.query("*IDN?")


@pytest.mark.parametrize(
    ("want", "config", "expected"),
    [
        (StreamTransport, TcpConfig(host="h", port=1), TcpTransport),
        (StreamTransport, SerialConfig(port="COM1"), SerialTransport),
        (LineIO, TcpConfig(host="h", port=1), StreamLineIO),
        (LineIO, VisaConfig(resource="R"), VisaLineIO),
        (Scpi, SerialConfig(port="COM1"), Scpi),
        (DatagramChannel, UdpConfig(host="h", port=1), DatagramChannel),
    ],
)
def test_build_io_supported_combinations(want, config, expected):
    """Each I/O type is built from every transport kind that can carry it.

    Args:
        want: The I/O type a driver requests.
        config: The transport config from the profile.
        expected: The concrete class that must be built.
    """
    assert type(build_io(want, config)) is expected


@pytest.mark.parametrize(
    ("want", "config"),
    [
        (Scpi, UdpConfig(host="h", port=1)),
        (DatagramChannel, TcpConfig(host="h", port=1)),
        (StreamTransport, VisaConfig(resource="R")),
    ],
)
def test_build_io_rejects_impossible_combinations(want, config):
    """Combinations that can't work are reported as driver definition errors.

    Args:
        want: The I/O type a driver requests.
        config: A transport config that can't carry it.
    """
    with pytest.raises(DriverDefinitionError):
        build_io(want, config)
