"""Run the Learn tutorial's station example using only simulated resources.

Run from the repository root with ``uv run python docs/examples/learn_station.py``.
This is a standalone teaching script, not the proposed execution engine or public API.
See ADR-0008, ADR-0011, ADR-0021 and ADR-0023 for the boundaries demonstrated here.
"""

from mastif.kernel.limits import Limits
from mastif.kernel.results import Measurement
from mastif.kernel.units import Amps, V, Volts, mA
from mastif.resources.driver import DriverConfig, driver
from mastif.resources.identity import Health, Identity
from mastif.resources.registry import Registry
from mastif.resources.std import PowerSupply
from mastif.station import Station, StationProfile


@driver("demo.learn-supply", provides=[PowerSupply])
class SimSupply:
    """An in-memory supply with a configurable reading and observable output state.

    Examples:
        ``SimSupply(SimSupply.Config(current_ma=180))`` creates a closed simulator.
    """

    class Config(DriverConfig):
        """Choose the reading returned while output is enabled."""

        current_ma: float = 180

    def __init__(self, cfg: Config) -> None:
        """Store configuration without opening I/O; e.g. ``SimSupply(cfg)``."""
        self.cfg = cfg
        self.enabled = False
        self.voltage = 0 * V
        self.current_limit = 0 * mA

    def identify(self) -> Identity:
        """Report a deterministic identity; e.g. ``supply.identify().serial``."""
        return Identity(vendor="demo", model="learn-supply", serial="SIM-001")

    def health(self) -> Health:
        """Report readiness; e.g. ``supply.health().ok`` is true."""
        return Health.good()

    def set_voltage(self, voltage: Volts) -> None:
        """Remember the setpoint; e.g. ``supply.set_voltage(5 * V)``."""
        self.voltage = voltage

    def set_current_limit(self, current: Amps) -> None:
        """Remember the protection setting; e.g. ``supply.set_current_limit(500 * mA)``."""
        self.current_limit = current

    def output(self, enabled: bool) -> None:
        """Switch simulated output; e.g. ``supply.output(False)``."""
        self.enabled = enabled

    def measure_voltage(self) -> Volts:
        """Read simulated output voltage; e.g. ``supply.measure_voltage()``."""
        return self.voltage if self.enabled else 0 * V

    def measure_current(self) -> Amps:
        """Read configured current; e.g. ``supply.measure_current().to('mA')``."""
        return (self.cfg.current_ma if self.enabled else 0) * mA


def run_demo(current_ma: float) -> tuple[Measurement, bool]:
    """Measure through a station and return evidence plus post-cleanup output state.

    Examples:
        ``run_demo(300)[0].verdict.value`` is ``"fail"``.
    """
    profile = StationProfile.from_yaml(f"""
station: demo-bench
resources:
  bench_supply:
    driver: demo.learn-supply
    config: {{current_ma: {current_ma}}}
    expect: {{serial: SIM-001}}
roles:
  supply: bench_supply
""")
    station = Station.build(profile, Registry([SimSupply]))
    problems = station.role_problems({"supply": PowerSupply})
    if problems:
        raise RuntimeError(problems)
    with station:
        supply = station.require("supply", PowerSupply)
        supply.set_voltage(5 * V)
        supply.set_current_limit(500 * mA)
        supply.output(True)
        result = Measurement("idle_current", supply.measure_current(), Limits.at_most(250 * mA))
    return result, supply.enabled


if __name__ == "__main__":
    for reading in (180, 300):
        result, enabled = run_demo(reading)
        print(f"{result.name}: {result.value:g} {result.unit} -> {result.verdict.value.upper()}")
        print(f"after cleanup: output enabled = {enabled}")
