# Channels

These built-in resource drivers provide communication capabilities for DUTs.
Unlike a raw transport, a channel implements a resource contract such as `Shell`
or `MessageChannel`. See [Write a DUT type](../../../wiki/guides/write-a-dut.md)
for how a DUT declares its channels and a profile selects their drivers.

| Module | Driver ID | Responsibility |
|---|---|---|
| [UDP messages](udp.md) | `mastif.udp` | A datagram-backed message channel |
| [Line shell](shell.md) | `mastif.line-shell` | A prompt-based console |
| [SSH shell](ssh.md) | `mastif.ssh-shell` | SSH commands with exit codes and stderr |

## Built-in driver collection

::: mastif.resources.channels.BUILTIN_DRIVERS
