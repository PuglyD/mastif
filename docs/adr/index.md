# Architecture Decision Records

An **ADR** records one decision: the problem it solves, from first principles; where it
sits in the system; the abstractions, data flow and errors; and why the alternatives
were rejected. Every module has its own ADR. Cross-cutting decisions have theirs too.
The format is defined in [the template](0000-template.md), and the rules are in
`AGENTS.md` → *Documentation*.

**New here?** Read ADR-0001 and ADR-0002 first. Then read the ADRs for the layer you are
working in, bottom-up.

## Cross-cutting

| ADR | Decision | One-line summary |
|---|---|---|
| [0001](0001-layered-architecture.md) | Layered architecture | Seven layers, dependencies point down only, org code is plugged in via entry points. |
| [0002](0002-error-model.md) | Error model | One typed hierarchy under `MastifError`; the type says what happened, the message says where; no sentinels. |

## Kernel: the shared vocabulary

| ADR | Module | One-line summary |
|---|---|---|
| [0003](0003-units.md) | `kernel.units` | Values carry their unit end to end; RF-correct dB arithmetic. |
| [0004](0004-limits-and-evaluation.md) | `kernel.limits` | Passing and warning ranges; `evaluate` is the single source of PASS/WARN/FAIL. |
| [0005](0005-verdicts-and-aggregation.md) | `kernel.verdict` | Six verdicts; worst child wins; ERROR is not FAIL. |
| [0006](0006-results.md) | `kernel.results` | Measurements, checks and tables that compute their own verdicts. |
| [0007](0007-identifiers.md) | `kernel.ids` | Run ids, slot ids and plan positions for full provenance. |

## Infra: settings, logging and versions

| ADR | Module | One-line summary |
|---|---|---|
| [0026](0026-settings.md) | `infra.config` | One Dynaconf settings object, built once and passed explicitly; typed sections. |
| [0027](0027-logging.md) | `infra.logs` | Operator console, complete rotating file, tables as tables, TRACE/SUCCESS levels. |
| [0028](0028-version-information.md) | `infra.version` | Package version plus git state, embedded in wheels or captured live. |
| [0029](0029-bootstrap.md) | `infra.bootstrap` | The one start-up call: settings, then logging, then version. |

## Resources: describing and talking to hardware

| ADR | Module | One-line summary |
|---|---|---|
| [0008](0008-contracts.md) | `resources.contracts` | Capabilities as plain Protocols, checked structurally including parameters. |
| [0009](0009-standard-contracts.md) | `resources.std` | A small optional starter set of contracts. |
| [0010](0010-identity-and-health.md) | `resources.identity` | "Who are you?" and "are you fit?", checked before use. |
| [0011](0011-drivers-and-duts.md) | `resources.driver` | `@driver`/`@dut`, typed config, injected I/O, channels, lifecycle hooks. |
| [0012](0012-driver-registry.md) | `resources.registry` | Explicit, side-effect-free discovery through entry points. |
| [0013](0013-transport-configuration.md) | `transports.config` | Where a device is, as validated data. |
| [0014](0014-byte-streams.md) | `transports.stream` | TCP and serial with framing and honest timeouts. |
| [0015](0015-line-io.md) | `transports.lineio` | Text lines over streams or VISA. |
| [0016](0016-scpi.md) | `transports.scpi` | SCPI chores done once; overflow markers never become numbers. |
| [0017](0017-datagram-channel.md) | `transports.datagram` | UDP request/response by matching, amid unsolicited traffic. |
| [0018](0018-io-injection.md) | `transports.factory` | Build the I/O a driver asks for from the profile's transport. |
| [0019](0019-builtin-udp-channel.md) | `channels.udp` | `mastif.udp`: a `MessageChannel` with no driver code. |
| [0020](0020-builtin-line-shell.md) | `channels.shell` | `mastif.line-shell`: a prompt-based console as a `Shell`. |

## Station: one physical bench

| ADR | Module | One-line summary |
|---|---|---|
| [0021](0021-station-profile.md) | `station.profile` | The facts of a bench as validated YAML, with roles and a sim overlay. |
| [0022](0022-resource-manager.md) | `station.manager` | Ordered open with rollback; safe state that never stops early. |
| [0023](0023-station-composition-root.md) | `station.station` | Wire everything in one place, validate before power, resolve roles. |

## Testing kit (`mastif-testing`)

| ADR | Module | One-line summary |
|---|---|---|
| [0024](0024-testing-fakes.md) | `mastif_testing.fakes` | Behavioural fakes for every transport. |
| [0025](0025-conformance-kit.md) | `mastif_testing.conformance` | One standard lifecycle and contract check for every driver. |
