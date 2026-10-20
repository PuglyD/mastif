"""Line-oriented text I/O: write a command line, read a reply line.

Why this exists:
    Most instrument and console protocols are text lines: send ``"MEAS:VOLT?\\n"``, get
    back ``"5.0021\\n"``. Each driver would otherwise repeat the same encoding,
    terminator and timeout handling. `LineIO` is that conversation in one interface. It
    is implemented over any byte stream (`StreamLineIO`) and over VISA (`VisaLineIO`,
    where the VISA library does the framing). Text drivers therefore work over TCP,
    serial or VISA without change.

Where it fits:
    A driver asks for ``io: LineIO`` in its ``__init__``. The station builds the right
    implementation from the profile's ``transport:`` block. `Scpi` wraps a `LineIO`
    for SCPI instruments. In tests, ``mastif_testing.FakeLineIO`` stands in with
    scripted replies.
"""

import logging
from typing import Any, Protocol, runtime_checkable

from mastif.resources.errors import TransportError, TransportTimeout
from mastif.resources.transports.config import LineSettings, VisaConfig
from mastif.resources.transports.stream import StreamTransport


@runtime_checkable
class LineIO(Protocol):
    """Send and receive lines of text.

    Example:
        A driver for a simple ASCII instrument::

            def __init__(self, cfg: Config, io: LineIO):
                self.io = io

            def temperature(self) -> Quantity:
                return float(self.io.query("TEMP?")) * degC
    """

    def open(self) -> None:
        """Open the underlying connection."""
        ...

    def close(self) -> None:
        """Close the underlying connection."""
        ...

    def write_line(self, line: str) -> None:
        """Send one line; the write terminator is added automatically."""
        ...

    def read_line(self, timeout: float | None = None) -> str:
        """Return the next line, without its terminator."""
        ...

    def query(self, line: str, timeout: float | None = None) -> str:
        """Send one line and return the next line received."""
        ...


class StreamLineIO:
    """`LineIO` over any `StreamTransport` (TCP, serial, or a fake stream).

    Example:
        Over a serial loopback, a query reads back its own echo::

            io = StreamLineIO(SerialTransport(SerialConfig(port="loop://")), LineSettings())
            io.open()
            assert io.query("PING") == "PING"
    """

    def __init__(self, stream: StreamTransport, settings: LineSettings) -> None:
        """Wrap a stream with line framing.

        Args:
            stream: The byte stream to talk over.
            settings: Terminators, encoding and default timeout.

        Example:
            ``StreamLineIO(TcpTransport(cfg), cfg)``, because `TcpConfig` is also a
            `LineSettings`.
        """
        self.stream = stream
        self.settings = settings

    def open(self) -> None:
        """Open the underlying stream.

        Example:
            Called by the station before the driver's own ``open()``.
        """
        self.stream.open()

    def close(self) -> None:
        """Close the underlying stream.

        Example:
            Called by the station after the driver's own ``close()``.
        """
        self.stream.close()

    def write_line(self, line: str) -> None:
        """Encode and send one line with the write terminator.

        Args:
            line: The text, without terminator.

        Raises:
            TransportError: If sending fails, or the text can't be encoded.

        Example:
            ``io.write_line("OUTP ON")`` sends ``b"OUTP ON\\n"`` with default settings.
        """
        s = self.settings
        try:
            data = (line + s.write_termination).encode(s.encoding)
        except UnicodeEncodeError as exc:
            raise TransportError(f"cannot encode {line!r} as {s.encoding}") from exc
        self.stream.write(data)

    def read_line(self, timeout: float | None = None) -> str:
        """Receive and decode the next line.

        Args:
            timeout: Seconds to wait; defaults to the configured timeout.

        Returns:
            The line without its terminator.

        Raises:
            TransportTimeout: If no complete line arrives in time.
            TransportError: If the bytes can't be decoded.

        Example:
            ``io.read_line()`` returns ``"5.0021"`` for the bytes ``b"5.0021\\n"``.
        """
        s = self.settings
        raw = self.stream.read_until(
            s.read_termination.encode(s.encoding), s.timeout if timeout is None else timeout
        )
        try:
            return raw.decode(s.encoding)
        except UnicodeDecodeError as exc:
            raise TransportError(f"cannot decode {raw!r} as {s.encoding}") from exc

    def query(self, line: str, timeout: float | None = None) -> str:
        """Send one line and return the reply line.

        Args:
            line: The command.
            timeout: Seconds to wait for the reply.

        Returns:
            The reply line.

        Example:
            ``io.query("MEAS:VOLT?")`` returns ``"5.0021"``.
        """
        self.write_line(line)
        return self.read_line(timeout)


class VisaLineIO:
    """`LineIO` over a VISA resource, using pyvisa (install the ``visa`` extra).

    VISA handles message framing itself, so this class only maps settings and errors.

    Example:
        Talking to a USB-TMC instrument (needs hardware and a VISA backend)::

            io = VisaLineIO(VisaConfig(resource="USB0::0x1234::0x5678::A123::INSTR"))
            io.open()
            print(io.query("*IDN?"))
    """

    def __init__(
        self,
        config: VisaConfig,
        logger: logging.Logger | None = None,
        resource_manager: Any = None,
    ) -> None:
        """Prepare the resource; nothing is opened until `open`.

        Args:
            config: Resource string, backend and line settings.
            logger: Where to trace I/O.
            resource_manager: A pyvisa ``ResourceManager``-like object. Pass a fake in
                tests; by default one is created on `open`.

        Example:
            >>> VisaLineIO(VisaConfig(resource="GPIB0::5::INSTR")).config.resource
            'GPIB0::5::INSTR'
        """
        self.config = config
        self.log = logger or logging.getLogger("mastif.io")
        self._rm = resource_manager
        self._res = None

    def open(self) -> None:
        """Open the VISA resource and apply terminators and timeout.

        Raises:
            TransportError: If pyvisa is missing or the resource can't be opened.

        Example:
            Called by the station before the driver's ``open()``.
        """
        if self._res is not None:
            return
        try:
            if self._rm is None:
                import pyvisa  # ty: ignore[unresolved-import]  # optional dependency

                self._rm = pyvisa.ResourceManager(self.config.backend)
            res = self._rm.open_resource(self.config.resource)
        except ImportError as exc:
            raise TransportError("VISA transport needs: pip install 'mastif[visa]'") from exc
        except Exception as exc:
            raise TransportError(f"{self.config.resource}: cannot open: {exc}") from exc
        res.timeout = int(self.config.timeout * 1000)
        res.read_termination = self.config.read_termination
        res.write_termination = self.config.write_termination
        res.encoding = self.config.encoding
        self._res = res
        self.log.debug("%s: opened", self.config.resource)

    def close(self) -> None:
        """Close the VISA resource; safe to call repeatedly.

        Example:
            Called by the station after the driver's ``close()``.
        """
        if self._res is not None:
            self._res.close()
            self._res = None
            self.log.debug("%s: closed", self.config.resource)

    def _call(self, op: str, *args: object) -> str:
        """Run one pyvisa operation, translating its errors into mastif errors.

        Any error whose text mentions a timeout becomes `TransportTimeout`. Matching on
        text avoids importing pyvisa's error codes, so this module works without
        pyvisa installed.

        Example:
            ``self._call("query", "*IDN?")``
        """
        if self._res is None:
            raise TransportError(f"{self.config.resource}: not open")
        try:
            return getattr(self._res, op)(*args)
        except Exception as exc:
            if "timeout" in str(exc).lower():
                raise TransportTimeout(f"{self.config.resource}: {exc}") from exc
            raise TransportError(f"{self.config.resource}: {exc}") from exc

    def write_line(self, line: str) -> None:
        """Send one line.

        Example:
            ``io.write_line("OUTP ON")``
        """
        self.log.debug("%s >> %r", self.config.resource, line)
        self._call("write", line)

    def read_line(self, timeout: float | None = None) -> str:
        """Read one message.

        Args:
            timeout: Ignored for VISA: the resource's configured timeout applies.

        Example:
            ``io.read_line()`` returns ``"5.0021"``.
        """
        reply = self._call("read")
        self.log.debug("%s << %r", self.config.resource, reply)
        return reply

    def query(self, line: str, timeout: float | None = None) -> str:
        """Send one line and read the reply.

        Example:
            ``io.query("*IDN?")`` returns ``"ACME,PSU-X,A123,1.4"``.
        """
        self.log.debug("%s >> %r", self.config.resource, line)
        reply = self._call("query", line)
        self.log.debug("%s << %r", self.config.resource, reply)
        return reply
