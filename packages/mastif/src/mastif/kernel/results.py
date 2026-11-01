"""What a test records: measurements, checks and tables.

Why this exists:
    A test run is only as trustworthy as the evidence it leaves behind. Each result
    records what was observed, against which limits, and the verdict. The verdict is
    **always computed** from the data and limits and can never be supplied by the
    caller, so a report can't contain a PASS that contradicts its own numbers. When a
    result is loaded from JSON, any ``verdict`` key is dropped and recomputed.

Where it fits:
    Test tasks create results through the task context (``ctx.measure(...)``,
    ``ctx.check(...)``, ``ctx.table(...)``). The engine wraps each one in a
    ``ResultRecorded`` event, adding the run, position and slot. Reports and UIs consume
    those events. Results are plain immutable Pydantic models, so they serialise as-is
    across process and network boundaries.

The three kinds:
    - `Measurement`: one numeric value, optionally against `Limits`.
    - `Check`: one boolean condition ("link is up", "firmware version matches").
    - `Table`: many values from an inner loop (per channel, per point), each judged
      per cell, optionally with `IndexedLimits`.

`Result` is the union of all three, discriminated by the ``kind`` field.
"""

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from mastif.kernel.errors import LimitsError
from mastif.kernel.limits import IndexedLimits, Limits, evaluate
from mastif.kernel.units import Quantity
from mastif.kernel.verdict import Verdict, aggregate

type Cell = float | int | str | bool | None
"""Scalar table-cell value; `None` represents an empty cell."""


def _drop_verdicts(data: Any, *keys: str) -> Any:
    """Remove computed keys from raw input so they are recomputed, never trusted.

    Serialised results include their computed verdicts, which is convenient for anyone
    reading the JSON. When that JSON is loaded back, the stored verdicts are discarded
    and recomputed, so editing a file can't change a verdict.

    Args:
        data: Raw input.
        *keys: Keys to drop.

    Returns:
        The input without those keys (non-dict input is returned unchanged).

    Examples:
        >>> _drop_verdicts({"name": "v", "verdict": "pass"}, "verdict")
        {'name': 'v'}
    """
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k not in keys}
    return data


class Measurement(BaseModel):
    """One named numeric value, optionally judged against limits.

    This is the most common result: a voltage, a current, a gain. Without limits a
    measurement is recorded for information only and its verdict is PASS.

    Attributes:
        kind: Always ``"measurement"``; tells the result types apart in JSON.
        name: Result name, unique within its step (e.g. ``"standby_current"``).
        value: The magnitude.
        unit: The unit, or ``None`` for unitless values.
        limits: Acceptance limits, or ``None`` to record without judging.

    Examples:
        >>> from mastif.kernel.units import mA
        >>> m = Measurement("standby_current", 180 * mA, Limits.at_most(250 * mA))
        >>> m.value, m.unit, m.verdict
        (180.0, 'mA', <Verdict.PASS: 'pass'>)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["measurement"] = "measurement"
    name: str
    value: float
    unit: str | None = None
    limits: Limits | None = None

    def __init__(
        self,
        name: str,
        value: float | Quantity,
        limits: Limits | None = None,
        *,
        unit: str | None = None,
        **data: Any,
    ) -> None:
        """Record a value, given as a number or a quantity.

        Passing a quantity is preferred because it keeps the unit attached. A bare
        number is accepted for unitless values, or with an explicit ``unit``.

        Args:
            name: Result name.
            value: The value; a quantity's unit is used unless ``unit`` is given.
            limits: Acceptance limits.
            unit: Unit for a bare number.
            **data: Other fields, as found in serialised input.

        Raises:
            UnitError: If the value's unit can't be compared with the limits. This is
                raised at construction, not when a report is generated.

        Examples:
            >>> Measurement("ratio", 0.98).verdict
            <Verdict.PASS: 'pass'>
            >>> from mastif.kernel.units import dB
            >>> Measurement("gain", 20.5, Limits.at_least(18 * dB), unit="dB").verdict
            <Verdict.PASS: 'pass'>
        """
        super().__init__(name=name, value=value, unit=unit, limits=limits, **data)

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: Any) -> Any:
        """Split a quantity value into ``value`` and ``unit``, and drop any stored verdict.

        Args:
            data: Raw input.

        Returns:
            Normalised input.

        Examples:
            >>> from mastif.kernel.units import V
            >>> Measurement._normalise({"name": "v", "value": 5 * V, "verdict": "fail"})
            {'name': 'v', 'value': 5.0, 'unit': 'V'}
        """
        data = _drop_verdicts(data, "verdict")
        if isinstance(data, dict) and isinstance(data.get("value"), Quantity):
            q: Quantity = data["value"]
            data = {**data, "value": q.value, "unit": data.get("unit") or q.unit}
        return data

    @model_validator(mode="after")
    def _judgeable(self) -> Self:
        """Evaluate once at construction, so unit mismatches fail early.

        Without this, a measurement in volts against limits in amps would only fail
        later, in a report or UI, far from the code that made the mistake.

        Returns:
            The measurement.

        Raises:
            UnitError: If the value and limits can't be compared.

        Examples:
            >>> from mastif.kernel.units import V, mA
            >>> Measurement("v", 1 * V, Limits.at_most(250 * mA))
            Traceback (most recent call last):
            ...
            mastif.kernel.errors.UnitError: cannot convert 'V' to 'mA'
        """
        _ = self.verdict
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verdict(self) -> Verdict:
        """PASS, WARN or FAIL from the limits; PASS when there are no limits.

        Examples:
            >>> from mastif.kernel.units import V
            >>> Measurement("v", 6 * V, Limits.at_most(5 * V)).verdict
            <Verdict.FAIL: 'fail'>
        """
        if self.limits is None:
            return Verdict.PASS
        value: float | Quantity = self.value if self.unit is None else self.quantity
        return evaluate(value, self.limits)

    @property
    def quantity(self) -> Quantity:
        """The value as a `Quantity`, for further arithmetic (dimensionless if unitless).

        Examples:
            >>> from mastif.kernel.units import mV
            >>> Measurement("v", 500 * mV).quantity.to("V")
            Quantity(value=0.5, unit='V')
        """
        return Quantity(value=self.value, unit=self.unit or "")


class Check(BaseModel):
    """A named boolean condition: something that either holds or doesn't.

    Use a check for anything without a numeric value: an identity match, a link being
    up, a self-test flag. Put the evidence in ``detail``. For example "expected fw 2.1,
    found 2.0" makes a failure actionable without opening the logs.

    Attributes:
        kind: Always ``"check"``.
        name: Result name.
        passed: Whether the condition held.
        detail: Human-readable explanation, most useful on failure.

    Examples:
        >>> c = Check(name="firmware_version", passed=False, detail="expected 2.1, got 2.0")
        >>> c.verdict
        <Verdict.FAIL: 'fail'>
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["check"] = "check"
    name: str
    passed: bool
    detail: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: Any) -> Any:
        """Drop any stored verdict so it is recomputed from ``passed``.

        Args:
            data: Raw input.

        Returns:
            Normalised input.

        Examples:
            >>> Check.model_validate({"name": "c", "passed": False, "verdict": "pass"}).verdict
            <Verdict.FAIL: 'fail'>
        """
        return _drop_verdicts(data, "verdict")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verdict(self) -> Verdict:
        """PASS if the condition held, otherwise FAIL.

        Examples:
            >>> Check(name="link_up", passed=True).verdict
            <Verdict.PASS: 'pass'>
        """
        return Verdict.PASS if self.passed else Verdict.FAIL


class Table(BaseModel):
    """A grid of values from an inner loop, judged cell by cell.

    When a task sweeps over channels, ports or frequency points, record one table
    rather than dozens of separate measurements. The data stays together for reports
    and plots, and every cell still gets its own verdict.

    How judging works:
        - Only columns listed in ``limits`` are judged; others (the index, notes) are
          carried along.
        - A judged cell holding a missing or non-numeric value is FAIL.
        - A column with `IndexedLimits` looks up its limits using the row's ``index``
          column value.
        - Row verdict = worst cell in the row; table verdict = worst row.

    Attributes:
        kind: Always ``"table"``.
        name: Result name.
        columns: Column names, in order.
        rows: Row values, aligned with ``columns``.
        index: Column whose value selects per-row limits from `IndexedLimits`.
        units: Unit per column (bare cell numbers are in this unit).
        limits: Limits per judged column.

    Examples:
        >>> from mastif.kernel.units import dBm
        >>> t = Table(
        ...     name="output_power",
        ...     columns=("channel", "power"),
        ...     units={"power": "dBm"},
        ...     limits={"power": Limits.between(9 * dBm, 11 * dBm)},
        ...     rows=((1, 10.2), (2, 8.1)),
        ... )
        >>> t.row_verdicts, t.verdict
        ((<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>), <Verdict.FAIL: 'fail'>)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["table"] = "table"
    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Cell, ...], ...]
    index: str | None = None
    units: dict[str, str] = Field(default_factory=dict)
    limits: dict[str, Limits | IndexedLimits] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: Any) -> Any:
        """Drop the stored computed fields so they are recomputed from the data.

        Args:
            data: Raw input.

        Returns:
            Normalised input.

        Examples:
            >>> Table._normalise({"name": "t", "verdict": "pass", "row_verdicts": []})
            {'name': 't'}
        """
        return _drop_verdicts(data, "verdict", "cell_verdicts", "row_verdicts")

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        """Check the table's shape and that every judged cell can be evaluated.

        Errors are raised at construction, inside the task that built the table, where
        they are easiest to fix.

        Returns:
            The table.

        Raises:
            LimitsError: If rows are ragged, referenced columns don't exist, or
                `IndexedLimits` are used without an index column.
            UnitError: If a column's unit can't be compared with its limits.

        Examples:
            >>> Table(name="t", columns=("a", "b"), rows=((1,),))
            Traceback (most recent call last):
            ...
            mastif.kernel.errors.LimitsError: row 0 has 1 cells, expected 2
        """
        width = len(self.columns)
        for i, row in enumerate(self.rows):
            if len(row) != width:
                raise LimitsError(f"row {i} has {len(row)} cells, expected {width}")
        referenced = set(self.limits) | set(self.units)
        if self.index is not None:
            referenced.add(self.index)
        unknown = referenced - set(self.columns)
        if unknown:
            raise LimitsError(f"unknown columns: {sorted(unknown)}")
        needs_index = any(isinstance(lim, IndexedLimits) for lim in self.limits.values())
        if needs_index and self.index is None:
            raise LimitsError("IndexedLimits require an index column")
        _ = self.cell_verdicts
        return self

    def _judge(self, row: tuple[Cell, ...], column: str) -> Verdict:
        """Judge one cell against its column's limits.

        Args:
            row: The row the cell is in.
            column: The judged column.

        Returns:
            The cell verdict; a missing or non-numeric value is FAIL.

        Raises:
            LimitsError: If the column has `IndexedLimits` and the table has no index.

        Examples:
            >>> t = Table(name="t", columns=("x",), rows=(), limits={"x": Limits.at_most(1.0)})
            >>> t._judge((0.5,), "x"), t._judge((None,), "x")
            (<Verdict.PASS: 'pass'>, <Verdict.FAIL: 'fail'>)
        """
        lim = self.limits[column]
        if isinstance(lim, IndexedLimits):
            if self.index is None:
                raise LimitsError("IndexedLimits require an index column")
            lim = lim.for_index(row[self.columns.index(self.index)])
        cell = row[self.columns.index(column)]
        if not isinstance(cell, int | float) or isinstance(cell, bool):
            return Verdict.FAIL
        unit = self.units.get(column)
        value: float | Quantity = cell if unit is None else Quantity(value=cell, unit=unit)
        return evaluate(value, lim)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cell_verdicts(self) -> tuple[dict[str, Verdict], ...]:
        """For each row, the verdict of every judged column, so a UI can colour cells.

        Examples:
            >>> lim = {"x": Limits.at_most(1.0)}
            >>> Table(name="t", columns=("x",), rows=((2.0,),), limits=lim).cell_verdicts
            ({'x': <Verdict.FAIL: 'fail'>},)
        """
        return tuple({col: self._judge(row, col) for col in self.limits} for row in self.rows)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def row_verdicts(self) -> tuple[Verdict, ...]:
        """Verdict per row: the worst judged cell, or PASS when no column is judged.

        Examples:
            >>> Table(name="t", columns=("note",), rows=(("ok",),)).row_verdicts
            (<Verdict.PASS: 'pass'>,)
        """
        return tuple(
            aggregate(cells.values()) if cells else Verdict.PASS for cells in self.cell_verdicts
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def verdict(self) -> Verdict:
        """Verdict for the whole table: the worst row, or PASS for an empty table.

        Examples:
            >>> Table(name="t", columns=("x",), rows=()).verdict
            <Verdict.PASS: 'pass'>
        """
        return aggregate(self.row_verdicts) if self.rows else Verdict.PASS

    def column(self, name: str) -> list[Cell]:
        """Return all values of one column, top to bottom, for plotting or post-processing.

        Args:
            name: Column name.

        Returns:
            The column's values.

        Raises:
            ValueError: If the column doesn't exist.

        Examples:
            >>> Table(name="t", columns=("ch", "p"), rows=((1, 9.5), (2, 9.9))).column("p")
            [9.5, 9.9]
        """
        i = self.columns.index(name)
        return [row[i] for row in self.rows]


type Result = Annotated[Measurement | Check | Table, Field(discriminator="kind")]
"""Result union discriminated by `kind` when validating measurements, checks, or tables."""
