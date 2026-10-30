"""Helpers for SCPI instruments, the most common bench-instrument command language.

Why this exists:
    SCPI (Standard Commands for Programmable Instruments) is spoken by most bench power
    supplies, generators, meters and analysers. Every SCPI driver needs the same
    chores: parse numbers from replies, read ``*IDN?`` into an identity, drain the error
    queue after commands, reset to a known state. `Scpi` does these once and correctly,
    so a SCPI driver is mostly a list of one-line methods.

Where it fits:
    A driver asks for ``io: Scpi`` in its ``__init__``. The station wraps the line I/O it
    built from the profile's ``transport:`` block. In tests, wrap a
    ``mastif_testing.FakeLineIO`` in `Scpi` to script replies.

Examples:
    A complete power-supply driver::

        @driver("acme.psu-x", provides=[PowerSupply])
        class PsuX:
            class Config(DriverConfig):
                transport: TcpConfig

            def __init__(self, cfg: Config, io: Scpi):
                self.io = io

            def identify(self) -> Identity:
                return self.io.identify()

            def set_voltage(self, voltage: Volts) -> None:
                self.io.write(f"VOLT {voltage.magnitude('V'):.4f}")

            def measure_current(self) -> Amps:
                return self.io.query_quantity("MEAS:CURR?", "A")
            ...
"""

from mastif.kernel.units import Quantity
from mastif.resources.errors import ProtocolError
from mastif.resources.identity import Identity
from mastif.resources.transports.lineio import LineIO


class Scpi:
    """SCPI conveniences over any `LineIO`.

    Examples:
        >>> from mastif_testing import FakeLineIO
        >>> scpi = Scpi(FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4", "MEAS:VOLT?": "+5.0021E+00"}))
        >>> scpi.identify().serial
        'A123'
        >>> scpi.query_quantity("MEAS:VOLT?", "V")
        Quantity(value=5.0021, unit='V')
    """

    def __init__(self, io: LineIO, *, check_errors: bool = False) -> None:
        """Wrap line I/O with SCPI helpers.

        Args:
            io: The line I/O to talk over.
            check_errors: If True, every `write` is followed by an error-queue check,
                so a rejected command raises immediately. This is slower, but useful
                while developing a driver.

        Examples:
            ``Scpi(io, check_errors=True)``
        """
        self.io = io
        self.check_errors = check_errors

    def open(self) -> None:
        """Open the underlying I/O.

        Examples:
            Called by the station before the driver's ``open()``.
        """
        self.io.open()

    def close(self) -> None:
        """Close the underlying I/O.

        Examples:
            Called by the station after the driver's ``close()``.
        """
        self.io.close()

    def write(self, command: str) -> None:
        """Send a command that produces no reply.

        Args:
            command: The SCPI command, e.g. ``"OUTP ON"``.

        Raises:
            ProtocolError: If ``check_errors`` is on and the instrument reports an error.

        Examples:
            >>> from mastif_testing import FakeLineIO
            >>> io = FakeLineIO()
            >>> Scpi(io).write("OUTP ON")
            >>> io.written
            ['OUTP ON']
        """
        self.io.write_line(command)
        if self.check_errors:
            self.raise_on_errors(after=command)

    def query(self, command: str, timeout: float | None = None) -> str:
        """Send a query and return the reply text, stripped of surrounding whitespace.

        Args:
            command: The query, usually ending in ``?``.
            timeout: Seconds to wait for the reply.

        Returns:
            The reply.

        Examples:
            >>> from mastif_testing import FakeLineIO
            >>> Scpi(FakeLineIO({"SYST:VERS?": " 1999.0 "})).query("SYST:VERS?")
            '1999.0'
        """
        return self.io.query(command, timeout).strip()

    def query_float(self, command: str, timeout: float | None = None) -> float:
        """Send a query and parse the reply as a number.

        Handles SCPI number formats such as ``+5.0021E+00``. Overflow markers
        (``9.9E37``, ``9.91E37``) are rejected rather than returned as huge values.

        Args:
            command: The query.
            timeout: Seconds to wait for the reply.

        Returns:
            The number.

        Raises:
            ProtocolError: If the reply isn't a number, or is an overflow or NaN marker.

        Examples:
            >>> from mastif_testing import FakeLineIO
            >>> Scpi(FakeLineIO({"MEAS:CURR?": "+1.8000E-01"})).query_float("MEAS:CURR?")
            0.18
            >>> Scpi(FakeLineIO({"MEAS:CURR?": "OVLD"})).query_float("MEAS:CURR?")
            Traceback (most recent call last):
            ...
            mastif.resources.errors.ProtocolError: MEAS:CURR? returned 'OVLD', expected a number
        """
        reply = self.query(command, timeout)
        try:
            value = float(reply)
        except ValueError:
            raise ProtocolError(f"{command} returned {reply!r}, expected a number") from None
        if abs(value) >= 9.9e37:
            raise ProtocolError(f"{command} returned overflow/invalid marker {reply!r}")
        return value

    def query_quantity(self, command: str, unit: str, timeout: float | None = None) -> Quantity:
        """Send a query and return the number as a `Quantity` in ``unit``.

        Args:
            command: The query.
            unit: The unit the instrument reports in.
            timeout: Seconds to wait for the reply.

        Returns:
            The quantity.

        Examples:
            >>> from mastif_testing import FakeLineIO
            >>> Scpi(FakeLineIO({"FREQ?": "2.4E9"})).query_quantity("FREQ?", "Hz").to("GHz")
            Quantity(value=2.4, unit='GHz')
        """
        return Quantity(value=self.query_float(command, timeout), unit=unit)

    def identify(self) -> Identity:
        """Ask ``*IDN?`` and parse the standard ``vendor,model,serial,revision`` reply.

        Use this as a SCPI driver's ``identify()``, so the station can check the profile's
        ``expect:`` block.

        Returns:
            The identity; fields missing from the reply are ``None``.

        Examples:
            >>> from mastif_testing import FakeLineIO
            >>> Scpi(FakeLineIO({"*IDN?": "ACME, PSU-X, A123, 1.4"})).identify()
            Identity(vendor='ACME', model='PSU-X', serial='A123', revision='1.4', extra={})
        """
        parts = [p.strip() or None for p in self.query("*IDN?").split(",")]
        parts += [None] * (4 - len(parts))
        return Identity(vendor=parts[0], model=parts[1], serial=parts[2], revision=parts[3])

    def errors(self, limit: int = 32) -> list[str]:
        """Drain the instrument's error queue (``SYST:ERR?``) and return its entries.

        Args:
            limit: Stop after this many entries, in case a device never reports empty.

        Returns:
            Error entries such as ``'-113,"Undefined header"'``; empty if none.

        Examples:
            >>> from mastif_testing import FakeLineIO
            >>> io = FakeLineIO({"SYST:ERR?": ['-113,"Undefined header"', '0,"No error"']})
            >>> Scpi(io).errors()
            ['-113,"Undefined header"']
        """
        found = []
        for _ in range(limit):
            entry = self.query("SYST:ERR?")
            code = entry.split(",", 1)[0].strip()
            if code in ("0", "+0"):
                break
            found.append(entry)
        return found

    def raise_on_errors(self, after: str = "") -> None:
        """Raise if the error queue holds anything.

        Args:
            after: The command just sent, for the error message.

        Raises:
            ProtocolError: Listing every queued error.

        Examples:
            >>> from mastif_testing import FakeLineIO
            >>> Scpi(FakeLineIO({"SYST:ERR?": '0,"No error"'})).raise_on_errors()
        """
        errs = self.errors()
        if errs:
            context = f" after {after!r}" if after else ""
            raise ProtocolError(f"instrument reported{context}: {'; '.join(errs)}")

    def reset(self) -> None:
        """Return the instrument to its default state (``*RST``) and clear status (``*CLS``).

        Useful in a driver's ``open()``, so every run starts from a known state.

        Examples:
            >>> from mastif_testing import FakeLineIO
            >>> io = FakeLineIO()
            >>> Scpi(io).reset()
            >>> io.written
            ['*RST', '*CLS']
        """
        self.io.write_line("*RST")
        self.io.write_line("*CLS")

    def wait(self, timeout: float | None = None) -> None:
        """Block until all pending operations complete (``*OPC?``).

        Args:
            timeout: Seconds to wait, e.g. longer for a slow sweep.

        Raises:
            ProtocolError: If the reply is not ``1``.

        Examples:
            >>> from mastif_testing import FakeLineIO
            >>> Scpi(FakeLineIO({"*OPC?": "1"})).wait()
        """
        reply = self.query("*OPC?", timeout)
        if reply not in ("1", "+1"):
            raise ProtocolError(f"*OPC? returned {reply!r}, expected 1")
