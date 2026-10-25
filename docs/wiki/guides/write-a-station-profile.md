# Guide: write a station profile

A station profile is a YAML file describing one bench. Concepts: [Station](../station.md).
Design: ADR-0013, ADR-0021, ADR-0023.

## Anatomy

```yaml
station: bench-01                  # recorded with every run
description: RF line, position 3

resources:                         # opened in this order, closed in reverse
  bench_psu:                       # resource name: letters, digits, _ and -
    driver: acme.psu-x             # driver id, from the registry
    config:                        # validated against the driver's Config
      transport: {kind: tcp, host: 10.0.0.5, port: 5025}
    expect: {serial: A123}         # identity checked before use

  rf_matrix:
    driver: acme.matrix-8
    config:
      transport: {kind: visa, resource: "TCPIP0::10.0.0.7::INSTR"}

  dut:
    driver: demo.widget-board
    channels:
      console: {driver: mastif.line-shell,
                config: {transport: {kind: serial, port: COM3, baudrate: 115200}, prompt: "# "}}

roles:                             # the names tests use
  psu_main: bench_psu
  rf_switch: rf_matrix
  console: dut.console             # resource.channel or resource.child

sim:                               # replacements when built with sim=True
  bench_psu: {driver: demo.psu-sim}
  rf_matrix: {driver: demo.matrix-sim}
  dut:
    driver: demo.widget-sim
    channels:
      console: {driver: demo.shell-sim}
```

## Decisions you make in a profile

| Question | Where it goes |
|---|---|
| Which device is it? | `driver:` |
| Where is it connected? | `config.transport` (`kind`: tcp, serial, visa, udp, telnet, ssh) |
| How should lines be framed? | `transport.read_termination`, `write_termination`, `encoding`, `timeout` |
| Which unit must be present? | `expect:` (any `Identity` field, or an `extra` key) |
| What do tests call it? | `roles:` (a resource name also works as a role) |
| What replaces it in simulation? | `sim:` (whole entry; nothing is merged) |

## Order matters

Resources open top to bottom, and close bottom to top. Put things that others depend on
first. For example, a fixture power relay goes before the DUT it powers.

## Validate it

```python
from mastif.resources.registry import Registry
from mastif.station import Station, StationProfile

profile = StationProfile.load("bench-01.yaml")  # syntax, names, roles, sim keys
station = Station.build(profile, Registry.discover())  # drivers, configs, channels (no I/O)
print(station.role_problems({"psu_main": PowerSupply}))  # [] if the bench fits the tests
```

This can run in CI. No hardware is touched.

## Common errors

| Message starts with | Meaning |
|---|---|
| `role 'x' points to unknown resource` | Typo in `roles:` |
| `resource 'x': no driver 'acme.y'; known: ...` | Typo, or the SDK isn't installed |
| `resource 'x': invalid config: transport.port: ...` | Bad value or unknown key |
| `resource 'dut': channel 'console' is not mapped` | A required DUT channel is missing |
| `resource 'dut': channel 'console' needs Shell, but ... doesn't provide it` | The wrong driver for that channel |
| `bench_psu: serial is 'B999', expected 'A123'` | The wrong device on the bench (at open) |

More: [Error map](../errors.md).
