"""``mastif.udp``: the built-in `MessageChannel` over UDP.

Why this exists:
    It lets a DUT declare ``ctrl: MessageChannel = channel()`` and have the station
    connect it to a UDP peer purely from the profile. All behaviour comes from
    `DatagramChannel`; this class only adapts it into a registered driver.
"""

from collections.abc import Callable

from mastif.resources.driver import DriverConfig, driver
from mastif.resources.std import MessageChannel
from mastif.resources.transports.config import UdpConfig
from mastif.resources.transports.datagram import DatagramChannel


@driver("mastif.udp", provides=[MessageChannel])
class UdpMessageChannel:
    """Message-based DUT communication over UDP.

    Example:
        >>> from mastif_testing import FakeDatagramPeer
        >>> from mastif.resources.transports import UdpConfig
        >>> with FakeDatagramPeer(lambda m: b"ok:" + m) as peer:
        ...     io = DatagramChannel(UdpConfig(host="127.0.0.1", port=peer.port))
        ...     ch = UdpMessageChannel(UdpMessageChannel.Config(transport=io.config), io)
        ...     io.open()
        ...     reply = ch.request(b"ping", match=lambda m: m.startswith(b"ok:"))
        ...     io.close()
        >>> reply
        b'ok:ping'
    """

    class Config(DriverConfig):
        """Where the DUT's UDP endpoint is.

        Example:
            ``{transport: {kind: udp, host: 192.168.1.50, port: 9000}}``
        """

        transport: UdpConfig

    def __init__(self, cfg: Config, io: DatagramChannel) -> None:
        """Keep the datagram channel the station injects (and opens).

        Example:
            The station calls ``UdpMessageChannel(cfg, io=DatagramChannel(cfg.transport))``.
        """
        self.io = io

    def send(self, message: bytes) -> None:
        """Send one datagram; see `DatagramChannel.send`.

        Example:
            ``board.ctrl.send(b"LED ON")``
        """
        self.io.send(message)

    def request(
        self,
        message: bytes,
        match: Callable[[bytes], bool],
        timeout: float = 1.0,
        retries: int = 0,
    ) -> bytes:
        """Send and wait for the matching reply; see `DatagramChannel.request`.

        Example:
            ``board.ctrl.request(b"TEMP?", match=lambda m: m.startswith(b"TEMP "))``
        """
        return self.io.request(message, match, timeout, retries)

    def subscribe(self, handler: Callable[[bytes], None]) -> Callable[[], None]:
        """Receive every incoming datagram; see `DatagramChannel.subscribe`.

        Example:
            ``stop = board.ctrl.subscribe(events.append)``
        """
        return self.io.subscribe(handler)
