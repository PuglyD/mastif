"""Fake transports for testing drivers and DUT code without hardware.

Why this exists:
    Driver code should be tested on every commit, but instruments sit in a lab. These
    fakes implement the same interfaces as the real transports, so a driver gets a
    fake injected exactly where the station would inject a real connection. Tests then
    script replies and assert on what the driver sent. Following `AGENTS.md`, mastif
    prefers these behavioural fakes to mocks: they fail the way real devices do (a
    missing reply times out), so tests catch real bugs.

Where it fits:
    - `FakeLineIO` replaces `LineIO`; wrap it in `Scpi` for SCPI drivers.
    - `FakeStream` replaces `StreamTransport` for binary protocols and consoles.
    - `FakeSshSession` replaces `SshSession`, for DUT code that runs commands over SSH.
    - `FakeDatagramPeer` is a real UDP peer on localhost, for testing `DatagramChannel`
      and UDP-based DUT code end to end.
"""

import socket
import threading
from collections import deque
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Self

from mastif.resources.errors import TransportError, TransportTimeout
from mastif.resources.std import ShellResult
from mastif.resources.transports.stream import BufferedStream

type Reply = str | list[str]


class FakeLineIO:
    """A scripted `LineIO`: replies come from a dictionary of known commands.

    When a line is written and it is a key in ``replies``, its reply is queued for the
    next `read_line`. A list of replies is served in order, and its last entry repeats
    afterwards. Reading with nothing queued raises `TransportTimeout`, as a silent
    instrument would.

    Attributes:
        written: Every line written, in order, for assertions.
        opened: How many times `open` was called.
        closed: How many times `close` was called.

    Example:
        >>> io = FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4", "MEAS:CURR?": ["0.10", "0.18"]})
        >>> io.query("MEAS:CURR?"), io.query("MEAS:CURR?"), io.query("MEAS:CURR?")
        ('0.10', '0.18', '0.18')
        >>> io.write_line("OUTP ON")
        >>> io.written
        ['MEAS:CURR?', 'MEAS:CURR?', 'MEAS:CURR?', 'OUTP ON']
    """

    def __init__(self, replies: Mapping[str, Reply] | None = None) -> None:
        """Create the fake with a reply script.

        Args:
            replies: Command line to reply, or to a list of successive replies.

        Example:
            ``FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4"})``
        """
        self._script = {
            k: deque([v] if isinstance(v, str) else v) for k, v in (replies or {}).items()
        }
        self._queue: deque[str] = deque()
        self.written: list[str] = []
        self.opened = 0
        self.closed = 0

    def open(self) -> None:
        """Count the open call.

        Example:
            >>> io = FakeLineIO(); io.open(); io.opened
            1
        """
        self.opened += 1

    def close(self) -> None:
        """Count the close call.

        Example:
            >>> io = FakeLineIO(); io.close(); io.closed
            1
        """
        self.closed += 1

    def feed(self, line: str) -> None:
        """Queue an unsolicited line, e.g. an asynchronous event from the device.

        Example:
            >>> io = FakeLineIO(); io.feed("ALARM 3"); io.read_line()
            'ALARM 3'
        """
        self._queue.append(line)

    def write_line(self, line: str) -> None:
        """Record the line and queue its scripted reply, if any.

        Example:
            >>> io = FakeLineIO({"PING": "PONG"}); io.write_line("PING"); io.read_line()
            'PONG'
        """
        self.written.append(line)
        replies = self._script.get(line)
        if replies:
            self._queue.append(replies.popleft() if len(replies) > 1 else replies[0])

    def read_line(self, timeout: float | None = None) -> str:
        """Return the next queued line.

        Raises:
            TransportTimeout: If nothing is queued, as with a silent device.

        Example:
            >>> FakeLineIO().read_line()
            Traceback (most recent call last):
            ...
            mastif.resources.errors.TransportTimeout: fake: no reply queued
        """
        if not self._queue:
            raise TransportTimeout("fake: no reply queued")
        return self._queue.popleft()

    def query(self, line: str, timeout: float | None = None) -> str:
        """Write a line and return the next queued reply.

        Example:
            >>> FakeLineIO({"*OPC?": "1"}).query("*OPC?")
            '1'
        """
        self.write_line(line)
        return self.read_line(timeout)


class FakeStream(BufferedStream):
    """A scripted `StreamTransport`: feed it bytes to read, inspect the bytes written.

    Reads share the real buffering code (`BufferedStream`), so framing behaves exactly
    as over TCP or serial.

    Attributes:
        sent: All bytes written, concatenated.

    Example:
        >>> s = FakeStream()
        >>> s.open()
        >>> s.feed(b"\\x00\\x00\\x01\\x00rest")
        >>> int.from_bytes(s.read_exactly(4), "big")
        256
        >>> s.write(b"\\x01")
        >>> s.sent
        b'\\x01'
    """

    def __init__(self, timeout: float = 0.05) -> None:
        """Create an empty fake stream.

        Args:
            timeout: Default read timeout; short, because nothing will ever arrive late.

        Example:
            ``FakeStream()``
        """
        super().__init__("fake-stream", timeout)
        self._incoming: deque[bytes] = deque()
        self.sent = b""

    def feed(self, data: bytes) -> None:
        """Make bytes available to read.

        Example:
            ``stream.feed(b"OK\\n")``
        """
        self._incoming.append(data)

    def _connect(self) -> None:
        """Nothing to connect.

        Example:
            Called by `open`.
        """

    def _disconnect(self) -> None:
        """Nothing to disconnect.

        Example:
            Called by `close`.
        """

    def _send(self, data: bytes) -> None:
        """Record sent bytes.

        Example:
            ``stream.write(b"x")`` appends ``b"x"`` to `sent`.
        """
        self.sent += data

    def _receive(self, timeout: float) -> bytes:
        """Hand out the next fed chunk, or ``b""`` (a timeout) if none.

        Example:
            Returns ``b"OK\\n"`` after ``feed(b"OK\\n")``.
        """
        return self._incoming.popleft() if self._incoming else b""


class FakeSshSession:
    """A scripted `SshSession`: each known command returns a canned result.

    A script value may be:

    - a ``str``: the command's output, with exit code 0
    - a `ShellResult`: full control over output, exit code and stderr (its ``command``
      is replaced by the command actually run)
    - an exception instance: raised when the command runs, e.g. a `TransportTimeout`
      to simulate a command that hangs

    Unknown commands behave like a real shell: exit code 127 and "command not found" on
    stderr. Running a command while closed raises `TransportError`, as the real session
    does.

    Attributes:
        ran: Every command run, in order, for assertions.
        opened: How many times `open` was called.
        closed: How many times `close` was called.

    Example:
        >>> ssh = FakeSshSession({"uname -r": "6.1.0\\n",
        ...                       "false": ShellResult(command="", output="", exit_code=1)})
        >>> ssh.open()
        >>> ssh.run("uname -r").output, ssh.run("false").exit_code, ssh.run("nope").exit_code
        ('6.1.0\\n', 1, 127)
        >>> ssh.ran
        ['uname -r', 'false', 'nope']
    """

    def __init__(self, commands: Mapping[str, str | ShellResult | Exception] | None = None) -> None:
        """Create the fake with a command script.

        Args:
            commands: Command line to its output, result or exception.

        Example:
            ``FakeSshSession({"cat /etc/hostname": "dut-07\\n"})``
        """
        self._script = dict(commands or {})
        self.name = "fake-ssh"
        self.ran: list[str] = []
        self.opened = 0
        self.closed = 0
        self._open = False

    @property
    def is_open(self) -> bool:
        """Whether `open` was called more recently than `close`.

        Example:
            >>> FakeSshSession().is_open
            False
        """
        return self._open

    def open(self) -> None:
        """Mark the session open and count the call.

        Example:
            >>> s = FakeSshSession(); s.open(); s.is_open, s.opened
            (True, 1)
        """
        self._open = True
        self.opened += 1

    def close(self) -> None:
        """Mark the session closed and count the call.

        Example:
            >>> s = FakeSshSession(); s.open(); s.close(); s.is_open, s.closed
            (False, 1)
        """
        self._open = False
        self.closed += 1

    def run(self, command: str, timeout: float | None = None) -> ShellResult:
        """Record the command and return (or raise) its scripted result.

        Raises:
            TransportError: If the session is not open, or the script says so.

        Example:
            >>> FakeSshSession().run("ls")
            Traceback (most recent call last):
            ...
            mastif.resources.errors.TransportError: fake-ssh: not open
        """
        if not self._open:
            raise TransportError(f"{self.name}: not open")
        self.ran.append(command)
        reply = self._script.get(command)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, ShellResult):
            return reply.model_copy(update={"command": command})
        if isinstance(reply, str):
            return ShellResult(command=command, output=reply, exit_code=0)
        name = command.split()[0] if command.split() else command
        return ShellResult(
            command=command, output="", exit_code=127, stderr=f"sh: {name}: command not found\n"
        )


class FakeDatagramPeer:
    """A real UDP peer on localhost that answers datagrams using a function.

    The responder gets each received payload and returns a reply payload, or ``None``
    for no reply. Use it as a context manager, so its socket and thread are cleaned up.

    Attributes:
        received: Every payload received, in order.

    Example:
        >>> import socket
        >>> with FakeDatagramPeer(lambda msg: msg.upper()) as peer:
        ...     s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ...     s.settimeout(2)
        ...     s.sendto(b"hi", ("127.0.0.1", peer.port))
        ...     reply = s.recv(100)
        ...     s.close()
        2
        >>> reply
        b'HI'
    """

    def __init__(self, responder: Callable[[bytes], bytes | None] = lambda _: None) -> None:
        """Bind to a free localhost port and start answering.

        Args:
            responder: Maps a received payload to a reply payload, or ``None``.

        Example:
            ``FakeDatagramPeer(lambda m: b"ACK")``
        """
        self.responder = responder
        self.received: list[bytes] = []
        self._last_sender: tuple[str, int] | None = None
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.settimeout(0.05)
        self._running = True
        self._thread = threading.Thread(target=self._serve, name="fake-udp-peer", daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        """The localhost port the peer listens on; point the channel's config at it.

        Example:
            ``UdpConfig(host="127.0.0.1", port=peer.port)``
        """
        return self._sock.getsockname()[1]

    def push(self, message: bytes) -> None:
        """Send an unsolicited datagram to whoever last sent to the peer.

        Use it to simulate status broadcasts arriving between requests and replies.

        Raises:
            TransportError: If nobody has sent anything to the peer yet.

        Example:
            ``peer.push(b"STATUS OK")``
        """
        if self._last_sender is None:
            raise TransportError("fake peer: no client address known yet")
        self._sock.sendto(message, self._last_sender)

    def close(self) -> None:
        """Stop answering and release the port.

        Example:
            Called automatically when the ``with`` block ends.
        """
        self._running = False
        self._thread.join(timeout=1.0)
        self._sock.close()

    def __enter__(self) -> Self:
        """Return the running peer.

        Example:
            ``with FakeDatagramPeer() as peer: ...``
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the peer.

        Example:
            Runs when the ``with`` block ends, even after an exception.
        """
        self.close()

    def _serve(self) -> None:
        """Receive datagrams and answer each one via the responder.

        Example:
            Runs on the ``fake-udp-peer`` thread.
        """
        while self._running:
            try:
                data, sender = self._sock.recvfrom(65535)
            except TimeoutError:
                continue
            except OSError:
                return
            self._last_sender = sender
            self.received.append(data)
            reply = self.responder(data)
            if reply is not None:
                self._sock.sendto(reply, sender)
