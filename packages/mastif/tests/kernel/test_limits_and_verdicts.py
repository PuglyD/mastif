"""Unit tests for `mastif.kernel.limits` and `mastif.kernel.verdict`.

Limits decide pass and fail, and `aggregate` decides what a whole run reports. These
tests pin down the precedence of verdicts, how ranges are built and validated, the
PASS/WARN/FAIL zones, unit handling during evaluation, and per-index limits.
"""

import pytest

from mastif.kernel import (
    IndexedLimits,
    Limits,
    LimitsError,
    Range,
    UnitError,
    Verdict,
    aggregate,
    evaluate,
)
from mastif.kernel.units import V, dB, mV


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ([], Verdict.SKIPPED),
        ([Verdict.SKIPPED, Verdict.SKIPPED], Verdict.SKIPPED),
        ([Verdict.PASS, Verdict.SKIPPED], Verdict.PASS),
        ([Verdict.PASS, Verdict.WARN], Verdict.WARN),
        ([Verdict.WARN, Verdict.FAIL], Verdict.FAIL),
        ([Verdict.FAIL, Verdict.ERROR], Verdict.ERROR),
        ([Verdict.ERROR, Verdict.ABORTED], Verdict.ABORTED),
    ],
)
def test_aggregate_precedence(verdicts, expected):
    """The worst child verdict wins, and skipped children count only if all were skipped.

    Args:
        verdicts: Child verdicts to combine.
        expected: The parent verdict they must produce.
    """
    assert aggregate(verdicts) == expected


def test_range_accepts_quantities_and_unifies_unit():
    """Bounds given in different prefixes end up in one unit, the first bound's unit."""
    r = Range(low=4500 * mV, high=5.5 * V)

    assert (r.low, r.high, r.unit) == (4500.0, pytest.approx(5500.0), "mV")


def test_range_needs_a_bound():
    """A range with no bounds would accept anything; that is a spec mistake, so it fails."""
    with pytest.raises(LimitsError):
        Range()


def test_range_rejects_inverted_bounds():
    """A range with low above high would accept nothing, so it fails at construction."""
    with pytest.raises(LimitsError):
        Range(low=2.0, high=1.0)


def test_exclusive_range_excludes_bounds():
    """With ``inclusive=False``, a value exactly on a bound counts as outside."""
    assert not Range(low=0.0, high=1.0, inclusive=False).contains(1.0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(5.0 * V, Verdict.PASS), (5.4 * V, Verdict.WARN), (6.0 * V, Verdict.FAIL)],
)
def test_evaluate_with_warning_range(value, expected):
    """Values land in the passing, warning or failing zone of two-sided limits.

    Args:
        value: The measured value.
        expected: The verdict that zone must produce.
    """
    limits = Limits.between(4.75 * V, 5.25 * V, warn_low=4.5 * V, warn_high=5.5 * V)

    assert evaluate(value, limits) == expected


def test_evaluate_converts_value_unit():
    """A value in mV is judged correctly against limits written in V."""
    assert evaluate(5000 * mV, Limits.between(4.75 * V, 5.25 * V)) == Verdict.PASS


def test_bare_number_is_taken_in_limits_unit():
    """A bare number is assumed to be in the limits' unit, for raw driver readings."""
    assert evaluate(20.0, Limits.between(18 * dB, 22 * dB)) == Verdict.PASS


def test_quantity_against_unitless_limits_raises():
    """Judging volts against unitless limits is ambiguous, so it raises instead of guessing."""
    with pytest.raises(UnitError):
        evaluate(1 * V, Limits.at_most(2.0))


def test_warning_range_must_contain_passing_range():
    """A warning range narrower than the passing range is a spec mistake and is refused."""
    with pytest.raises(LimitsError):
        Limits.between(0.0, 10.0, warn_low=1.0)


def test_indexed_limits_fall_back_to_default():
    """An index without its own entry uses the default limits."""
    default = Limits.at_most(1.0)
    limits = IndexedLimits(by_index={3: Limits.at_most(2.0)}, default=default)

    assert limits.for_index(7) is default


def test_indexed_limits_without_default_reject_unknown_index():
    """Without a default, an unlisted index is an error, which catches incomplete specs."""
    with pytest.raises(LimitsError):
        IndexedLimits(by_index={1: Limits.at_most(1.0)}).for_index(2)


def test_one_sided_warning_keeps_other_side_failing():
    """Regression: giving only ``warn_high`` must not turn low values into WARN.

    The missing warning bound defaults to the passing bound, so values far below the
    passing range still FAIL.
    """
    limits = Limits.between(4.75 * V, 5.25 * V, warn_high=5.5 * V)

    assert evaluate(4.0 * V, limits) == Verdict.FAIL
    assert evaluate(5.4 * V, limits) == Verdict.WARN
