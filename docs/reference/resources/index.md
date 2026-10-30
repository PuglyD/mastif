# Resources

The resources layer describes hardware capabilities, driver integration, and
communication. Start with [Resource concepts](../../wiki/resources.md) if these
boundaries are new to you, then choose the API you need below.

## Resource model

| Module | Responsibility |
|---|---|
| [Contracts](contracts.md) | Describe and validate capability interfaces |
| [Standard capabilities](std.md) | Built-in instrument and DUT interfaces |
| [Drivers and DUTs](driver.md) | Declare driver types, configuration, channels, and lifecycle hooks |
| [Identity and health](identity.md) | Report what is connected and its readiness |
| [Driver registry](registry.md) | Discover installed drivers and resolve their IDs |
| [Errors](errors.md) | Report definition, communication, and verification failures |

## Communication

- [Transports](transports/index.md): connection configuration, byte streams, line I/O,
  SCPI, datagrams, SSH, Telnet, native libraries, and I/O construction.
- [Channels](channels/index.md): built-in resource drivers implementing `Shell` and
  `MessageChannel` capabilities for DUT communication.

For composition and lifecycle coordination, continue to [Station](../station/index.md).
