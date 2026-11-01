"""Watch a station open, lose an instrument mid-measurement, and clean up.

Run from the repository root with ``uv run python docs/examples/learn_lifecycle.py``.
Everything is in memory: no hardware or network is involved. This is a teaching script
for ADR-0022 (the resource manager) and ADR-0002 (the error model), not a public API.
"""

from mastif.kernel.units import Amps, V, Volts, mA
from mastif.resources.driver import DriverConfig, driver
from mastif.resources.errors import TransportTimeout
from mastif.resources.identity import Health, Identity
from mastif.resources.registry import Registry
from mastif.resources.std import PowerSupply
from mastif.station import Station, StationProfile
from mastif.station.manager import ResourceEvent


@driver("demo.flaky-supply", provides=[PowerSupply])
class FlakySupply:
    """A simulated supply whose measurement can be configured to stop answering.

    Examples:
        ``FlakySupply(FlakySupply.Config(loses_connection=True))`` times out on a read.
    """

    class Config(DriverConfig):
        """Choose whether measuring behaves like a cable that has fallen out."""

        loses_connection: bool = False

    def __init__(self, cfg: Config) -> None:
        """Store configuration without doing any I/O; e.g. ``FlakySupply(cfg)``."""
        self.cfg = cfg
        self.enabled = False

    def identify(self) -> Identity:
        """Report a fixed identity; e.g. ``supply.identify().serial``."""
        return Identity(vendor="demo", model="flaky-supply", serial="SIM-002")

    def health(self) -> Health:
        """Report readiness; e.g. ``supply.health().ok`` is true."""
        return Health.good()

    def set_voltage(self, voltage: Volts) -> None:
        """Accept a setpoint; e.g. ``supply.set_voltage(5 * V)``."""

    def set_current_limit(self, current: Amps) -> None:
        """Accept a protection setting; e.g. ``supply.set_current_limit(500 * mA)``."""

    def output(self, enabled: bool) -> None:
        """Switch simulated output; e.g. ``supply.output(False)``."""
        self.enabled = enabled
        print(f"    supply output -> {'ON' if enabled else 'OFF'}")

    def measure_voltage(self) -> Volts:
        """Read simulated voltage; e.g. ``supply.measure_voltage()``."""
        return 5 * V

    def measure_current(self) -> Amps:
        """Read current, or time out; e.g. ``supply.measure_current()``."""
        if self.cfg.loses_connection:
            raise TransportTimeout("bench_supply: no reply to MEAS:CURR? within 2.0 s")
        return 180 * mA


def show(event: ResourceEvent) -> None:
    """Print one lifecycle step; e.g. ``show(ResourceEvent("psu", "opened"))``."""
    detail = f"  ({event.detail})" if event.detail else ""
    print(f"  [{event.resource}] {event.phase}{detail}")


def run(loses_connection: bool) -> None:
    """Measure through a station, reporting what happened on the way out.

    Examples:
        ``run(loses_connection=True)`` prints the timeout after the cleanup steps.
    """
    profile = StationProfile.from_yaml(f"""
station: demo-bench
resources:
  bench_supply:
    driver: demo.flaky-supply
    config: {{loses_connection: {str(loses_connection).lower()}}}
    expect: {{serial: SIM-002}}
roles:
  supply: bench_supply
""")
    station = Station.build(profile, Registry([FlakySupply]), listener=show)
    print("  built: nothing has been opened yet")
    try:
        with station:
            supply = station.require("supply", PowerSupply)
            supply.set_voltage(5 * V)
            supply.output(True)
            print(f"    measured {supply.measure_current()}")
    except TransportTimeout as error:
        print(f"  the test raised TransportTimeout: {error}")


if __name__ == "__main__":
    print("A normal run:")
    run(loses_connection=False)
    print("The cable falls out mid-measurement:")
    run(loses_connection=True)
