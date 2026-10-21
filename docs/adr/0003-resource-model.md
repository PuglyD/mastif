# ADR-0003: Resource model: contracts, drivers, DUT channels and the station

- **Status:** accepted
- **Date:** 2026-10-21

## Context

Organisations must be able to describe their own instruments and DUTs quickly, with no
mastif base classes to learn. Stations differ in hardware and wiring, yet the same tests
should run on all of them. Hardware failures must never leave a station half-open or
unsafe.

## Decision

- **Contracts are plain `typing.Protocol` classes.**
  - A contract needs no mastif import.
  - `@contract` is optional metadata. Today it only declares a safe-state action.
  - `contract_problems()` checks that each member exists and has compatible
    parameters, and reports structured `ProblemKind` values. The standard
    `runtime_checkable` check only looks at member names, so it isn't enough.
- **Drivers are classes marked `@driver(id, provides=[...])`; DUTs are marked `@dut`.**
  - Neither needs a base class.
  - The decorator validates the class when it is defined, then attaches a
    `DriverSpec`. Nothing is registered at import time.
  - The `Registry` collects drivers either from explicit class lists or from the
    `mastif.drivers` entry points.
- **Configuration and I/O are injected.**
  - A nested `Config(DriverConfig)` is validated from the profile, with
    `extra="forbid"`.
  - `__init__` parameters annotated with `StreamTransport`, `LineIO`, `Scpi` or
    `DatagramChannel` are built from `Config.transport`, and the station opens and
    closes them.
  - Tests inject fakes through the same path.
- **A DUT is a resource with named channels.**
  - Channels are declared as `name: Contract = channel()`.
  - Each channel is mapped in the profile to a channel driver, either one of the
    built-ins (`mastif.udp`, `mastif.line-shell`) or the org's own.
  - The station checks that the channel driver provides the declared contract, and
    attaches the channel before the DUT's `open()` runs.
- **Lifecycle hooks are optional:** `open`, `identify`, `health`, `safe_state`,
  `close`, and `children` for composite resources.
- **The station has two phases.**
  - `Station.build` validates everything without I/O.
  - The `ResourceManager` opens resources in profile order. For each one it opens the
    I/O, then the channels, then calls `open`, then `identify` and checks it against
    `expect`, then calls `health`.
  - If anything fails, it closes everything already opened.
  - It closes in reverse order and continues past errors.
  - `safe_state_all` never stops early.
- **Tests address hardware only by role.** A role maps to a resource,
  `resource.channel` or `resource.child`. `role_problems()` provides the station half
  of the engine's preflight.
- **The UDP `DatagramChannel` uses a plain socket and one reader thread.** The step-1
  plan suggested an asyncio loop on a background thread. A reader thread delivers the
  same request/response matching and fan-out with less machinery.

## Consequences

- An org can write a working driver with a decorator, a `Config` and a few methods,
  and test it with `mastif_testing.check_lifecycle` and the fakes.
- Profile mistakes surface at build time, with the resource and field named.
- `self.state` on DUTs is created dynamically. Authors should annotate
  `state: MyState` on the class so that type checkers know it exists.
- `shared` and `slot` are reserved in the profile model for multi-DUT stations. They
  are not yet enforced.

## Alternatives considered

- **Driver base classes / ABCs:** rejected. They couple every org type to mastif and
  push towards deep inheritance.
- **Registration at import time:** rejected. The set of available drivers would depend
  on import order, and tests would leak into each other.
- **A universal `send/receive` interface on DUTs:** rejected. A shell, a message
  channel and a register bus have genuinely different contracts.
