"""UDP messaging with request/response matching and subscriptions.

Why this exists:
    Many DUTs speak a message protocol over UDP: commands go out as datagrams, and
    replies, status broadcasts and streamed data come back on the same socket, often
    interleaved. A naive "send, then receive the next packet" breaks as soon as an
    unsolicited status message arrives between a command and its reply. This module
    reads continuously and routes each incoming datagram:

    - to the oldest waiting `request` whose matcher accepts it, and
    - to every subscriber, so monitors and loggers see all traffic.

Where it fits:
    `DatagramChannel` implements the built-in `MessageChannel` contract. A DUT declares
    ``ctrl: MessageChannel = channel()``, and the station profile maps it to
    ``{driver: mastif.udp, config: {transport: {kind: udp, host: ..., port: ...}}}``.
    A driver can also ask for ``io: DatagramChannel`` directly when its config has a
    `UdpConfig` transport.

Threading:
    One daemon reader thread per open channel; the public methods are thread-safe.
    Subscriber handlers run on the reader thread, so they must be quick. A handler
    that raises is logged and does not stop the reader.
"""

import logging
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from mastif.resources.errors import TransportError, TransportTimeout
from mastif.resources.transports.config import UdpConfig

type Handler = Callable[[bytes], None]
type Matcher = Callable[[bytes], bool]


@dataclass
class _Pending:
    """One `request` waiting for its reply.

    Example:
        ``_Pending(match=lambda m: m.startswith(b"TEMP "))`` until a matching datagram arrives.
    """

    match: Matcher
    done: threading.Event = field(default_factory=threading.Event)
    reply: bytes = b""


class DatagramChannel:
    """A UDP endpoint talking to one peer, implementing `MessageChannel`.

    Example:
        >>> from mastif_testing import FakeDatagramPeer
        >>> with FakeDatagramPeer(lambda msg: b"PONG " + msg) as peer:
        ...     ch = DatagramChannel(UdpConfig(host="127.0.0.1", port=peer.port))
        ...     ch.open()
        ...     reply = ch.request(b"42", match=lambda m: m.startswith(b"PONG"))
        ...     ch.close()
        >>> reply
        b'PONG 42'
    """

    def __init__(self, config: UdpConfig, logger: logging.Logger | None = None) -> None:
        """Prepare the channel; no socket exists until `open`.

        Args:
            config: Peer address and local binding.
            logger: Where to trace messages.

        Example:
            >>> DatagramChannel(UdpConfig(host="192.168.1.50", port=9000)).name
            '192.168.1.50:9000'
        """
        self.config = config
        self.name = f"{config.host}:{config.port}"
        self.log = logger or logging.getLogger("mastif.io")
        self._sock: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pending: list[_Pending] = []
        self._subscribers: list[Handler] = []

    @property
    def is_open(self) -> bool:
        """Whether the socket is bound and the reader is running.

        Example:
            ``ch.is_open`` is False until ``ch.open()``.
        """
        return self._sock is not None

    @property
    def local_port(self) -> int:
        """The local UDP port in use, useful when the OS picked it (``local_port: 0``).

        Raises:
            TransportError: If the channel is not open.

        Example:
            ``ch.local_port`` returns e.g. ``54012`` after `open`.
        """
        return self._require_sock().getsockname()[1]

    def open(self) -> None:
        """Bind the socket and start the reader thread; does nothing if already open.

        Raises:
            TransportError: If the local address can't be bound.

        Example:
            Called by the station when the channel's resource is opened.
        """
        if self._sock is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.config.local_host, self.config.local_port))
        except OSError as exc:
            sock.close()
            raise TransportError(f"{self.name}: cannot bind local port: {exc}") from exc
        sock.settimeout(0.1)
        self._sock = sock
        self._reader = threading.Thread(
            target=self._read_loop, name=f"mastif-udp-{self.name}", daemon=True
        )
        self._reader.start()
        self.log.debug("%s: opened on local port %d", self.name, self.local_port)

    def close(self) -> None:
        """Stop the reader and close the socket; safe to call repeatedly.

        Waiting requests fail with `TransportError` instead of hanging until timeout.

        Example:
            Called by the station when the run ends.
        """
        sock, self._sock = self._sock, None
        if sock is None:
            return
        if self._reader is not None:
            self._reader.join(timeout=1.0)
        sock.close()
        with self._lock:
            pending, self._pending = self._pending, []
        for p in pending:
            p.done.set()
        self.log.debug("%s: closed", self.name)

    def send(self, message: bytes) -> None:
        """Send one datagram to the peer without waiting for a reply.

        Args:
            message: The datagram payload.

        Raises:
            TransportError: If the channel is closed or the send fails.

        Example:
            ``ch.send(b"LED ON")``
        """
        sock = self._require_sock()
        self.log.debug("%s >> %r", self.name, message)
        try:
            sock.sendto(message, (self.config.host, self.config.port))
        except OSError as exc:
            raise TransportError(f"{self.name}: send failed: {exc}") from exc

    def request(
        self,
        message: bytes,
        match: Matcher,
        timeout: float = 1.0,
        retries: int = 0,
    ) -> bytes:
        """Send a message and return the first incoming datagram accepted by ``match``.

        The waiter is registered *before* sending, so a reply that arrives very fast is
        never missed. On timeout the message is re-sent up to ``retries`` more times.
        Datagrams the matcher rejects go to subscribers and other waiters as usual.

        Args:
            message: The request payload.
            match: Returns True for the datagram that answers this request.
            timeout: Seconds to wait per attempt.
            retries: Extra attempts after the first.

        Returns:
            The matching reply.

        Raises:
            TransportTimeout: If no matching reply arrives on any attempt.
            TransportError: If the channel is closed while waiting.

        Example:
            ``ch.request(b"TEMP?", match=lambda m: m.startswith(b"TEMP "), retries=2)``
        """
        pending = _Pending(match)
        with self._lock:
            self._pending.append(pending)
        try:
            for _ in range(retries + 1):
                self.send(message)
                if pending.done.wait(timeout):
                    if not self.is_open:
                        raise TransportError(f"{self.name}: closed while waiting for a reply")
                    return pending.reply
        finally:
            with self._lock:
                if pending in self._pending:
                    self._pending.remove(pending)
        raise TransportTimeout(
            f"{self.name}: no matching reply to {message!r} after {retries + 1} attempt(s)"
        )

    def subscribe(self, handler: Handler) -> Callable[[], None]:
        """Call ``handler`` with every incoming datagram until unsubscribed.

        Args:
            handler: Receives each payload; runs on the reader thread, so keep it quick.

        Returns:
            A function that removes the subscription.

        Example:
            ``stop = ch.subscribe(status_log.append)``, then later ``stop()``
        """
        with self._lock:
            self._subscribers.append(handler)

        def unsubscribe() -> None:
            """Remove this subscription; calling it twice is harmless.

            Example:
                ``unsubscribe()``
            """
            with self._lock:
                if handler in self._subscribers:
                    self._subscribers.remove(handler)

        return unsubscribe

    def _require_sock(self) -> socket.socket:
        """Return the socket, or raise if the channel is closed.

        Example:
            Guards `send` and `local_port`.
        """
        if self._sock is None:
            raise TransportError(f"{self.name}: not open")
        return self._sock

    def _read_loop(self) -> None:
        """Receive datagrams until closed and dispatch each one.

        Example:
            Runs on the ``mastif-udp-<peer>`` thread started by `open`.
        """
        while (sock := self._sock) is not None:
            try:
                data, _ = sock.recvfrom(65535)
            except TimeoutError:
                continue
            except OSError:
                if self._sock is None:
                    return
                self.log.exception("%s: receive failed", self.name)
                continue
            self.log.debug("%s << %r", self.name, data)
            self._dispatch(data)

    def _dispatch(self, data: bytes) -> None:
        """Hand one datagram to the oldest matching waiter and to every subscriber.

        Matcher or handler exceptions are logged and treated as "not interested", so a
        bug in one listener can't stop the channel.

        Example:
            ``self._dispatch(b"TEMP 41.5")`` completes a pending ``TEMP?`` request.
        """
        with self._lock:
            waiters = list(self._pending)
            handlers = list(self._subscribers)
        for p in waiters:
            if p.done.is_set():
                continue
            try:
                accepted = p.match(data)
            except Exception:
                self.log.exception("%s: matcher raised", self.name)
                accepted = False
            if accepted:
                p.reply = data
                p.done.set()
                break
        for handler in handlers:
            try:
                handler(data)
            except Exception:
                self.log.exception("%s: subscriber raised", self.name)
