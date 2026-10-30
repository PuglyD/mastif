"""Telnet transport: a byte stream over a Telnet connection, with optional login.

Why this exists:
    Many simple instruments and lab boxes (RF switch matrices, digital I/O modules,
    terminal servers) expose an ASCII command set over Telnet rather than a raw TCP
    socket. Telnet is TCP plus in-band option negotiation: the server sends ``IAC``
    (byte 255) sequences such as "DO ECHO" that must be answered and must never reach
    the driver as data. A plain `TcpTransport` would pass those bytes through and
    corrupt the first reply. This module handles them, plus an optional login, and
    gives drivers the same `StreamTransport` shape as TCP and serial. `LineIO`, `Scpi`
    and the ``mastif.line-shell`` channel therefore work over Telnet unchanged.

How it works:
    The protocol work is done by ``telnetlib``, the standard-library module that left
    the stdlib in Python 3.13. On 3.13+ the ``telnetlib-313-and-up`` package supplies
    the same module; on 3.12 the stdlib copy is used. It refuses every option the
    server proposes (the right default for a command client), strips negotiation from
    the data and escapes ``IAC`` bytes the driver sends. `TelnetTransport` adapts it to
    `BufferedStream`, which adds mastif's framing, deadlines and I/O tracing.

Where it fits:
    The station builds a `TelnetTransport` from a ``transport: {kind: telnet, ...}``
    block (see `mastif.resources.transports.factory`) whenever a driver asks for a
    stream, `LineIO` or `Scpi`.
"""

import logging
import warnings
from types import ModuleType
from typing import Any

from mastif.resources.errors import TransportError, TransportTimeout
from mastif.resources.transports.config import TelnetConfig
from mastif.resources.transports.stream import BufferedStream


def load_telnetlib() -> ModuleType:
    """Import the ``telnetlib`` module, without its 3.12 deprecation warning.

    On Python 3.12 the module is still in the standard library but warns on import;
    mastif depends on it deliberately (ADR-0032), so the warning is suppressed. On
    3.13+ the module comes from the ``telnetlib-313-and-up`` package, a core dependency.

    Returns:
        The ``telnetlib`` module.

    Raises:
        TransportError: If the module is missing, e.g. a 3.13+ environment installed
            without mastif's dependencies.

    Examples:
        >>> load_telnetlib().Telnet.__name__
        'Telnet'
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import telnetlib  # stdlib on 3.12, the telnetlib-313-and-up package on 3.13+
    except ImportError as exc:
        raise TransportError(
            "telnet transport needs the telnetlib module: pip install telnetlib-313-and-up"
        ) from exc
    return telnetlib


class TelnetTransport(BufferedStream):
    """A Telnet client connection, as a `StreamTransport`.

    Examples:
        Talking to a switch matrix with a Telnet console (needs hardware)::

            sw = TelnetTransport(TelnetConfig(host="10.0.0.9"))
            sw.open()
            sw.write(b"SETA=1\\r\\n")
            print(sw.read_until(b"\\r\\n"))
            sw.close()
    """

    def __init__(self, config: TelnetConfig, logger: logging.Logger | None = None) -> None:
        """Prepare a connection; nothing happens on the network until `open`.

        Args:
            config: Host, port, timeouts and optional login.
            logger: Where to trace I/O.

        Examples:
            >>> TelnetTransport(TelnetConfig(host="10.0.0.9")).name
            'telnet://10.0.0.9:23'
        """
        super().__init__(
            f"telnet://{config.host}:{config.port}", config.timeout, logger, config.encoding
        )
        self.config = config
        self._tn: Any = None

    def _connect(self) -> None:
        """Connect, log in if the config asks for it, then wait for ``ready_prompt``.

        Raises:
            TransportError: If the connection is refused or fails.
            TransportTimeout: If a login prompt doesn't appear in time.

        Examples:
            With ``login_prompt="login: "`` and ``username="admin"``, waits for
            ``login: ``, sends ``admin\\r\\n``, and likewise for the password.
        """
        telnetlib = load_telnetlib()
        cfg = self.config
        try:
            self._tn = telnetlib.Telnet(cfg.host, cfg.port, timeout=cfg.connect_timeout)
        except OSError as exc:
            raise TransportError(f"{self.name}: cannot connect: {exc}") from exc
        try:
            if cfg.login_prompt is not None and cfg.username is not None:
                self._answer(cfg.login_prompt, cfg.username)
                if cfg.password is not None:
                    self._answer(cfg.password_prompt, cfg.password.get_secret_value(), "***")
            if cfg.ready_prompt is not None:
                self._expect(cfg.ready_prompt)
        except BaseException:
            self._disconnect()
            raise

    def _answer(self, prompt: str, reply: str, shown: str | None = None) -> None:
        """Wait for one login prompt and send the reply with the write terminator.

        Args:
            prompt: The prompt to wait for.
            reply: The text to send.
            shown: What to write in the trace instead of ``reply`` (hides passwords).

        Raises:
            TransportTimeout: If the prompt doesn't appear within ``connect_timeout``.
            TransportError: If the connection fails meanwhile.

        Examples:
            ``self._answer("login: ", "admin")``
        """
        self._expect(prompt)
        self.log.debug("%s login >> %r", self.name, shown if shown is not None else reply)
        self._send(self._to_bytes(reply + self.config.write_termination))

    def _expect(self, prompt: str) -> None:
        """Read and discard everything up to and including ``prompt``.

        Args:
            prompt: The text to wait for.

        Raises:
            TransportTimeout: If it doesn't appear within ``connect_timeout``.
            TransportError: If the connection fails meanwhile.

        Examples:
            ``self._expect("Welcome\\r\\n")`` skips a login banner.
        """
        wait = self.config.connect_timeout
        expected = self._to_bytes(prompt)
        try:
            seen = self._tn.read_until(expected, wait)
        except (OSError, EOFError) as exc:
            raise TransportError(f"{self.name}: connection lost during login: {exc}") from exc
        if not seen.endswith(expected):
            raise TransportTimeout(
                f"{self.name}: no {prompt!r} prompt within {wait} s (received {seen[-80:]!r})"
            )
        self.log.debug("%s login << %r", self.name, seen)

    def _disconnect(self) -> None:
        """Close the connection.

        Examples:
            Called by `close`; afterwards the transport can be opened again.
        """
        if self._tn is not None:
            self._tn.close()
            self._tn = None

    def _send(self, data: bytes) -> None:
        """Send bytes; ``telnetlib`` doubles any ``IAC`` byte so it arrives as data.

        Raises:
            TransportError: If the send fails.

        Examples:
            ``self._send(b"SETA=1\\r\\n")``
        """
        assert self._tn is not None
        try:
            self._tn.write(data)
        except OSError as exc:
            raise TransportError(f"{self.name}: send failed: {exc}") from exc

    def _receive(self, timeout: float) -> bytes:
        """Receive at least one data byte, with negotiation removed; ``b""`` on timeout.

        ``read_some`` keeps reading until it has data, answering negotiation as it goes,
        so a packet holding only negotiation never looks like a timeout.

        Raises:
            TransportError: If the server closed the connection or the read failed.

        Examples:
            Returns ``b"1\\r\\n"`` for the bytes ``IAC WILL ECHO "1\\r\\n"``.
        """
        assert self._tn is not None
        sock = self._tn.get_socket()
        sock.settimeout(timeout)
        try:
            chunk = self._tn.read_some()
        except TimeoutError:
            return b""
        except (OSError, EOFError) as exc:
            raise TransportError(f"{self.name}: receive failed: {exc}") from exc
        if not chunk:
            raise TransportError(f"{self.name}: connection closed by peer")
        return chunk
