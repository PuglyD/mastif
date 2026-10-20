"""Unit tests for `mastif.kernel.results` and `mastif.kernel.ids`.

Results are the evidence a run leaves behind, so these tests focus on the guarantee
that a verdict always matches its data. That includes verdicts recomputed after a JSON
round trip and unit mistakes caught at construction. The id tests cover the keys that
name runs and positions in a plan.
"""

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter

from mastif.kernel import (
    Check,
    IndexedLimits,
    Limits,
    LimitsError,
    Measurement,
    Position,
    Result,
    Table,
    UnitError,
    Verdict,
    new_run_id,
)
from mastif.kernel.units import V, dBm, mA


def test_measurement_verdict_is_computed_from_limits():
    """A measurement judges itself against its limits and keeps the quantity's unit."""
    m = Measurement(name="current", value=300 * mA, limits=Limits.at_most(250 * mA))

    assert (m.unit, m.verdict) == ("mA", Verdict.FAIL)


def test_measurement_without_limits_passes():
    """A value recorded for information only (no limits) is PASS."""
    assert Measurement(name="v", value=1.0).verdict == Verdict.PASS


def test_supplied_verdict_is_ignored_and_recomputed():
    """A stored verdict is never trusted: an edited JSON file can't turn a FAIL into a PASS."""
    m = Measurement.model_validate(
        {"name": "v", "value": 9.0, "unit": "V", "limits": Limits.at_most(5 * V), "verdict": "pass"}
    )

    assert m.verdict == Verdict.FAIL


def test_measurement_with_incompatible_unit_fails_at_construction():
    """Volts against milliamp limits fails where it is written, not later in a report."""
    with pytest.raises(UnitError):
        Measurement(name="v", value=1 * V, limits=Limits.at_most(250 * mA))


def test_check_verdict():
    """A check that didn't hold is FAIL."""
    assert Check(name="link up", passed=False).verdict == Verdict.FAIL


def _power_table(rows):
    """Build the output-power table used by several tests.

    Channels 7 and 8 accept 8-10 dBm; all other channels accept 9-11 dBm.

    Args:
        rows: ``(channel, power_dbm)`` rows.

    Returns:
        A `Table` indexed by channel, with `IndexedLimits` on the power column.
    """
    normal = Limits.between(9 * dBm, 11 * dBm)
    long_cable = Limits.between(8 * dBm, 10 * dBm)
    return Table(
        name="output_power",
        columns=("channel", "power"),
        index="channel",
        units={"power": "dBm"},
        limits={"power": IndexedLimits(by_index={7: long_cable, 8: long_cable}, default=normal)},
        rows=rows,
    )


def test_table_judges_each_row_against_its_index():
    """Each row uses the limits for its own channel, and the worst row decides the table."""
    t = _power_table(((1, 10.2), (7, 8.4), (8, 11.0)))

    assert t.row_verdicts == (Verdict.PASS, Verdict.PASS, Verdict.FAIL)
    assert t.verdict == Verdict.FAIL


def test_table_missing_value_fails_cell():
    """A judged cell with no value is FAIL: a missing reading can't pass."""
    assert _power_table(((1, None),)).verdict == Verdict.FAIL


def test_table_rejects_ragged_rows():
    """Rows must match the column count, or cells would be judged against the wrong limits."""
    with pytest.raises(LimitsError):
        Table(name="t", columns=("a", "b"), rows=((1,),))


def test_table_rejects_limits_on_unknown_column():
    """Limits on a column that doesn't exist are a typo, not something to ignore."""
    with pytest.raises(LimitsError):
        Table(name="t", columns=("a",), rows=(), limits={"b": Limits.at_most(1.0)})


def test_results_round_trip_through_discriminated_union():
    """All result kinds survive the JSON trip that events take, keeping verdicts and limits."""
    adapter = TypeAdapter(list[Result])
    original = [
        Measurement(name="v", value=5 * V, limits=Limits.at_most(6 * V)),
        Check(name="c", passed=True),
        _power_table(((1, 10.0),)),
    ]

    restored = adapter.validate_json(adapter.dump_json(original))

    assert restored == original


def test_position_key_and_lookup():
    """A position exposes its text key, individual loop values and loop order."""
    p = Position.of(profile="std", channel=2)

    assert (p.key, p.get("channel"), p.names) == (
        "profile=std/channel=2",
        2,
        ("profile", "channel"),
    )


def test_positions_are_hashable_and_ordered():
    """Loop order is part of a position's identity, and equal positions deduplicate in sets."""
    assert Position.of(a=1, b=2) != Position.of(b=2, a=1)
    assert len({Position.of(a=1), Position.of(a=1)}) == 1


def test_run_ids_sort_by_time():
    """Run ids sort chronologically, so run folders list in the order they were started."""
    early = new_run_id(datetime(2026, 1, 1, tzinfo=UTC))
    late = new_run_id(datetime(2026, 6, 1, tzinfo=UTC))

    assert early < late and early.startswith("20260101T000000Z-")
