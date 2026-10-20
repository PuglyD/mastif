"""Unit tests for `mastif.resources.contracts`, `mastif.resources.std` and `identity`.

Contracts are how tests stay independent of hardware, so these tests pin down the
structural check that `@driver` relies on: missing members, parameter compatibility,
properties, and contract inheritance. They also cover the identity comparison that
stops a station from driving the wrong device.
"""

from typing import Protocol

import pytest

from mastif.resources import (
    ContractMismatch,
    ContractProblem,
    Health,
    Identity,
    ProblemKind,
    contract,
    contract_info,
    contract_problems,
    satisfies,
)
from mastif.resources.contracts import check_provides, contract_members
from mastif.resources.std import PowerSupply, Relay, ShellResult


class Probe(Protocol):
    """A minimal contract used across these tests."""

    def read(self, channel: int) -> float:
        """Read one channel."""
        ...

    @property
    def channels(self) -> int:
        """Number of channels."""
        ...


class GoodProbe:
    """Satisfies `Probe`, with an extra optional parameter that must be allowed."""

    def read(self, channel: int, averages: int = 1) -> float:
        """Return a constant."""
        return 1.0

    @property
    def channels(self) -> int:
        """Two channels."""
        return 2


def test_class_with_every_member_satisfies():
    """Extra optional parameters on the implementation don't break compatibility."""
    assert satisfies(GoodProbe, Probe)


def test_missing_member_is_reported_as_missing():
    """A class lacking a contract method is reported with ProblemKind.MISSING."""

    class NoRead:
        @property
        def channels(self) -> int:
            return 1

    assert contract_problems(NoRead, Probe) == [ContractProblem("read", ProblemKind.MISSING)]


def test_method_requiring_extra_argument_is_incompatible():
    """An implementation can't require more arguments than the contract passes."""

    class Needy(GoodProbe):
        def read(self, channel: int, gain: float) -> float:  # ty: ignore[invalid-method-override]
            return 0.0

    assert contract_problems(Needy, Probe) == [
        ContractProblem("read", ProblemKind.INCOMPATIBLE_PARAMETERS)
    ]


def test_method_accepting_fewer_arguments_is_incompatible():
    """An implementation that drops a contract parameter would fail when called."""

    class Deaf(GoodProbe):
        def read(self) -> float:  # ty: ignore[invalid-method-override]
            return 0.0

    assert ContractProblem("read", ProblemKind.INCOMPATIBLE_PARAMETERS) in contract_problems(
        Deaf, Probe
    )


def test_property_member_must_be_property():
    """A contract property implemented as a method is flagged, because callers won't call it."""

    class MethodChannels(GoodProbe):
        def channels(self) -> int:  # ty: ignore[invalid-property-type-override]
            return 2

    assert contract_problems(MethodChannels, Probe) == [
        ContractProblem("channels", ProblemKind.NOT_A_PROPERTY)
    ]


def test_varargs_implementation_is_compatible():
    """An implementation that accepts ``*args, **kwargs`` can take any contract call."""

    class Generic(GoodProbe):
        def read(self, *args, **kwargs) -> float:
            return 0.0

    assert satisfies(Generic, Probe)


def test_inherited_contract_members_are_collected():
    """A contract extending another requires the members of both."""

    class MultiProbe(Probe, Protocol):
        def calibrate(self) -> None:
            """Calibrate."""
            ...

    assert set(contract_members(MultiProbe)) == {"read", "channels", "calibrate"}


def test_check_provides_lists_every_problem():
    """`check_provides` names the driver, the contract and each problem in one error."""
    with pytest.raises(ContractMismatch, match=r"acme.x does not provide Probe: read: missing"):
        check_provides("acme.x", object, (Probe,))


def test_contract_decorator_is_optional_and_keeps_the_class():
    """`@contract` returns the same class; undecorated contracts get a default name."""

    @contract(safe_state="stop")
    class Mover(Protocol):
        def stop(self) -> None:
            """Stop."""
            ...

    assert contract_info(Mover).safe_state == "stop"
    assert contract_info(Probe).name == "Probe"


def test_std_contracts_declare_safe_states():
    """The built-in supply and relay contracts know how to make themselves safe."""
    assert callable(contract_info(PowerSupply).safe_state)
    assert contract_info(Relay).safe_state == "open_all"


def test_identity_mismatch_reports_expected_and_actual():
    """Every differing field is returned with expected and actual values."""
    idn = Identity(serial="B999", model="PSU-X")

    assert idn.mismatches({"serial": "A123", "model": "PSU-X"}) == {"serial": ("A123", "B999")}


def test_identity_extra_fields_can_be_expected():
    """Non-standard facts in ``extra`` can be checked like the standard ones."""
    idn = Identity(extra={"part_number": "900-0042"})

    assert idn.mismatches({"part_number": "900-0042"}) == {}


def test_unreported_field_counts_as_mismatch():
    """An unknown value isn't proof of the right device, so it is a mismatch."""
    assert Identity().mismatches({"serial": "A123"}) == {"serial": ("A123", None)}


def test_expected_values_are_compared_as_text():
    """YAML may parse a serial like ``1234`` as a number; it still matches the text."""
    assert Identity(serial="1234").mismatches({"serial": 1234}) == {}


def test_health_good_shortcut():
    """`Health.good` builds a healthy result with readings."""
    assert Health.good(temp=30.0) == Health(ok=True, readings={"temp": 30.0})


def test_shell_result_ok_depends_on_exit_code():
    """Unknown exit codes count as ok; non-zero exit codes don't."""
    assert ShellResult(command="x", output="").ok
    assert not ShellResult(command="x", output="", exit_code=2).ok
