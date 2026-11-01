# Station profiles and roles

The test asks for a role, and a driver implements a capability. Something needs to join them up
for one particular bench: *this* supply, at *this* address, with *this* serial number. That
something is a **station profile**, and in this chapter we'll write one and see what mastif does
with it.

!!! success "Works today"
    Everything on this page runs against the current code, with no hardware.

## Facts about a bench are data

Think about what actually differs between two benches running the same test. It's a list of facts:
which instruments there are, where they're plugged in, and what they're called. There's no logic
in that list, no decisions and no sequencing.

Facts like that belong in a data file, for a few practical reasons. A technician who swaps an
instrument can update a file without being a Python programmer. You can diff two benches and see exactly
how they differ. And mastif can validate a file completely, before anything is switched on.

Here's the tutorial's bench:

```yaml title="stations/demo.yaml"
station: demo-bench            # This bench's name; it goes in every run record

resources:                     # What's here. Opened top to bottom, closed bottom to top
  bench_supply:                # Our name for this particular instance
    driver: demo.learn-supply  # Which driver to use, by id
    config:                    # Passed to that driver, and validated by it
      current_ma: 180
    expect:                    # What it must report about itself when opened
      serial: SIM-001

roles:                         # The jobs tests ask for
  supply: bench_supply         # Tests say 'supply'; on this bench that's bench_supply
```

Three different kinds of name appear here, and it helps to keep them straight.

| Name | Example | What it identifies | Who chooses it |
|---|---|---|---|
| Driver id | `demo.learn-supply` | A kind of device | The SDK author |
| Resource name | `bench_supply` | One instance on this bench | Whoever writes the profile |
| Role | `supply` | A job in a test | The test author and profile author, together |

Why have both a resource name and a role? Because they change for different reasons. A bench might have
`psu_left` and `psu_right` as physical instruments, while a test wants `supply`. Today's profile maps
`supply` to the left one. If that one fails, you remap one line, and nothing else changes. Several roles
can also share one resource, when a single instrument does two jobs.

## Build first, open later

Now let's load it. This is one of the most important behaviours in mastif, so we'll go slowly.

```python
from mastif.kernel.units import Amps, Volts, mA
from mastif.resources.driver import DriverConfig, driver
from mastif.resources.identity import Identity
from mastif.resources.registry import Registry
from mastif.resources.std import PowerSupply
from mastif.station import Station, StationProfile


@driver("demo.learn-supply", provides=[PowerSupply])
class SimSupply:
    class Config(DriverConfig):
        current_ma: float = 180

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.on = False

    def identify(self) -> Identity:
        return Identity(vendor="demo", model="learn-supply", serial="SIM-001")

    def set_voltage(self, voltage: Volts) -> None: ...
    def set_current_limit(self, current: Amps) -> None: ...
    def output(self, enabled: bool) -> None: self.on = enabled
    def measure_voltage(self) -> Volts: ...
    def measure_current(self) -> Amps: return self.cfg.current_ma * mA


PROFILE = """
station: demo-bench
resources:
  bench_supply:
    driver: demo.learn-supply
    config: {current_ma: 180}
    expect: {serial: SIM-001}
roles:
  supply: bench_supply
"""

profile = StationProfile.from_yaml(PROFILE)
station = Station.build(profile, Registry([SimSupply]))

print(station.name)  # demo-bench
print(station.role_problems({"supply": PowerSupply}))  # []
```

Two things have happened there, and neither of them touched a device.

**`StationProfile.from_yaml`** read the file and validated its structure. (Use `StationProfile.load(path)`
for a real file.) Every field name is checked, every role must point at a resource that exists, and every
`sim` entry must replace something real.

**`Station.build`** went further. For each resource it found the driver in the registry, validated `config`
against that driver's own `Config` model, prepared whatever I/O the driver asked for, and constructed the
driver object. Everything is wired up, ready to go, and *no connection has been made*.

We call this **build first, open later**, and it has a big consequence: **almost every mistake in a station's
setup can be found without touching the bench.** You can run this check in continuous integration, on a laptop
with no instruments attached, for every station in your company.

## The mistakes it catches

Let's see that in action. These are all real messages. Each one was produced before anything was opened.

A typo in a role:

```text title="role 'supply' -> benchsupply"
StationError: role 'supply' points to unknown resource 'benchsupply'
```

A misspelled configuration field. This one's important, because a configuration system that ignores unknown
keys would silently use your default instead:

```text title="curent_ma: 180"
StationError: resource 'bench_supply': invalid config: curent_ma: Extra inputs are not permitted
```

A driver that isn't installed. Note that it tells you what *is* available:

```text title="driver: acme.psu-x"
StationError: resource 'bench_supply': no driver 'acme.psu-x'; known: demo.learn-supply,
mastif.line-shell, mastif.ssh-shell, mastif.udp
```

A stray field anywhere in the profile:

```text title="colour: red"
StationError: <string>: invalid station profile:
colour: Extra inputs are not permitted
```

And a test asking for something the bench can't provide. `role_problems` doesn't raise. It returns a list,
because you want to see every problem at once rather than fixing them one at a time:

```python title="continuing the example above"
from mastif.resources.std import Shell

print(station.role_problems({"supply": Shell, "console": Shell}))
```

```text title="Real output"
["role 'supply' (demo.learn-supply) does not provide Shell",
 "no role 'console'; known roles: bench_supply, supply"]
```

This is the check the engine will run automatically across every task in a plan, as part of its
[preflight](../writing-tests/requirements.md).

## Roles can point inside things

A DUT usually has channels, and an instrument can have sub-units such as the axes of a positioner. A role can
reach into those with a dotted path:

```yaml title="excerpt of a larger profile"
resources:
  dut:
    driver: demo.widget-board
    channels:
      console:
        driver: mastif.line-shell
        config:
          transport: {kind: serial, port: COM3, baudrate: 115200}
          prompt: "# "
roles:
  console: dut.console         # The console channel of the DUT
```

A task asks for `console` and gets something providing `Shell`, without knowing it lives inside a DUT, or that
it's serial today and could be SSH tomorrow. We'll build this out in [DUT channels and child
resources](../hardware-integration/channels.md).

## Keep logic out of it

Here's a line we hold quite firmly. A station profile has no conditions, no loops and no expressions. As soon as
a configuration file can make decisions, it becomes a second programming language, with no debugger, no tests
and no types. If you find yourself wanting "use this limit on Tuesdays", that's not a fact about the bench. It
belongs in a plan or in code.

## Recap

- A **station profile** holds the facts about one bench as validated data.
- **Build first, open later** means `Station.build` wires everything and touches nothing, so nearly every setup
  mistake can be found on a laptop or in CI.
- Error messages name what's wrong, and `role_problems` reports all of it together.

Being able to build a station without hardware suggests an obvious next step: what if we didn't need the hardware
for the rest of it either?

**Next:** [Working with simulated resources](simulation.md)
