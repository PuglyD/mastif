# Replace hardware with simulation

**You have:** a task, or a whole plan, that normally needs a bench.

**You want:** to run it without one, with behaviour you control, including its failures.

!!! success "Works today"
    Everything on this page runs against the current code, with no hardware.

A simulator isn't a special mode in mastif. It's an ordinary driver which provides the same contract and happens to keep its answers in memory. The test can't tell the difference, and that's why this works.

## Write a simulator

```python
from mastif.kernel.units import Amps, Volts, V, mA
from mastif.resources.driver import DriverConfig, driver
from mastif.resources.errors import TransportTimeout
from mastif.resources.identity import Health, Identity
from mastif.resources.std import PowerSupply


@driver("demo.psu-sim", provides=[PowerSupply])
class PsuSim:
    """A simulated supply, whose readings and faults are configurable."""

    class Config(DriverConfig):
        current_ma: float = 180
        serial: str = "SIM-001"
        healthy: bool = True
        loses_connection: bool = False

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.enabled = False
        self.voltage = 0 * V

    def identify(self) -> Identity:
        return Identity(vendor="demo", model="psu-sim", serial=self.cfg.serial)

    def health(self) -> Health:
        return Health(ok=self.cfg.healthy, detail="" if self.cfg.healthy else "simulated fault")

    def set_voltage(self, voltage: Volts) -> None:
        self.voltage = voltage

    def set_current_limit(self, current: Amps) -> None:
        pass

    def output(self, enabled: bool) -> None:
        self.enabled = enabled

    def measure_voltage(self) -> Volts:
        return self.voltage if self.enabled else 0 * V

    def measure_current(self) -> Amps:
        if self.cfg.loses_connection:
            raise TransportTimeout("psu-sim: simulated lost connection")
        return (self.cfg.current_ma if self.enabled else 0) * mA
```

Make it return zero when the output's off, as the real thing would. A test that forgets to enable the output should see that on a simulator, too.

## Use it from a profile

Either add it as a `sim:` overlay on a real profile, or write a separate profile:

```yaml title="an overlay on a real bench's profile"
sim:
  bench_supply:
    driver: demo.psu-sim
    config: {current_ma: 300}
    expect: {serial: SIM-001}
```

```python title="excerpt"
station = Station.build(profile, registry, sim=True)
```

Each entry replaces its resource entirely, and anything without an entry **stays real**. Check what's been selected before you describe a run as hardware-free, including any DUT channels:

```python title="excerpt"
for name, entry in profile.entries(sim=True).items():
    print(name, entry.driver)
```

## Rehearse the bad days

This is where a simulator pays for itself. Let's use the `PsuSim` above to run through the scenarios you'd rather not set up on a bench:

```python title="continuing the example above"
from mastif.kernel.limits import Limits
from mastif.kernel.results import Measurement
from mastif.resources.errors import IdentityMismatch, ResourceFault
from mastif.resources.registry import Registry
from mastif.station import Station, StationProfile


def station_with(config: str, expect: str = "SIM-001") -> Station:
    profile = StationProfile.from_yaml(f"""
station: sim-bench
resources:
  psu:
    driver: demo.psu-sim
    config: {config}
    expect: {{serial: {expect}}}
roles:
  supply: psu
""")
    return Station.build(profile, Registry([PsuSim]))


def measure(station: Station) -> str:
    with station:
        supply = station.require("supply", PowerSupply)
        supply.output(True)
        result = Measurement("idle", supply.measure_current(), Limits.at_most(250 * mA))
        return result.verdict.value


print(measure(station_with("{current_ma: 180}")))   # pass
print(measure(station_with("{current_ma: 300}")))   # fail

for label, station, expected in [
    ("wrong instrument", station_with("{}", expect="OTHER"), IdentityMismatch),
    ("unhealthy", station_with("{healthy: false}"), ResourceFault),
    ("lost connection", station_with("{loses_connection: true}"), TransportTimeout),
]:
    try:
        measure(station)
    except expected as error:
        print(f"{label}: {error}")
```

```text title="Real output"
pass
fail
wrong instrument: psu: serial is 'SIM-001', expected 'OTHER'
unhealthy: psu: unhealthy: simulated fault
lost connection: psu-sim: simulated lost connection
```

Each of those scenarios exercised the real station, the real lifecycle and real error handling. That's a good test suite for your application, and you'd struggle to reproduce those on purpose with real hardware.

## How much should it model?

Keep it as simple as your question requires. Add behaviour only when you have a specific reason to.

| Worth adding | Because |
|---|---|
| Configurable readings | To test pass and fail paths |
| Configurable faults | To test your error handling |
| Output state | To check that cleanup happened |
| A delay, sometimes | To test timeouts, or UI behaviour |

Resist building something which models the physics. An elaborate simulator is still only a model, and it takes real effort to maintain. Worse, it can give people the feeling that the simulator's numbers mean something about the product. They don't.

## What it doesn't test

Since a simulator replaces the driver, that driver's commands and parsing don't get exercised at all. To test those, keep your real driver and [fake the I/O](../../getting-started/tutorial/hardware-integration/fake-io.md) instead. Those two tools aren't alternatives, and you should use both.

## See also

- [Working with simulated resources](../../getting-started/tutorial/deploying/simulation.md), in the tutorial.
- [Testing drivers with fake I/O](../../getting-started/tutorial/hardware-integration/fake-io.md).

**Next:** [Diagnose an identity or health-check failure](identity-failures.md)
