"""Optional built-in contracts for the most common station resources.

Why this exists:
    Organisations are expected to define their own contracts, because only they know
    exactly what their tests need. A few capabilities appear at almost every station,
    though: a power supply, a signal source, a switch, relays, digital lines, a
    motion axis, and ways to talk to a DUT. These are offered here so that a new org can
    start testing on day one, and so that example code and simulators have a shared
    vocabulary.

    They are deliberately small. If your power supply needs over-voltage protection or
    sequencing, define your own contract. It can extend these (``class
    ProtectedSupply(PowerSupply, Protocol)``) or replace them entirely.

Where it fits:
    These are plain Protocols like any org contract. Drivers list them in
    ``provides=[...]``. Tasks request them with ``requires(role)``. The DUT-facing
    `Shell` and `MessageChannel` are what mastif's built-in channel drivers implement
    (a line-based shell over serial or TCP, and datagram messaging over UDP).

Conventions:
    Physical values are `Quantity` (``12 * V``). Timeouts are plain float seconds,
    because they configure the I/O rather than describe the device.
"""

from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from mastif.kernel.units import Amps, Hertz, Quantity, Volts, Watts
from mastif.resources.contracts import contract


@contract(safe_state=lambda psu: psu.output(False))
class PowerSupply(Protocol):
    """A programmable DC supply channel. Safe state: output off.

    Example:
        A test powering a board and checking its idle current::

            psu: PowerSupply = requires("psu_main")

            def run(self, ctx):
                self.psu.set_voltage(12 * V)
                self.psu.set_current_limit(1 * A)
                self.psu.output(True)
                ctx.measure("idle_current", self.psu.measure_current(), Limits.at_most(250 * mA))
    """

    def set_voltage(self, voltage: Volts) -> None:
        """Set the output voltage setpoint."""
        ...

    def set_current_limit(self, current: Amps) -> None:
        """Set the current limit (constant-current threshold)."""
        ...

    def output(self, enabled: bool) -> None:
        """Switch the output on or off."""
        ...

    def measure_voltage(self) -> Volts:
        """Measure the actual output voltage."""
        ...

    def measure_current(self) -> Amps:
        """Measure the actual output current."""
        ...


@contract(safe_state=lambda src: src.output(False))
class SignalSource(Protocol):
    """A signal generator output (RF or otherwise). Safe state: output off.

    Example:
        Driving a receiver input with a test tone::

            src: SignalSource = requires("rf_source")
            self.src.set_frequency(2.4 * GHz)
            self.src.set_level(-30 * dBm)
            self.src.output(True)
    """

    def set_frequency(self, frequency: Hertz) -> None:
        """Set the output frequency."""
        ...

    def set_level(self, level: Quantity) -> None:
        """Set the output level, e.g. in dBm or V."""
        ...

    def output(self, enabled: bool) -> None:
        """Switch the output on or off."""
        ...


class PowerMeter(Protocol):
    """Something that measures power, e.g. an RF power sensor or a spectrum analyser marker.

    Example:
        Checking a transmitter's output power::

            meter: PowerMeter = requires("tx_meter")
            ctx.measure("tx_power", self.meter.measure_power(), Limits.between(9 * dBm, 11 * dBm))
    """

    def measure_power(self) -> Watts:
        """Measure power; dBm or W are both valid units."""
        ...


class Switch(Protocol):
    """A signal-routing switch or matrix with named ports.

    Port names come from the station profile, so tests say ``route("source", "dut_in")``
    and never mention switch positions.

    Example:
        Connecting a source to the DUT input::

            sw: Switch = requires("rf_matrix")
            self.sw.route("source", "dut_in")
    """

    def route(self, a: str, b: str) -> None:
        """Connect port ``a`` to port ``b``."""
        ...

    def clear(self) -> None:
        """Disconnect all routes."""
        ...


@contract(safe_state="open_all")
class Relay(Protocol):
    """A bank of relays addressed by channel name or number. Safe state: all open.

    Example:
        Connecting a load::

            relays: Relay = requires("load_relays")
            self.relays.set("load_1", closed=True)
    """

    def set(self, channel: str | int, closed: bool) -> None:
        """Close or open one relay."""
        ...

    def is_closed(self, channel: str | int) -> bool:
        """Report whether one relay is closed."""
        ...

    def open_all(self) -> None:
        """Open every relay."""
        ...


class DigitalIO(Protocol):
    """Digital lines that can be driven and read, e.g. DUT straps or fixture sensors.

    Example:
        Waiting for the fixture lid sensor::

            dio: DigitalIO = requires("fixture_io")
            ctx.require(self.dio.read("lid_closed"), "fixture lid must be closed")
    """

    def write(self, line: str | int, high: bool) -> None:
        """Drive one line high or low."""
        ...

    def read(self, line: str | int) -> bool:
        """Read one line; True means high."""
        ...


@contract(safe_state="stop")
class Axis(Protocol):
    """One motion axis (linear or rotary). Safe state: stop.

    Example:
        Rotating a turntable to 45 degrees::

            table: Axis = requires("turntable")
            self.table.move_to(45 * deg)
    """

    def move_to(self, position: Quantity) -> None:
        """Move to an absolute position and return when it is reached."""
        ...

    def position(self) -> Quantity:
        """Report the current position."""
        ...

    def home(self) -> None:
        """Run the homing sequence."""
        ...

    def stop(self) -> None:
        """Stop motion immediately."""
        ...


class ShellResult(BaseModel):
    """The outcome of one command run through a `Shell`.

    Attributes:
        command: The command that was sent.
        output: Everything the DUT printed in response, without the echoed command and
            prompt.
        exit_code: The command's exit status when the shell can report it, else ``None``.
        stderr: The command's error output, when the shell keeps it separate (SSH exec
            does; a console mixes it into ``output`` and leaves this empty).

    Example:
        >>> ShellResult(command="uname -r", output="6.1.0", exit_code=0).ok
        True
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str
    output: str
    exit_code: int | None = None
    stderr: str = ""

    @property
    def ok(self) -> bool:
        """True unless the shell reported a non-zero exit code.

        Example:
            >>> ShellResult(command="false", output="", exit_code=1).ok
            False
        """
        return self.exit_code in (None, 0)


class Shell(Protocol):
    """A command-line interface on a DUT: send a command, get its output.

    It may run over a serial console, Telnet or SSH. The test doesn't care which; the
    station profile decides.

    Example:
        Reading the DUT's firmware version::

            board: WidgetBoard = requires("dut")
            result = self.board.console.execute("version")
            ctx.check("fw_version", result.output == "2.1", detail=result.output)
    """

    def execute(self, command: str, timeout: float = 5.0) -> ShellResult:
        """Run a command and wait for it to finish."""
        ...


class MessageChannel(Protocol):
    """Message-based communication with a DUT, e.g. UDP datagrams or framed packets.

    Supports three patterns:

    - fire-and-forget (`send`)
    - request/response with a matcher that picks the right reply among other traffic
      (`request`)
    - listening to unsolicited messages such as status broadcasts (`subscribe`)

    Example:
        Asking the DUT for its temperature::

            reply = self.board.ctrl.request(b"TEMP?", match=lambda m: m.startswith(b"TEMP "))
    """

    def send(self, message: bytes) -> None:
        """Send one message without waiting for a reply."""
        ...

    def request(
        self,
        message: bytes,
        match: Callable[[bytes], bool],
        timeout: float = 1.0,
        retries: int = 0,
    ) -> bytes:
        """Send a message and return the first incoming message accepted by ``match``."""
        ...

    def subscribe(self, handler: Callable[[bytes], None]) -> Callable[[], None]:
        """Call ``handler`` for every incoming message; returns a function that unsubscribes."""
        ...
