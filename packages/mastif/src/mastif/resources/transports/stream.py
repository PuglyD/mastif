"""Byte-stream transports: TCP sockets and serial ports.

Why this exists:
    Most instruments and DUT consoles are a byte stream underneath. A driver needs the
    same small set of operations whatever the medium: open, write bytes, read until a
    terminator, close, with timeouts that raise instead of hanging forever. This module
    gives TCP and serial that one shape (`StreamTransport`). A driver written against
    it therefore works over either, and so does a fake in tests.

Where it fits:
    Drivers rarely use streams directly. They usually ask for a `LineIO` or `Scpi`,
    which wrap a stream. A driver for a binary protocol can ask for ``io:
    StreamTransport`` instead. The station creates the stream from the profile's
    ``transport:`` block and opens it before calling the driver's ``open()``.

Every transport traces the bytes it moves at DEBUG level through an injected logger.
"""

import logging
import socket
import time
from typing import Protocol, runtime_checkable

from mastif.resources.errors import TransportError, TransportTimeout
from mastif.resources.transports.config import SerialConfig, TcpConfig


@runtime_checkable
class StreamTransport(Protocol):
    """A bidirectional byte stream with timeouts.

    Examples:
        A binary-protocol driver asking for a raw stream::

            @driver("acme.counter", provides=[Counter])
            class AcmeCounter:
                class Config(DriverConfig):
                    transport: TcpConfig

                def __init__(self, cfg: Config, io: StreamTransport):
                    self.io = io

                def read_count(self) -> int:
                    self.io.write(b"\\x01\\x10")
                    return int.from_bytes(self.io.read_exactly(4), "big")
    """

    @property
    def is_open(self) -> bool:
        """Whether the stream is currently open."""
        ...

    def open(self) -> None:
        """Connect or open the port."""
        ...

    def close(self) -> None:
        """Disconnect; safe to call when already closed."""
        ...

    def write(self, data: bytes | str) -> None:
        """Send all of ``data``; text is encoded, but no terminator is added."""
        ...

    def read_until(self, terminator: bytes | str, timeout: float | None = None) -> bytes:
        """Return bytes up to (excluding) ``terminator``, waiting at most ``timeout`` s."""
        ...

    def read_exactly(self, size: int, timeout: float | None = None) -> bytes:
        """Return exactly ``size`` bytes, waiting at most ``timeout`` s."""
        ...


class BufferedStream:
    """Shared read/timeout logic for byte streams; subclasses supply the raw I/O.

    A subclass implements `_connect`, `_disconnect`, `_send` and `_receive`. This base
    class adds buffering, terminator and length framing, deadline handling and I/O
    tracing, so every stream behaves the same.

    Examples:
        A minimal in-memory stream (how a test fake could be built)::

            class Canned(BufferedStream):
                def _connect(self): pass
                def _disconnect(self): pass
                def _send(self, data): pass
                def _receive(self, timeout): return b"OK\\n"
    """

    def __init__(
        self,
        name: str,
        timeout: float,
        logger: logging.Logger | None = None,
        encoding: str = "ascii",
    ) -> None:
        """Set up the shared state.

        Args:
            name: Human-readable endpoint name used in errors and traces.
            timeout: Default read timeout in seconds.
            logger: Where to trace I/O; defaults to the ``mastif.io`` logger.
            encoding: Encoding for text passed to `write` and `read_until`.

        Examples:
            Subclasses call ``super().__init__(f"{host}:{port}", config.timeout, logger)``.
        """
        self.name = name
        self.timeout = timeout
        self.log = logger or logging.getLogger("mastif.io")
        self.encoding = encoding
        self._buffer = bytearray()
        self._open = False

    @property
    def is_open(self) -> bool:
        """Whether the stream is currently open.

        Examples:
            ``stream.is_open`` is False until ``stream.open()`` succeeds.
        """
        return self._open

    def open(self) -> None:
        """Open the underlying connection; does nothing if already open.

        Raises:
            TransportError: If the connection cannot be established.

        Examples:
            ``stream.open()`` is called by the station before the driver's ``open()``.
        """
        if self._open:
            return
        self._connect()
        self._buffer.clear()
        self._open = True
        self.log.debug("%s: opened", self.name)

    def close(self) -> None:
        """Close the connection; safe to call repeatedly.

        Examples:
            ``stream.close()`` is called by the station after the driver's ``close()``.
        """
        if not self._open:
            return
        self._open = False
        try:
            self._disconnect()
        finally:
            self.log.debug("%s: closed", self.name)

    def write(self, data: bytes | str) -> None:
        """Send all of ``data``, exactly as given.

        Text is encoded with the stream's encoding. No terminator is added, because
        streams also carry binary protocols where an extra byte would corrupt a frame.
        For line-based protocols, ask for a `LineIO` instead: its ``write_line()``
        appends the configured terminator.

        Args:
            data: Bytes, or text to encode.

        Raises:
            TransportError: If the stream is closed, the send fails, or the text can't
                be encoded.

        Examples:
            ``stream.write(b"\\x01\\x10")`` or ``stream.write("*IDN?\\n")``
        """
        self._require_open()
        data = self._to_bytes(data)
        self.log.debug("%s >> %r", self.name, data)
        self._send(data)

    def read_until(self, terminator: bytes | str, timeout: float | None = None) -> bytes:
        """Return the bytes before the next ``terminator``, consuming the terminator.

        Bytes after the terminator stay buffered for the next read, so replies that
        arrive back-to-back in one packet are not lost.

        Args:
            terminator: The delimiter, e.g. ``b"\\n"``.
            timeout: Seconds to wait in total; defaults to the configured timeout.

        Returns:
            The bytes before the terminator.

        Raises:
            TransportTimeout: If no terminator arrives in time.
            TransportError: If the stream is closed or fails.

        Examples:
            ``stream.read_until(b"\\n")`` returns ``b"ACME,PSU-X,A123,1.4"``.
        """
        self._require_open()
        terminator = self._to_bytes(terminator)
        deadline = self._deadline(timeout)
        while (idx := self._buffer.find(terminator)) < 0:
            self._fill(deadline, f"terminator {terminator!r}")
        data = bytes(self._buffer[:idx])
        del self._buffer[: idx + len(terminator)]
        self.log.debug("%s << %r", self.name, data)
        return data

    def read_exactly(self, size: int, timeout: float | None = None) -> bytes:
        """Return exactly ``size`` bytes, for fixed-length binary frames.

        Args:
            size: Number of bytes to return.
            timeout: Seconds to wait in total; defaults to the configured timeout.

        Returns:
            The bytes.

        Raises:
            TransportTimeout: If fewer than ``size`` bytes arrive in time.
            TransportError: If the stream is closed or fails.

        Examples:
            ``header = stream.read_exactly(4)``
        """
        self._require_open()
        deadline = self._deadline(timeout)
        while len(self._buffer) < size:
            self._fill(deadline, f"{size} bytes")
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        self.log.debug("%s << %r", self.name, data)
        return data

    def _to_bytes(self, data: bytes | str) -> bytes:
        """Encode text with the stream's encoding; pass bytes through unchanged.

        Raises:
            TransportError: If the text can't be encoded.

        Examples:
            ``self._to_bytes("OK")`` returns ``b"OK"`` with ASCII encoding.
        """
        if isinstance(data, bytes):
            return data
        try:
            return data.encode(self.encoding)
        except UnicodeEncodeError as exc:
            raise TransportError(f"{self.name}: cannot encode {data!r} as {self.encoding}") from exc

    def _deadline(self, timeout: float | None) -> float:
        """Turn a relative timeout into an absolute monotonic deadline.

        Examples:
            ``self._deadline(None)`` uses the configured default timeout.
        """
        return time.monotonic() + (self.timeout if timeout is None else timeout)

    def _fill(self, deadline: float, waiting_for: str) -> None:
        """Receive one more chunk into the buffer before the deadline.

        Args:
            deadline: Absolute ``time.monotonic()`` deadline.
            waiting_for: Description for the timeout message.

        Raises:
            TransportTimeout: If the deadline passes first.

        Examples:
            Called in a loop by `read_until` until the terminator is buffered.
        """
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TransportTimeout(f"{self.name}: timed out waiting for {waiting_for}")
        chunk = self._receive(remaining)
        if not chunk:
            raise TransportTimeout(f"{self.name}: timed out waiting for {waiting_for}")
        self._buffer.extend(chunk)

    def _require_open(self) -> None:
        """Raise unless the stream is open.

        Examples:
            Guards every read and write, so using a closed stream fails with a clear message.
        """
        if not self._open:
            raise TransportError(f"{self.name}: not open")

    def _connect(self) -> None:
        """Open the raw connection (subclass hook).

        Examples:
            TCP creates and connects a socket here.
        """
        raise NotImplementedError

    def _disconnect(self) -> None:
        """Close the raw connection (subclass hook).

        Examples:
            TCP closes its socket here.
        """
        raise NotImplementedError

    def _send(self, data: bytes) -> None:
        """Send raw bytes (subclass hook).

        Examples:
            TCP calls ``socket.sendall(data)`` here.
        """
        raise NotImplementedError

    def _receive(self, timeout: float) -> bytes:
        """Receive at least one byte, or return ``b""`` on timeout (subclass hook).

        Examples:
            TCP calls ``socket.recv(4096)`` with ``timeout`` set on the socket.
        """
        raise NotImplementedError


class TcpTransport(BufferedStream):
    """A TCP client connection.

    Examples:
        Talking to a raw-SCPI LAN instrument (needs hardware)::

            tcp = TcpTransport(TcpConfig(host="10.0.0.5", port=5025))
            tcp.open()
            tcp.write(b"*IDN?\\n")
            print(tcp.read_until(b"\\n"))
            tcp.close()
    """

    def __init__(self, config: TcpConfig, logger: logging.Logger | None = None) -> None:
        """Prepare a connection; nothing happens on the network until `open`.

        Args:
            config: Host, port and timeouts.
            logger: Where to trace I/O.

        Examples:
            >>> TcpTransport(TcpConfig(host="127.0.0.1", port=5025)).name
            '127.0.0.1:5025'
        """
        super().__init__(f"{config.host}:{config.port}", config.timeout, logger, config.encoding)
        self.config = config
        self._sock: socket.socket | None = None

    def _connect(self) -> None:
        """Connect the socket, translating OS errors into `TransportError`.

        Examples:
            A refused connection raises ``TransportError("127.0.0.1:1: cannot connect: ...")``.
        """
        try:
            self._sock = socket.create_connection(
                (self.config.host, self.config.port), timeout=self.config.connect_timeout
            )
        except OSError as exc:
            raise TransportError(f"{self.name}: cannot connect: {exc}") from exc

    def _disconnect(self) -> None:
        """Close the socket.

        Examples:
            Called by `close`; afterwards the transport can be opened again.
        """
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def _send(self, data: bytes) -> None:
        """Send all bytes, translating OS errors.

        Examples:
            A dropped connection raises ``TransportError("...: send failed: ...")``.
        """
        assert self._sock is not None
        try:
            self._sock.sendall(data)
        except OSError as exc:
            raise TransportError(f"{self.name}: send failed: {exc}") from exc

    def _receive(self, timeout: float) -> bytes:
        """Receive one chunk, returning ``b""`` on timeout.

        Raises:
            TransportError: If the peer closed the connection or the read failed.

        Examples:
            Returns whatever the instrument sent so far, e.g. ``b"ACME,PSU"``.
        """
        assert self._sock is not None
        self._sock.settimeout(timeout)
        try:
            chunk = self._sock.recv(4096)
        except TimeoutError:
            return b""
        except OSError as exc:
            raise TransportError(f"{self.name}: receive failed: {exc}") from exc
        if not chunk:
            raise TransportError(f"{self.name}: connection closed by peer")
        return chunk


class SerialTransport(BufferedStream):
    """A serial port through pyserial (install the ``serial`` extra).

    Examples:
        A loopback port echoes what is written (no hardware needed)::

            port = SerialTransport(SerialConfig(port="loop://"))
            port.open()
            port.write(b"hello\\n")
            assert port.read_until(b"\\n") == b"hello"
    """

    def __init__(self, config: SerialConfig, logger: logging.Logger | None = None) -> None:
        """Prepare the port; nothing is opened until `open`.

        Args:
            config: Port name or URL, line settings and timeouts.
            logger: Where to trace I/O.

        Examples:
            >>> SerialTransport(SerialConfig(port="COM3")).name
            'COM3'
        """
        super().__init__(config.port, config.timeout, logger, config.encoding)
        self.config = config
        self._port = None

    def _connect(self) -> None:
        """Open the port with pyserial, translating its errors.

        Raises:
            TransportError: If pyserial is not installed or the port can't be opened.

        Examples:
            A missing port raises ``TransportError("COM9: cannot open: ...")``.
        """
        try:
            import serial  # optional dependency, imported on use
        except ImportError as exc:
            raise TransportError("serial transport needs: pip install 'mastif[serial]'") from exc
        try:
            self._port = serial.serial_for_url(
                self.config.port,
                baudrate=self.config.baudrate,
                bytesize=self.config.bytesize,
                parity=self.config.parity,
                stopbits=self.config.stopbits,
                timeout=self.config.timeout,
            )
        except (serial.SerialException, ValueError) as exc:
            raise TransportError(f"{self.name}: cannot open: {exc}") from exc

    def _disconnect(self) -> None:
        """Close the port.

        Examples:
            Called by `close`.
        """
        if self._port is not None:
            self._port.close()
            self._port = None

    def _send(self, data: bytes) -> None:
        """Write all bytes to the port.

        Examples:
            ``self._send(b"version\\r\\n")``
        """
        assert self._port is not None
        try:
            self._port.write(data)
            self._port.flush()
        except Exception as exc:
            raise TransportError(f"{self.name}: send failed: {exc}") from exc

    def _receive(self, timeout: float) -> bytes:
        """Read what is waiting (at least one byte), or ``b""`` on timeout.

        Examples:
            Returns console output as it arrives, e.g. ``b"2.1\\r\\n# "``.
        """
        assert self._port is not None
        self._port.timeout = timeout
        try:
            return self._port.read(max(1, self._port.in_waiting))
        except Exception as exc:
            raise TransportError(f"{self.name}: receive failed: {exc}") from exc
