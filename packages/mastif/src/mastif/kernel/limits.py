"""Acceptance limits, and the pure function that turns a value into a verdict.

Why this exists:
    A test only means something when it states what counts as acceptable. A
    specification usually says "between 4.75 V and 5.25 V", and often adds a marginal
    zone: "between 4.5 V and 5.5 V is tolerated, but flag it". mastif models this
    directly, and judges values with a pure function (`evaluate`) that has no hidden
    state. The same value and limits therefore always give the same verdict, whether
    the code runs on a station, in a resumed run or in a report regenerated a year
    later.

Where it fits:
    `Limits` are declared by test authors, either in code or in org config files. They
    are attached to `Measurement` and `Table` results (`mastif.kernel.results`), which
    compute their own verdicts with `evaluate`. The engine then combines those verdicts
    upwards using `mastif.kernel.verdict.aggregate`.

How to use it::

    from mastif.kernel.limits import Limits, Range
    from mastif.kernel.units import V, mA, dB

    supply = Limits.between(4.75 * V, 5.25 * V, warn_low=4.5 * V, warn_high=5.5 * V)
    current = Limits.at_most(250 * mA)
    gain = Limits(passing=Range(18 * dB, 22 * dB))

A value inside ``passing`` is PASS, a value inside the wider ``warning`` range is WARN,
and anything else is FAIL.
"""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from mastif.kernel.errors import LimitsError, UnitError
from mastif.kernel.units import Quantity, convert
from mastif.kernel.verdict import Verdict

type Bound = float | Quantity | None
"""Range endpoint: a bare magnitude, a quantity with units, or `None` for no bound."""


def _split(bound: Bound) -> tuple[float | None, str | None]:
    """Separate a bound into its magnitude and its unit.

    Range constructors accept either bare numbers or quantities, and this helper is how
    they tell the two apart.

    Args:
        bound: A number, a quantity or ``None``.

    Returns:
        ``(magnitude, unit)``; the unit is ``None`` for bare numbers and for ``None``.

    Examples:
        >>> from mastif.kernel.units import V
        >>> _split(5 * V)
        (5.0, 'V')
        >>> _split(5.0)
        (5.0, None)
    """
    if isinstance(bound, Quantity):
        return bound.value, bound.unit
    return bound, None


class Range(BaseModel):
    """An interval of acceptable values in a single unit; either end may be open.

    A range is the building block of `Limits`. Leave ``low`` or ``high`` as ``None`` for
    a one-sided range, such as "at most 250 mA". Bounds may be given as quantities, and
    the first unit found becomes the range unit, with the other bound converted to it.

    Attributes:
        low: Lower bound, or ``None`` for no lower bound.
        high: Upper bound, or ``None`` for no upper bound.
        inclusive: Whether a value exactly on a bound counts as inside.
        unit: Unit of both bounds; ``None`` means the range is unitless.

    Examples:
        >>> from mastif.kernel.units import V, mV
        >>> r = Range(4500 * mV, 5.5 * V)
        >>> r.low, r.high, r.unit
        (4500.0, 5500.0, 'mV')
        >>> Range(high=0.25).contains(0.1)
        True
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    low: float | None = None
    high: float | None = None
    inclusive: bool = True
    unit: str | None = None

    def __init__(
        self,
        low: Bound = None,
        high: Bound = None,
        *,
        inclusive: bool = True,
        unit: str | None = None,
        **data: Any,
    ) -> None:
        """Create a range from numbers or quantities.

        This typed constructor lets static type checkers accept quantities as bounds.
        Pydantic then reduces them to floats in one unit (see `_accept_quantities`).

        Args:
            low: Lower bound; a quantity's unit becomes the range unit.
            high: Upper bound; converted to the range unit.
            inclusive: Whether values equal to a bound are inside the range.
            unit: Explicit unit; overrides units taken from the bounds.
            **data: Other fields, as found in serialised input.

        Raises:
            UnitError: If the bounds have incompatible units.
            LimitsError: If the range has no bounds or ``low > high``.

        Examples:
            >>> from mastif.kernel.units import dB
            >>> Range(18 * dB, 22 * dB)
            Range(low=18.0, high=22.0, inclusive=True, unit='dB')
            >>> Range(0, 10, inclusive=False).contains(10)
            False
        """
        super().__init__(low=low, high=high, inclusive=inclusive, unit=unit, **data)

    @model_validator(mode="before")
    @classmethod
    def _accept_quantities(cls, data: Any) -> Any:
        """Reduce quantity bounds to floats in one unit before field validation.

        Order of precedence for the unit: an explicit ``unit``, then the unit of ``low``,
        then the unit of ``high``.

        Args:
            data: Raw input mapping.

        Returns:
            The input with bounds as floats and ``unit`` filled in.

        Raises:
            UnitError: If the two bounds have incompatible units.

        Examples:
            >>> from mastif.kernel.units import V, mV
            >>> Range._accept_quantities({"low": 1 * V, "high": 1500 * mV})
            {'low': 1.0, 'high': 1.5, 'unit': 'V'}
        """
        if not isinstance(data, dict):
            return data
        low, low_unit = _split(data.get("low"))
        high, high_unit = _split(data.get("high"))
        unit = data.get("unit") or low_unit or high_unit
        if low is not None and low_unit is not None and unit is not None:
            low = convert(low, low_unit, unit)
        if high is not None and high_unit is not None and unit is not None:
            high = convert(high, high_unit, unit)
        return {**data, "low": low, "high": high, "unit": unit}

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        """Reject ranges that cannot hold any meaningful value.

        A range with no bounds at all would accept everything, which almost always means
        a configuration mistake. A range with ``low > high`` would accept nothing.

        Returns:
            The range.

        Raises:
            LimitsError: If both bounds are missing or ``low > high``.

        Examples:
            >>> Range(2.0, 1.0)
            Traceback (most recent call last):
            ...
            mastif.kernel.errors.LimitsError: range low 2.0 is above high 1.0
        """
        if self.low is None and self.high is None:
            raise LimitsError("a range needs at least one bound")
        if self.low is not None and self.high is not None and self.low > self.high:
            raise LimitsError(f"range low {self.low} is above high {self.high}")
        return self

    def contains(self, value: float) -> bool:
        """Tell whether a magnitude lies inside the range.

        The value must already be in the range's unit. `evaluate` takes care of that
        conversion, which is why test code normally calls `evaluate` and not this.

        Args:
            value: Magnitude in the range's unit.

        Returns:
            True if the value is inside the range.

        Examples:
            >>> Range(4.75, 5.25).contains(5.25)
            True
            >>> Range(4.75, 5.25, inclusive=False).contains(5.25)
            False
        """
        if self.inclusive:
            return (self.low is None or value >= self.low) and (
                self.high is None or value <= self.high
            )
        return (self.low is None or value > self.low) and (self.high is None or value < self.high)

    def in_unit(self, unit: str | None) -> "Range":
        """Return the same range expressed in another unit.

        `Limits` uses this to bring its warning range into the passing range's unit, so
        that a single conversion of the measured value is enough.

        Args:
            unit: Target unit. A unitless range can only stay unitless.

        Returns:
            The converted range (``self`` if the unit already matches).

        Raises:
            UnitError: If a unitless range is mixed with a unit-bearing one, or the
                dimensions differ.

        Examples:
            >>> from mastif.kernel.units import V
            >>> Range(4.5 * V, 5.5 * V).in_unit("mV")
            Range(low=4500.0, high=5500.0, inclusive=True, unit='mV')
        """
        if unit == self.unit:
            return self
        if unit is None or self.unit is None:
            raise UnitError(f"cannot mix unit {self.unit!r} with {unit!r}")
        src = self.unit

        def conv(x: float | None) -> float | None:
            """Convert one bound, leaving an open bound open.

            Examples:
                ``conv(None)`` returns ``None``; ``conv(4.5)`` returns ``4500.0`` for V to mV.
            """
            return None if x is None else convert(x, src, unit)

        return Range(low=conv(self.low), high=conv(self.high), inclusive=self.inclusive, unit=unit)


class Limits(BaseModel):
    """The acceptance criteria for one value: a passing range plus an optional warning range.

    Judging a value gives one of three outcomes:

    - inside ``passing``: **PASS**
    - outside ``passing`` but inside ``warning``: **WARN** (marginal; the unit is
      accepted but the result stands out in reports)
    - anything else: **FAIL**

    The warning range must contain the passing range. It is stored in the passing
    range's unit.

    Most code uses the shortcut constructors `between`, `at_least` and `at_most`.

    Attributes:
        passing: Range for PASS.
        warning: Wider range for WARN, or ``None`` for no marginal zone.

    Examples:
        >>> from mastif.kernel.units import V
        >>> lim = Limits.between(4.75 * V, 5.25 * V, warn_low=4.5 * V, warn_high=5.5 * V)
        >>> evaluate(5.4 * V, lim)
        <Verdict.WARN: 'warn'>
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    passing: Range
    warning: Range | None = None

    @model_validator(mode="after")
    def _warning_is_wider(self) -> Self:
        """Bring the warning range into the passing unit and check it is the wider one.

        A warning range narrower than the passing range would mean "marginal" values are
        better than "passing" ones, which is always a specification mistake.

        Returns:
            The limits.

        Raises:
            LimitsError: If the warning range does not contain the passing range.

        Examples:
            >>> Limits.between(0.0, 10.0, warn_low=1.0)
            Traceback (most recent call last):
            ...
            mastif.kernel.errors.LimitsError: warning range must contain the passing range
        """
        if self.warning is None:
            return self
        w = self.warning.in_unit(self.passing.unit)
        p = self.passing
        low_ok = w.low is None or (p.low is not None and w.low <= p.low)
        high_ok = w.high is None or (p.high is not None and w.high >= p.high)
        if not (low_ok and high_ok):
            raise LimitsError("warning range must contain the passing range")
        object.__setattr__(self, "warning", w)
        return self

    @property
    def unit(self) -> str | None:
        """Unit the limits are expressed in (the passing range's unit).

        Examples:
            >>> from mastif.kernel.units import mA
            >>> Limits.at_most(250 * mA).unit
            'mA'
        """
        return self.passing.unit

    @classmethod
    def between(
        cls,
        low: Bound,
        high: Bound,
        *,
        warn_low: Bound = None,
        warn_high: Bound = None,
        inclusive: bool = True,
    ) -> "Limits":
        """Build two-sided limits, the most common form in a test specification.

        The warning bounds are optional and independent. Give only ``warn_high`` to
        tolerate marginal values on the high side only.

        Args:
            low: Passing lower bound.
            high: Passing upper bound.
            warn_low: Warning lower bound (at or below ``low``).
            warn_high: Warning upper bound (at or above ``high``).
            inclusive: Whether all bounds are inclusive.

        Returns:
            The limits.

        Examples:
            >>> from mastif.kernel.units import V
            >>> lim = Limits.between(4.75 * V, 5.25 * V)
            >>> evaluate(5 * V, lim), evaluate(6 * V, lim)
            (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>)
        """
        passing = Range.model_validate({"low": low, "high": high, "inclusive": inclusive})
        warning = None
        if warn_low is not None or warn_high is not None:
            warning = Range.model_validate(
                {
                    "low": warn_low if warn_low is not None else low,
                    "high": warn_high if warn_high is not None else high,
                    "inclusive": inclusive,
                    "unit": passing.unit,
                }
            )
        return cls(passing=passing, warning=warning)

    @classmethod
    def at_least(cls, low: Bound, *, warn_low: Bound = None, inclusive: bool = True) -> "Limits":
        """Build lower-bound-only limits, e.g. "output power at least 10 dBm".

        Args:
            low: Passing lower bound.
            warn_low: Warning lower bound (at or below ``low``).
            inclusive: Whether the bounds are inclusive.

        Returns:
            The limits.

        Examples:
            >>> from mastif.kernel.units import dBm
            >>> evaluate(9.5 * dBm, Limits.at_least(10 * dBm, warn_low=9 * dBm))
            <Verdict.WARN: 'warn'>
        """
        return cls.between(low, None, warn_low=warn_low, inclusive=inclusive)

    @classmethod
    def at_most(cls, high: Bound, *, warn_high: Bound = None, inclusive: bool = True) -> "Limits":
        """Build upper-bound-only limits, e.g. "standby current at most 250 mA".

        Args:
            high: Passing upper bound.
            warn_high: Warning upper bound (at or above ``high``).
            inclusive: Whether the bounds are inclusive.

        Returns:
            The limits.

        Examples:
            >>> from mastif.kernel.units import mA
            >>> evaluate(300 * mA, Limits.at_most(250 * mA))
            <Verdict.FAIL: 'fail'>
        """
        return cls.between(None, high, warn_high=warn_high, inclusive=inclusive)


class IndexedLimits(BaseModel):
    """A family of limits for one quantity, where the acceptable range depends on an index.

    Use this when the same quantity is measured repeatedly over something you iterate
    on (channels, ports, frequency points, temperature steps) and the specification
    gives a different range for some of those points. Typically the index is a column
    of a `Table`, and each row is judged against the limits for its own index.

    For example, output power is measured on channels 1-8. Channels 1-6 must be between
    9 and 11 dBm, and channels 7 and 8 drive longer cables, so 8 to 10 dBm is acceptable
    for them.

    For a single value, call `for_index` and judge it with `evaluate`. If there is no
    default, an index without its own entry is an error rather than being silently
    accepted. This catches a specification that doesn't cover every point.

    Attributes:
        by_index: Limits for specific indices. Keys are stored as text so that ``7`` and
            ``"7"`` name the same index, including after a JSON round trip.
        default: Limits for indices not listed; ``None`` makes unlisted indices an error.

    Examples:
        >>> from mastif.kernel.units import dBm
        >>> normal = Limits.between(9 * dBm, 11 * dBm)
        >>> long_cable = Limits.between(8 * dBm, 10 * dBm)
        >>> power = IndexedLimits(by_index={7: long_cable, 8: long_cable}, default=normal)
        >>> evaluate(8.4 * dBm, power.for_index(7)), evaluate(8.4 * dBm, power.for_index(1))
        (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    by_index: dict[str, Limits]
    default: Limits | None = None

    @field_validator("by_index", mode="before")
    @classmethod
    def _text_keys(cls, v: Any) -> Any:
        """Store index keys as text, so that ints and strings name the same index.

        JSON object keys are always strings, so without this an index of ``7`` would no
        longer match after limits were saved and reloaded.

        Args:
            v: Raw mapping.

        Returns:
            The mapping with ``str`` keys.

        Examples:
            >>> IndexedLimits._text_keys({1: "a", "2": "b"})
            {'1': 'a', '2': 'b'}
        """
        return {str(k): lim for k, lim in v.items()} if isinstance(v, dict) else v

    def for_index(self, index: object) -> Limits:
        """Return the limits that apply at one index.

        Args:
            index: The index, compared by its text form, so ``7`` and ``"7"`` are the
                same index.

        Returns:
            The limits listed for that index, or the default.

        Raises:
            LimitsError: If the index is not listed and there is no default.

        Examples:
            >>> lim = IndexedLimits(by_index={1: Limits.at_most(1.0)})
            >>> lim.for_index("1").passing.high
            1.0
            >>> lim.for_index(2)
            Traceback (most recent call last):
            ...
            mastif.kernel.errors.LimitsError: no limits for index 2 and no default
        """
        found = self.by_index.get(str(index), self.default)
        if found is None:
            raise LimitsError(f"no limits for index {index!r} and no default")
        return found


def evaluate(value: float | Quantity, limits: Limits) -> Verdict:
    """Judge a value against limits: the single source of truth for PASS/WARN/FAIL.

    This is a pure function: same inputs, same verdict, no side effects. Results call
    it to compute their own verdicts, so a report can always be recomputed and checked.

    Quantities are converted to the limits' unit before comparison. Bare numbers are
    assumed to already be in that unit.

    Args:
        value: The measured value.
        limits: The acceptance limits.

    Returns:
        ``Verdict.PASS``, ``Verdict.WARN`` or ``Verdict.FAIL``.

    Raises:
        UnitError: If a quantity is judged against unitless limits, or its unit has a
            different dimension.

    Examples:
        >>> from mastif.kernel.units import V, mV
        >>> lim = Limits.between(4.75 * V, 5.25 * V)
        >>> evaluate(5000 * mV, lim)
        <Verdict.PASS: 'pass'>
        >>> evaluate(5.0, lim)
        <Verdict.PASS: 'pass'>
    """
    if isinstance(value, Quantity):
        if limits.unit is None:
            raise UnitError(f"value has unit {value.unit!r} but limits are unitless")
        x = value.magnitude(limits.unit)
    else:
        x = float(value)
    if limits.passing.contains(x):
        return Verdict.PASS
    if limits.warning is not None and limits.warning.contains(x):
        return Verdict.WARN
    return Verdict.FAIL
