import pytest

from mastif.kernel import Quantity, UnitError, convert, convertible
from mastif.kernel.units import A, GHz, MHz, V, dB, dBm, mA, mV


def test_multiplying_number_by_unit_builds_quantity():
    q = 12 * V

    assert q == Quantity(value=12.0, unit="V")


def test_convert_between_prefixes():
    assert convert(1500.0, "mV", "V") == pytest.approx(1.5)


def test_to_changes_unit_but_not_value():
    q = (2.4 * GHz).to("MHz")

    assert (q.value, q.unit) == (pytest.approx(2400.0), "MHz")


def test_incompatible_units_raise():
    with pytest.raises(UnitError):
        (1 * V).to("A")


def test_unknown_unit_is_its_own_dimension():
    assert convertible("psi", "psi")
    assert not convertible("psi", "V")


def test_addition_converts_right_operand():
    assert (1 * V + 500 * mV) == 1.5 * V


def test_comparison_across_prefixes():
    assert 300 * mA < 1 * A
    assert 2400 * MHz == 2.4 * GHz


def test_equal_quantities_hash_equal():
    assert hash(1 * V) == hash(1000 * mV)


def test_dbm_plus_db_is_dbm():
    assert (10 * dBm + 3 * dB) == 13 * dBm


def test_dbm_minus_dbm_is_db():
    q = 10 * dBm - 4 * dBm

    assert (q.value, q.unit) == (6.0, "dB")


def test_dbm_plus_dbm_is_rejected():
    with pytest.raises(UnitError):
        10 * dBm + 3 * dBm


def test_log_unit_never_converts_to_linear():
    with pytest.raises(UnitError):
        (10 * dBm).to("mW")


def test_log_quantity_cannot_be_scaled():
    with pytest.raises(UnitError):
        (3 * dB) * 2


def test_nan_is_rejected():
    with pytest.raises(ValueError):
        Quantity(value=float("nan"), unit="V")


def test_round_trips_through_json():
    q = 3.3 * V

    assert Quantity.model_validate_json(q.model_dump_json()) == q
