"""Physical quantities: numbers that carry their unit.

Why this exists:
    Nearly everything a test station handles is a physical value: a supply voltage, a
    current draw, a frequency, an RF power level. A bare ``0.25`` can't tell you whether
    it means amps or milliamps, and confusing the two produces a verdict that looks
    right but is wrong. mastif carries the unit with the number from the instrument
    driver through to the final report, and converts only when two values are combined
    or compared.

Where it fits:
    This module sits at the bottom of the stack (`mastif.kernel`). Org-defined driver
    contracts take and return quantities (``set_voltage(12 * V)``). Test tasks record
    them as `Measurement` results. `Limits` compare them against specification ranges.

How to use it:
    Multiply a number by a unit constant::

        from mastif.kernel.units import V, mA, GHz, dBm

        supply = 12 * V
        max_current = 250 * mA
        carrier = 2.4 * GHz
        rf_level = -10 * dBm

    Units in the built-in table (SI prefixes of V, A, W, Hz, s, ohm, plus deg/rad, degC,
    %, dB, dBm) convert within their dimension. Any other symbol (``"psi"``, ``"rpm"``)
    is accepted as its own dimension and converts only to itself, so organisations never
    have to register units.

    Logarithmic units (dB, dBm) never convert to linear units. They combine using the
    usual RF rules: ``dBm + dB -> dBm`` (a level plus a gain), ``dBm - dBm -> dB`` (the
    difference between two levels) and ``dB + dB -> dB``. Adding two absolute levels
    (``dBm + dBm``) has no meaning, so it is rejected.

See ADR-0001 for why mastif uses this small module rather than pint.
"""

import math
from dataclasses import dataclass
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, field_validator

from mastif.kernel.errors import UnitError


@dataclass(frozen=True, slots=True)
class _UnitDef:
    """Conversion facts for one unit symbol.

    Two units can be converted when they share a ``dimension``. ``factor`` is the size of
    one unit expressed in the dimension's base unit (``mV`` has factor ``1e-3`` in
    dimension ``V``). ``log`` marks dB-family units, which follow different arithmetic.

    Example:
        >>> _UnitDef("V", 1e-3)
        _UnitDef(dimension='V', factor=0.001, log=False)
    """

    dimension: str
    factor: float
    log: bool = False


def _scaled(base: str, prefixes: dict[str, float]) -> dict[str, _UnitDef]:
    """Build table entries for a base unit and its SI-prefixed variants.

    Used once, at import time, to build the built-in unit table without writing every
    prefix by hand.

    Args:
        base: The base unit symbol, e.g. ``"V"``.
        prefixes: Prefix symbol to multiplier, e.g. ``{"m": 1e-3}``.

    Returns:
        Mapping of symbol to definition, including the base unit itself.

    Example:
        >>> sorted(_scaled("V", {"m": 1e-3}))
        ['V', 'mV']
        >>> _scaled("V", {"m": 1e-3})["mV"].factor
        0.001
    """
    table = {base: _UnitDef(base, 1.0)}
    for prefix, factor in prefixes.items():
        table[prefix + base] = _UnitDef(base, factor)
    return table


_SMALL = {"m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12}
_LARGE = {"k": 1e3, "M": 1e6, "G": 1e9}

_UNITS: dict[str, _UnitDef] = {
    "": _UnitDef("", 1.0),
    "%": _UnitDef("", 0.01),
    **_scaled("V", _SMALL | _LARGE),
    **_scaled("A", _SMALL | {"k": 1e3}),
    **_scaled("W", _SMALL | _LARGE),
    **_scaled("Hz", _LARGE),
    **_scaled("s", _SMALL),
    **_scaled("ohm", {"m": 1e-3} | _LARGE),
    "deg": _UnitDef("rad", math.pi / 180.0),
    "rad": _UnitDef("rad", 1.0),
    "degC": _UnitDef("degC", 1.0),
    "dB": _UnitDef("dB", 1.0, log=True),
    "dBm": _UnitDef("dBm", 1.0, log=True),
}


def _lookup(symbol: str) -> _UnitDef:
    """Return the conversion facts for a unit symbol.

    Unknown symbols are not an error. They become their own dimension, which lets
    organisations use any unit without registering it.

    Args:
        symbol: Unit symbol.

    Returns:
        The built-in definition, or a standalone dimension for unknown symbols.

    Example:
        >>> _lookup("mA").dimension
        'A'
        >>> _lookup("psi")
        _UnitDef(dimension='psi', factor=1.0, log=False)
    """
    return _UNITS.get(symbol) or _UnitDef(symbol, 1.0)


def convertible(a: str, b: str) -> bool:
    """Tell whether a value in unit ``a`` can be expressed in unit ``b``.

    Use this when building generic tooling (report columns, UI unit pickers) that has to
    decide whether two values can be compared without raising.

    Args:
        a: First unit symbol.
        b: Second unit symbol.

    Returns:
        True if both units share a dimension.

    Example:
        >>> convertible("mV", "kV")
        True
        >>> convertible("V", "A")
        False
        >>> convertible("dBm", "mW")
        False
    """
    return _lookup(a).dimension == _lookup(b).dimension


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a bare magnitude from one unit to another.

    This is the low-level primitive behind `Quantity.to` and limit evaluation. Most code
    should call ``quantity.to("V")`` instead. Use `convert` when you hold plain floats,
    for example from a CSV file or a driver's raw response.

    Args:
        value: Magnitude expressed in ``from_unit``.
        from_unit: Source unit symbol.
        to_unit: Target unit symbol.

    Returns:
        The magnitude expressed in ``to_unit``.

    Raises:
        UnitError: If the units have different dimensions.

    Example:
        >>> convert(1500.0, "mV", "V")
        1.5
        >>> convert(1.0, "V", "A")
        Traceback (most recent call last):
        ...
        mastif.kernel.errors.UnitError: cannot convert 'V' to 'A'
    """
    src, dst = _lookup(from_unit), _lookup(to_unit)
    if src.dimension != dst.dimension:
        raise UnitError(f"cannot convert {from_unit!r} to {to_unit!r}")
    return value * src.factor / dst.factor


class Quantity(BaseModel):
    """A magnitude together with its unit, e.g. ``12 V`` or ``-10 dBm``.

    Quantities are what driver contracts exchange and what measurements record. They
    are immutable Pydantic models, so they validate, hash, and serialise to JSON as
    ``{"value": 12.0, "unit": "V"}``. That means they travel unchanged through events,
    run snapshots and the network API.

    Arithmetic and comparisons convert the right-hand operand to the left-hand unit, so
    ``1 * V + 500 * mV == 1.5 * V``. Bare numbers in arithmetic count as dimensionless.

    Attributes:
        value: The magnitude. NaN is rejected.
        unit: The unit symbol; ``""`` means dimensionless.

    Example:
        >>> from mastif.kernel.units import V, mV
        >>> q = 3.3 * V
        >>> q
        Quantity(value=3.3, unit='V')
        >>> str(q.to("mV"))
        '3300 mV'
        >>> q > 3000 * mV
        True
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float
    unit: str = ""

    @field_validator("value")
    @classmethod
    def _finite(cls, v: float) -> float:
        """Reject NaN, so comparisons and therefore verdicts stay meaningful.

        Every comparison with NaN is false, so a NaN reading would quietly fall outside
        every limit. mastif rejects it at the source instead, and a driver that cannot
        read a value must raise an error.

        Args:
            v: Candidate magnitude.

        Returns:
            The magnitude unchanged.

        Raises:
            ValueError: If the magnitude is NaN (reported by Pydantic as a validation
                error).

        Example:
            >>> Quantity(value=float("nan"), unit="V")
            Traceback (most recent call last):
            ...
            pydantic_core._pydantic_core.ValidationError: 1 validation error for Quantity
            ...
        """
        if math.isnan(v):
            raise ValueError("quantity value must not be NaN")
        return v

    @property
    def is_log(self) -> bool:
        """Whether the unit is logarithmic (dB family), which changes arithmetic rules.

        Example:
            >>> from mastif.kernel.units import dBm, mW
            >>> (0 * dBm).is_log, (1 * mW).is_log
            (True, False)
        """
        return _lookup(self.unit).log

    def to(self, unit: str) -> Self:
        """Express this quantity in another unit of the same dimension.

        Use this when a driver or report needs a value in a specific unit. For example,
        a SCPI command might expect hertz while the test author wrote ``2.4 * GHz``.

        Args:
            unit: Target unit symbol.

        Returns:
            A new quantity in ``unit``; the original is unchanged.

        Raises:
            UnitError: If the units have different dimensions.

        Example:
            >>> from mastif.kernel.units import GHz
            >>> (2.4 * GHz).to("Hz")
            Quantity(value=2400000000.0, unit='Hz')
        """
        return type(self)(value=convert(self.value, self.unit, unit), unit=unit)

    def magnitude(self, unit: str | None = None) -> float:
        """Return the bare number, optionally converted first.

        This is the usual last step inside a driver, just before formatting a command
        string: ``io.write(f"VOLT {v.magnitude('V'):.3f}")``.

        Args:
            unit: Unit to express the magnitude in; ``None`` keeps the current unit.

        Returns:
            The magnitude as a float.

        Example:
            >>> from mastif.kernel.units import mA
            >>> (250 * mA).magnitude("A")
            0.25
            >>> (250 * mA).magnitude()
            250.0
        """
        return self.value if unit is None else convert(self.value, self.unit, unit)

    def _coerce(self, other: object) -> "Quantity":
        """Turn the other operand of an operator into a quantity.

        Bare numbers become dimensionless quantities, so ``(5 * V) + 1`` fails loudly
        instead of silently assuming volts.

        Args:
            other: The other operand.

        Returns:
            The operand as a quantity.

        Raises:
            TypeError: If the operand is neither a number nor a quantity.

        Example:
            >>> from mastif.kernel.units import V
            >>> (1 * V)._coerce(2)
            Quantity(value=2.0, unit='')
        """
        if isinstance(other, Quantity):
            return other
        if isinstance(other, int | float):
            return Quantity(value=float(other), unit="")
        raise TypeError(f"unsupported operand {other!r}")

    def __add__(self, other: object) -> "Quantity":
        """Add another quantity, converted to this quantity's unit.

        dB-family operands follow the RF rules described in the module docstring.

        Args:
            other: A quantity of the same dimension, or a dB value for dB-family units.

        Returns:
            The sum, in this quantity's unit.

        Raises:
            UnitError: If the dimensions differ or the dB combination has no meaning.

        Example:
            >>> from mastif.kernel.units import V, mV, dB, dBm
            >>> 1 * V + 500 * mV
            Quantity(value=1.5, unit='V')
            >>> -10 * dBm + 3 * dB
            Quantity(value=-7.0, unit='dBm')
        """
        o = self._coerce(other)
        if self.is_log or o.is_log:
            return _log_add(self, o, sign=1.0)
        return Quantity(value=self.value + o.magnitude(self.unit), unit=self.unit)

    def __sub__(self, other: object) -> "Quantity":
        """Subtract another quantity, converted to this quantity's unit.

        Subtracting two levels in the same dB unit gives a relative dB value, such as a
        gain or a loss.

        Args:
            other: A quantity of the same dimension, or a dB-family quantity.

        Returns:
            The difference.

        Raises:
            UnitError: If the dimensions differ or the dB combination has no meaning.

        Example:
            >>> from mastif.kernel.units import dBm
            >>> (5 * dBm) - (-15 * dBm)
            Quantity(value=20.0, unit='dB')
        """
        o = self._coerce(other)
        if self.is_log or o.is_log:
            return _log_add(self, o, sign=-1.0)
        return Quantity(value=self.value - o.magnitude(self.unit), unit=self.unit)

    def __mul__(self, k: float) -> "Quantity":
        """Scale by a plain number, for example to average or apply a ratio.

        dB-family quantities cannot be scaled: doubling a dBm level has no physical
        meaning.

        Args:
            k: Scale factor.

        Returns:
            The scaled quantity.

        Raises:
            UnitError: If this quantity is logarithmic.

        Example:
            >>> from mastif.kernel.units import mA
            >>> (100 * mA) * 3
            Quantity(value=300.0, unit='mA')
        """
        if not isinstance(k, int | float):
            return NotImplemented
        if self.is_log:
            raise UnitError("logarithmic quantities cannot be scaled")
        return Quantity(value=self.value * k, unit=self.unit)

    __rmul__ = __mul__

    def __truediv__(self, k: float) -> "Quantity":
        """Divide by a plain number, for example to average several readings.

        Args:
            k: Divisor.

        Returns:
            The scaled quantity.

        Example:
            >>> from mastif.kernel.units import V
            >>> (9 * V) / 3
            Quantity(value=3.0, unit='V')
        """
        return self * (1.0 / k)

    def __neg__(self) -> "Quantity":
        """Negate the magnitude, keeping the unit.

        Returns:
            The negated quantity.

        Example:
            >>> from mastif.kernel.units import dB
            >>> -(3 * dB)
            Quantity(value=-3.0, unit='dB')
        """
        return Quantity(value=-self.value, unit=self.unit)

    def _cmp_value(self, other: object) -> float:
        """Convert the right-hand side of a comparison to this quantity's unit.

        Args:
            other: A quantity of the same dimension.

        Returns:
            The other operand's magnitude in this quantity's unit.

        Raises:
            UnitError: If the dimensions differ.

        Example:
            >>> from mastif.kernel.units import V, mV
            >>> (1 * V)._cmp_value(250 * mV)
            0.25
        """
        return self._coerce(other).magnitude(self.unit)

    def __lt__(self, other: object) -> bool:
        """Less than, after converting ``other`` to this unit.

        Example:
            >>> from mastif.kernel.units import A, mA
            >>> 300 * mA < 1 * A
            True
        """
        return self.value < self._cmp_value(other)

    def __le__(self, other: object) -> bool:
        """Less than or equal, after converting ``other`` to this unit.

        Example:
            >>> from mastif.kernel.units import V, mV
            >>> 1 * V <= 1000 * mV
            True
        """
        return self.value <= self._cmp_value(other)

    def __gt__(self, other: object) -> bool:
        """Greater than, after converting ``other`` to this unit.

        Example:
            >>> from mastif.kernel.units import GHz, MHz
            >>> 1 * GHz > 999 * MHz
            True
        """
        return self.value > self._cmp_value(other)

    def __ge__(self, other: object) -> bool:
        """Greater than or equal, after converting ``other`` to this unit.

        Example:
            >>> from mastif.kernel.units import s, ms
            >>> 1 * s >= 1000 * ms
            True
        """
        return self.value >= self._cmp_value(other)

    def __eq__(self, other: object) -> bool:
        """Equal when the units are compatible and the magnitudes match after conversion.

        A tiny relative tolerance (1e-12) absorbs floating-point noise from conversions,
        so ``2400 * MHz == 2.4 * GHz`` holds.

        Example:
            >>> from mastif.kernel.units import GHz, MHz, V, A
            >>> 2400 * MHz == 2.4 * GHz
            True
            >>> 1 * V == 1 * A
            False
        """
        if not isinstance(other, Quantity):
            return NotImplemented
        return convertible(self.unit, other.unit) and math.isclose(
            self.value, other.magnitude(self.unit), rel_tol=1e-12, abs_tol=1e-15
        )

    def __hash__(self) -> int:
        """Hash on the value in the dimension's base unit, consistent with ``==``.

        Example:
            >>> from mastif.kernel.units import V, mV
            >>> hash(1 * V) == hash(1000 * mV)
            True
        """
        d = _lookup(self.unit)
        return hash((d.dimension, round(self.value * d.factor, 12)))

    def __str__(self) -> str:
        """Render for humans (logs, reports) as ``"<value> <unit>"``.

        Example:
            >>> from mastif.kernel.units import dBm
            >>> str(-10.5 * dBm)
            '-10.5 dBm'
            >>> str(Quantity(value=3.0))
            '3'
        """
        return f"{self.value:g} {self.unit}".rstrip()


def _log_add(a: Quantity, b: Quantity, sign: float) -> Quantity:
    """Add or subtract dB-family quantities following RF conventions.

    The rules are: level ± gain gives a level (``dBm + dB -> dBm``), gain + level gives
    a level, gain ± gain gives a gain, and level - level of the same unit gives a gain
    (``dBm - dBm -> dB``). Any other combination is rejected, including mixing dB with
    linear units.

    Args:
        a: Left operand.
        b: Right operand.
        sign: ``1.0`` to add, ``-1.0`` to subtract.

    Returns:
        The result, in the unit the convention gives.

    Raises:
        UnitError: For combinations with no meaning (``dBm + dBm``, dB with linear).

    Example:
        >>> from mastif.kernel.units import dB, dBm
        >>> _log_add(10 * dBm, 3 * dB, 1.0)
        Quantity(value=13.0, unit='dBm')
        >>> _log_add(10 * dBm, 3 * dBm, 1.0)
        Traceback (most recent call last):
        ...
        mastif.kernel.errors.UnitError: cannot add 'dBm' and 'dBm'
    """
    if not (a.is_log and b.is_log):
        raise UnitError(f"cannot combine {a.unit!r} with {b.unit!r}")
    value = a.value + sign * b.value
    match (a.unit, b.unit, sign > 0):
        case (u, "dB", _):
            return Quantity(value=value, unit=u)
        case ("dB", u, True):
            return Quantity(value=value, unit=u)
        case (u1, u2, False) if u1 == u2:
            return Quantity(value=value, unit="dB")
    raise UnitError(f"cannot {'add' if sign > 0 else 'subtract'} {a.unit!r} and {b.unit!r}")


class Unit:
    """A unit constant that builds quantities when multiplied by a number.

    Unit constants exist so test code reads like an engineering spec: ``12 * V`` rather
    than ``Quantity(value=12, unit="V")``. The common constants are defined at the bottom
    of this module. Orgs can create their own for any symbol.

    Example:
        >>> psi = Unit("psi")
        >>> 30 * psi
        Quantity(value=30.0, unit='psi')
    """

    __slots__ = ("symbol",)

    def __init__(self, symbol: str) -> None:
        """Create a unit constant.

        Args:
            symbol: Unit symbol, e.g. ``"V"`` or an org-specific ``"rpm"``.

        Example:
            >>> Unit("rpm").symbol
            'rpm'
        """
        self.symbol = symbol

    def __rmul__(self, value: float) -> Quantity:
        """Build a quantity from ``number * unit``.

        Args:
            value: Magnitude.

        Returns:
            The quantity ``value`` in this unit.

        Example:
            >>> 5 * Unit("V")
            Quantity(value=5.0, unit='V')
        """
        if not isinstance(value, int | float):
            return NotImplemented
        return Quantity(value=float(value), unit=self.symbol)

    def __repr__(self) -> str:
        """Render as ``Unit('V')`` for debugging.

        Example:
            >>> Unit("V")
            Unit('V')
        """
        return f"Unit({self.symbol!r})"


def as_quantity(value: Any, unit: str = "") -> Quantity:
    """Accept either a quantity or a bare number and return a quantity.

    Useful at boundaries that receive loosely typed data, such as YAML config or a
    driver's parsed response, when a sensible default unit is known.

    Args:
        value: A quantity (returned unchanged), or a number interpreted in ``unit``.
        unit: Unit for bare numbers.

    Returns:
        The quantity.

    Example:
        >>> as_quantity(5, "V")
        Quantity(value=5.0, unit='V')
        >>> from mastif.kernel.units import mV
        >>> as_quantity(500 * mV, "V")
        Quantity(value=500.0, unit='mV')
    """
    if isinstance(value, Quantity):
        return value
    return Quantity(value=float(value), unit=unit)


V, mV, uV, kV = Unit("V"), Unit("mV"), Unit("uV"), Unit("kV")
A, mA, uA = Unit("A"), Unit("mA"), Unit("uA")
W, mW = Unit("W"), Unit("mW")
Hz, kHz, MHz, GHz = Unit("Hz"), Unit("kHz"), Unit("MHz"), Unit("GHz")
s, ms, us, ns = Unit("s"), Unit("ms"), Unit("us"), Unit("ns")
ohm, kohm = Unit("ohm"), Unit("kohm")
deg, rad, degC = Unit("deg"), Unit("rad"), Unit("degC")
dB, dBm = Unit("dB"), Unit("dBm")
percent = Unit("%")

# Documentation aliases for contract signatures, e.g. ``def set_voltage(self, v: Volts)``.
# They tell readers the intended dimension but are not checked statically.
type Volts = Quantity
type Amps = Quantity
type Watts = Quantity
type Hertz = Quantity
type Seconds = Quantity
type Decibels = Quantity
