"""Exercise a fictional SCPI supply through injected fake I/O.

Run ``uv run python docs/examples/learn_driver.py`` from the repository root.
This teaching script demonstrates ADR-0009, ADR-0011, ADR-0016 and ADR-0025;
it is not a supported driver for any real instrument.
"""

from mastif.kernel.units import Amps, Volts, mV
from mastif.resources.driver import DriverConfig, build_resource, driver, spec_of
from mastif.resources.identity import Identity
from mastif.resources.std import PowerSupply
from mastif.resources.transports import Scpi, TcpConfig
from mastif_testing import FakeLineIO, assert_satisfies, check_lifecycle


@driver("demo.learn-scpi", provides=[PowerSupply])
class LearnSupply:
    """Translate a supply capability to a fictional instrument's SCPI vocabulary.

    Examples:
        ``build_resource(spec_of(LearnSupply), config, io_factory=factory)``
        constructs a driver using the application's I/O factory.
    """

    class Config(DriverConfig):
        """Describe the TCP endpoint; fake I/O replaces it in this example."""

        transport: TcpConfig

    def __init__(self, cfg: Config, io: Scpi) -> None:
        """Accept station-supplied I/O; e.g. ``LearnSupply(cfg, Scpi(fake))``."""
        self.io = io

    def identify(self) -> Identity:
        """Read identity; e.g. ``supply.identify().serial`` returns SIM-001 here."""
        return self.io.identify()

    def set_voltage(self, voltage: Volts) -> None:
        """Send volts regardless of input scale; e.g. ``set_voltage(5000 * mV)``."""
        self.io.write(f"VOLT {voltage.magnitude('V'):.4f}")

    def set_current_limit(self, current: Amps) -> None:
        """Send the protection setting in amperes; e.g. ``set_current_limit(1 * A)``."""
        self.io.write(f"CURR {current.magnitude('A'):.4f}")

    def output(self, enabled: bool) -> None:
        """Control output; e.g. ``output(False)`` is the contract's safe-state action."""
        self.io.write("OUTP ON" if enabled else "OUTP OFF")

    def measure_voltage(self) -> Volts:
        """Parse a voltage reply; e.g. ``measure_voltage()`` returns a quantity."""
        return self.io.query_quantity("MEAS:VOLT?", "V")

    def measure_current(self) -> Amps:
        """Parse a current reply; e.g. ``measure_current().magnitude('mA')``."""
        return self.io.query_quantity("MEAS:CURR?", "A")


def demonstrate() -> None:
    """Verify command conversion and lifecycle against the fake device.

    Examples:
        ``demonstrate()`` prints the verified reading and lifecycle outcome.
    """
    config = {"transport": {"kind": "tcp", "host": "192.0.2.10", "port": 5025}}
    fake = FakeLineIO({"MEAS:CURR?": "0.180"})
    io = Scpi(fake)
    built = build_resource(spec_of(LearnSupply), config, name="supply", io_factory=lambda *_: io)
    io.open()
    try:
        built.instance.set_voltage(5000 * mV)
        assert fake.written == ["VOLT 5.0000"]
        current = built.instance.measure_current()
        assert current.magnitude("mA") == 180
        print(f"command: {fake.written[0]}")
        print(f"reading: {current.magnitude('mA'):g} mA")
    finally:
        io.close()

    assert_satisfies(LearnSupply, PowerSupply)
    lifecycle_io = Scpi(FakeLineIO({"*IDN?": "demo,learn-scpi,SIM-001,1.0"}))
    report = check_lifecycle(LearnSupply, config, io=lifecycle_io)
    assert report.identity is not None and report.identity.serial == "SIM-001"
    assert report.safe_state_ran
    print("conformance: identity checked; safe-state action ran")


if __name__ == "__main__":
    demonstrate()
