"""Build a simulated bench, measure a current, and judge it against a limit.

Run from the repository root with ``uv run python docs/examples/quickstart.py``.
"""

from mastif.kernel.limits import Limits
from mastif.kernel.results import Measurement
from mastif.kernel.units import Amps, V, Volts, mA
from mastif.resources.driver import DriverConfig, driver
from mastif.resources.identity import Identity
from mastif.resources.registry import Registry
from mastif.resources.std import PowerSupply
from mastif.station import Station, StationProfile


# --8<-- [start:driver]
@driver("demo.sim-psu", provides=[PowerSupply])
class SimPsu:
    """A power supply that lives in memory; a real driver would send commands instead."""

    class Config(DriverConfig):
        """What the bench's profile can set on this driver."""

        current_ma: float = 180

    def __init__(self, cfg: Config) -> None:
        """Store the configuration; e.g. ``SimPsu(cfg)``. Constructors never touch hardware."""
        self.cfg = cfg

    def identify(self) -> Identity:
        """Say who this is; e.g. ``psu.identify().serial``."""
        return Identity(vendor="demo", model="sim-psu", serial="SIM-001")

    def set_voltage(self, voltage: Volts) -> None:
        """Accept a setpoint; e.g. ``psu.set_voltage(5 * V)``."""

    def set_current_limit(self, current: Amps) -> None:
        """Accept a protection limit; e.g. ``psu.set_current_limit(500 * mA)``."""

    def output(self, enabled: bool) -> None:
        """Switch the output, so you can see the cleanup; e.g. ``psu.output(True)``."""
        print(f"output {'on' if enabled else 'off'}")

    def measure_voltage(self) -> Volts:
        """Read the voltage; e.g. ``psu.measure_voltage()``."""
        return 5 * V

    def measure_current(self) -> Amps:
        """Read the current; e.g. ``psu.measure_current()``."""
        return self.cfg.current_ma * mA


# --8<-- [end:driver]
# --8<-- [start:test]
BENCH = """
station: my-bench
resources:
  bench_psu:
    driver: demo.sim-psu
    config: {current_ma: 180}
    expect: {serial: SIM-001}
roles:
  supply: bench_psu
"""

station = Station.build(StationProfile.from_yaml(BENCH), Registry([SimPsu]))

with station:
    supply = station.require("supply", PowerSupply)
    supply.set_voltage(5 * V)
    supply.output(True)
    result = Measurement("idle_current", supply.measure_current(), Limits.at_most(250 * mA))
    print(f"{result.name}: {result.value:g} {result.unit} -> {result.verdict.value.upper()}")
# --8<-- [end:test]
