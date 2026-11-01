# Resources

The resources layer connects the capabilities test code needs to the drivers and
communication mechanisms that provide them.

- [`contracts`](#mastif.resources.contracts) and [`std`](#mastif.resources.std)
  define capability interfaces; [`driver`](#mastif.resources.driver) declares implementations.
- [`identity`](#mastif.resources.identity) reports what is connected and its readiness;
  [`registry`](#mastif.resources.registry) discovers drivers.
- Transport modules provide [connection settings](#mastif.resources.transports.config),
  streams, protocol helpers, and [I/O construction](#mastif.resources.transports.factory).
- [`channels`](#mastif.resources.channels) supplies built-in message and shell drivers;
  [`errors`](#mastif.resources.errors) describes resource and communication failures.

Expand modules and classes in the right-hand TOC to browse public and private members.
For explanations and design decisions, see
[Resource concepts](../../learn/architecture/resources.md) and [Transports](../../learn/architecture/transports.md).
For composition and lifecycle coordination, continue to [Station](../station/index.md).

::: mastif.resources.contracts

::: mastif.resources.std

::: mastif.resources.driver

::: mastif.resources.identity

::: mastif.resources.registry

::: mastif.resources.errors

::: mastif.resources.transports.config

::: mastif.resources.transports.stream

::: mastif.resources.transports.lineio

::: mastif.resources.transports.scpi

::: mastif.resources.transports.datagram

::: mastif.resources.transports.telnet

::: mastif.resources.transports.ssh

::: mastif.resources.transports.native

::: mastif.resources.transports.factory

::: mastif.resources.channels
    options:
      members:
        - BUILTIN_DRIVERS
        - __all__

::: mastif.resources.channels.udp

::: mastif.resources.channels.shell

::: mastif.resources.channels.ssh
