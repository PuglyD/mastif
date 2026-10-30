# Transports

Transports and protocol helpers carry device commands and replies. Drivers receive
them through I/O injection. For the conceptual boundaries, see
[Transports](../../../wiki/transports.md).

| Module | Responsibility |
|---|---|
| [Configuration](config.md) | Typed connection and protocol settings |
| [Byte streams](stream.md) | Raw stream interfaces and TCP/serial implementations |
| [Line I/O](lineio.md) | Line-oriented communication and VISA integration |
| [SCPI](scpi.md) | Common instrument commands and response parsing |
| [Datagrams](datagram.md) | UDP messaging, requests, and subscriptions |
| [Telnet](telnet.md) | Telnet connection and negotiation |
| [SSH](ssh.md) | SSH command sessions and interactive streams |
| [Native libraries](native.md) | Vendor-library function calls and session handling |
| [I/O factory](factory.md) | Construct injected I/O from configuration |
