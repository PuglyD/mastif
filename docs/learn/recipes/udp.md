# Implement a UDP request/reply protocol

**You have:** a device with a UDP control port, which answers requests and also sends messages of its own accord.

**You want:** to send a request and get *its* reply, without confusing that with anything else on the port.

!!! success "Works today"
    Everything on this page runs against the current code. It uses a loopback peer, with no hardware.

The difficulty with UDP is that a message arriving tells you nothing about why it was sent. It might be the reply to your request. It might be a late reply to an older one. It might be a status message that the device sends every second. `DatagramChannel` handles this by having you say what your reply looks like.

## A request and a reply

```python
from mastif.resources.transports import DatagramChannel, UdpConfig
from mastif_testing import FakeDatagramPeer


def respond(message: bytes) -> bytes | None:
    return b"CURRENT 0.180" if message == b"READ CURRENT" else None


with FakeDatagramPeer(respond) as peer:
    channel = DatagramChannel(UdpConfig(host="127.0.0.1", port=peer.port))
    channel.open()
    try:
        reply = channel.request(b"READ CURRENT", match=lambda data: data.startswith(b"CURRENT "))
        print(reply)  # b'CURRENT 0.180'
    finally:
        channel.close()
```

The `match` function is the key part. A background thread reads every datagram. The waiter gets registered **before** the request is sent, so that an instant reply can't slip past, and the first datagram which `match` accepts is your answer. Everything else goes to subscribers.

## Make your matcher strict

Matching on a prefix is fine for a small protocol like this. Now consider what happens if a reply is delayed. You send `READ CURRENT`, it times out, and you send it again. Then the first reply arrives late. Your second request accepts that old reply, and from then on, things are off by one.

If your protocol has transaction ids, use them, because this is exactly what they're for:

```python
import struct

from mastif.resources.transports import DatagramChannel, UdpConfig
from mastif_testing import FakeDatagramPeer


def respond(message: bytes) -> bytes:
    transaction = message[:2]
    return transaction + b"OK"


with FakeDatagramPeer(respond) as peer:
    channel = DatagramChannel(UdpConfig(host="127.0.0.1", port=peer.port))
    channel.open()
    try:
        transaction = struct.pack(">H", 42)
        reply = channel.request(
            transaction + b"READ",
            match=lambda data: data[:2] == transaction,
        )
        print(reply[2:])  # b'OK'
    finally:
        channel.close()
```

## Messages you didn't ask for

Devices often send notifications. Subscribe to get these, and keep your callback quick, since it runs on the channel's reading thread:

```python title="excerpt"
channel.subscribe(lambda message: log.info("device says: %r", message))
```

A subscriber that raises gets logged, and it doesn't break the channel.

## Validate after matching

Matching says that a datagram is your reply, not that its contents are valid. Parse it strictly, and put the actual bytes in any error:

```python
from mastif.kernel.units import Amps, A
from mastif.resources.errors import ProtocolError


def parse_current(reply: bytes) -> Amps:
    try:
        return float(reply.removeprefix(b"CURRENT ")) * A
    except ValueError:
        raise ProtocolError(f"bad current reply: {reply!r}") from None


print(parse_current(b"CURRENT 0.180"))  # 0.18 A
```

## UDP's promises, or lack of them

UDP doesn't guarantee delivery, order or uniqueness. `request` can resend on a timeout, but think about what that means. If the device acted on your first message and only the reply got lost, a resend makes it act twice. That's fine for a read. For a command, you'd want the device itself to recognise a repeated transaction id. There's more on this in [Failure propagation and recovery](../system-design/recovery.md).

## On a DUT

For a DUT's control port, there's a built-in channel driver, so that you won't have to write any of this plumbing:

```python title="on the DUT type"
ctrl: MessageChannel = channel()
```

```yaml title="under resources.dut.channels"
ctrl:
  driver: mastif.udp
  config:
    transport: {kind: udp, host: 192.0.2.50, port: 9000, local_port: 9001}
```

Your product's message format still belongs in your SDK, in a DUT type's methods, while the generic channel just moves bytes.

## See also

- [Communicating with a device](../../getting-started/tutorial/hardware-integration/communication.md).
- [ADR-0017](../../adr/0017-datagram-channel.md) and [ADR-0019](../../adr/0019-builtin-udp-channel.md).

**Next:** [Wrap a vendor DLL](native-library.md)
