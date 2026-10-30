"""Tiny example drivers used by mastif's own docstring examples.

They are not registered anywhere and are not part of the public API. Real
organisations write their drivers in their own SDK packages.

Examples:
    >>> from mastif.resources._examples import ExamplePsu
    >>> ExamplePsu.__mastif_driver__.id
    'demo.example-psu'
"""

from mastif.kernel.units import Amps, Volts
from mastif.resources.driver import DriverConfig, driver
from mastif.resources.std import PowerSupply
from mastif.resources.transports.config import TcpConfig
from mastif.resources.transports.scpi import Scpi


@driver("demo.example-psu", provides=[PowerSupply])
class ExamplePsu:
    """A minimal SCPI bench power supply, showing the shape of a typical driver.

    Examples:
        >>> from mastif_testing import FakeLineIO
        >>> psu = ExamplePsu(ExamplePsu.Config.model_validate(
        ...     {"transport": {"kind": "tcp", "host": "10.0.0.5", "port": 5025}}),
        ...     Scpi(FakeLineIO({"MEAS:VOLT?": "12.001"})))
        >>> psu.measure_voltage()
        Quantity(value=12.001, unit='V')
    """

    class Config(DriverConfig):
        """Where the supply is: a raw-SCPI TCP port."""

        transport: TcpConfig

    def __init__(self, cfg: Config, io: Scpi) -> None:
        """Keep the SCPI I/O the station injects.

        Examples:
            The station calls ``ExamplePsu(cfg, io=Scpi(...))``.
        """
        self.io = io

    def set_voltage(self, voltage: Volts) -> None:
        """Set the voltage setpoint.

        Examples:
            ``psu.set_voltage(12 * V)`` sends ``VOLT 12.0000``.
        """
        self.io.write(f"VOLT {voltage.magnitude('V'):.4f}")

    def set_current_limit(self, current: Amps) -> None:
        """Set the current limit.

        Examples:
            ``psu.set_current_limit(500 * mA)`` sends ``CURR 0.5000``.
        """
        self.io.write(f"CURR {current.magnitude('A'):.4f}")

    def output(self, enabled: bool) -> None:
        """Switch the output on or off.

        Examples:
            ``psu.output(False)`` sends ``OUTP OFF``.
        """
        self.io.write("OUTP ON" if enabled else "OUTP OFF")

    def measure_voltage(self) -> Volts:
        """Measure the output voltage.

        Examples:
            ``psu.measure_voltage()`` returns e.g. ``12.001 V``.
        """
        return self.io.query_quantity("MEAS:VOLT?", "V")

    def measure_current(self) -> Amps:
        """Measure the output current.

        Examples:
            ``psu.measure_current()`` returns e.g. ``0.18 A``.
        """
        return self.io.query_quantity("MEAS:CURR?", "A")
