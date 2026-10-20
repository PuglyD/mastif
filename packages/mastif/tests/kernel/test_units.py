"""Unit tests for `mastif.kernel.units`.

Quantities carry units from drivers through to reports. These tests pin down the
behaviour test authors rely on: building quantities with ``number * unit``, converting
between prefixes, refusing to mix dimensions, the RF rules for dB arithmetic, and
surviving a JSON round trip unchanged.
"""

import pytest

from mastif.kernel import Quantity, UnitError, convert, convertible
from mastif.kernel.units import A, GHz, MHz, V, dB, dBm, mA, mV


def test_multiplying_number_by_unit_builds_quantity():
    """``12 * V`` is the main way authors write values, so it must build a plain Quantity."""
    q = 12 * V

    assert q == Quantity(value=12.0, unit="V")


def test_convert_between_prefixes():
    """The low-level `convert` scales correctly between SI prefixes of one dimension."""
    assert convert(1500.0, "mV", "V") == pytest.approx(1.5)


def test_to_changes_unit_but_not_value():
    """`Quantity.to` re-expresses a value; drivers rely on it to format commands."""
    q = (2.4 * GHz).to("MHz")

    assert (q.value, q.unit) == (pytest.approx(2400.0), "MHz")


def test_incompatible_units_raise():
    """Converting volts to amps is a programming error and must fail loudly."""
    with pytest.raises(UnitError):
        (1 * V).to("A")


def test_unknown_unit_is_its_own_dimension():
    """Orgs can use any unit symbol without registration; it converts only to itself."""
    assert convertible("psi", "psi")
    assert not convertible("psi", "V")


def test_addition_converts_right_operand():
    """Adding mixed prefixes converts the right operand into the left operand's unit."""
    assert (1 * V + 500 * mV) == 1.5 * V


def test_comparison_across_prefixes():
    """Comparisons work across prefixes; this is what makes limit checks unit-safe."""
    assert 300 * mA < 1 * A
    assert 2400 * MHz == 2.4 * GHz


def test_equal_quantities_hash_equal():
    """Equal quantities hash equally, so they behave correctly as dict and set keys."""
    assert hash(1 * V) == hash(1000 * mV)


def test_dbm_plus_db_is_dbm():
    """A level plus a gain is a level: the most common RF calculation."""
    assert (10 * dBm + 3 * dB) == 13 * dBm


def test_dbm_minus_dbm_is_db():
    """The difference between two levels is a relative value (gain or loss) in dB."""
    q = 10 * dBm - 4 * dBm

    assert (q.value, q.unit) == (6.0, "dB")


def test_dbm_plus_dbm_is_rejected():
    """Adding two absolute power levels has no meaning in dB arithmetic, so it is refused."""
    with pytest.raises(UnitError):
        10 * dBm + 3 * dBm


def test_log_unit_never_converts_to_linear():
    """Converting dBm to mW is a non-linear transform, not a unit conversion, so it is refused."""
    with pytest.raises(UnitError):
        (10 * dBm).to("mW")


def test_log_quantity_cannot_be_scaled():
    """Multiplying a dB value by a number is a common mistake, so it is refused."""
    with pytest.raises(UnitError):
        (3 * dB) * 2


def test_nan_is_rejected():
    """NaN would silently fall outside every limit, so it is rejected at construction."""
    with pytest.raises(ValueError):
        Quantity(value=float("nan"), unit="V")


def test_round_trips_through_json():
    """Quantities cross process and network boundaries as JSON, so they must survive it."""
    q = 3.3 * V

    assert Quantity.model_validate_json(q.model_dump_json()) == q
