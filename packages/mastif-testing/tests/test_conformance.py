"""Unit tests for `mastif_testing.conformance`.

These helpers are what org SDKs use to vet their drivers, so they must pass good
drivers, and must name the failing step and reason for bad ones.
"""

import pytest

from mastif.resources._examples import ExamplePsu
from mastif.resources.driver import driver
from mastif.resources.identity import Health, Identity
from mastif.resources.std import PowerSupply
from mastif_testing import assert_satisfies, check_lifecycle


@driver("acme.full-hooks")
class FullHooks:
    """A driver with every lifecycle hook, recording calls."""

    def __init__(self) -> None:
        """Start with no calls."""
        self.calls: list[str] = []

    def open(self) -> None:
        """Record open."""
        self.calls.append("open")

    def identify(self) -> Identity:
        """Return a fixed identity."""
        return Identity(serial="S1")

    def health(self) -> Health:
        """Report healthy."""
        return Health.good()

    def safe_state(self) -> None:
        """Record safe state."""
        self.calls.append("safe")

    def close(self) -> None:
        """Record close."""
        self.calls.append("close")


def test_full_lifecycle_runs_every_step_in_order():
    """All hooks run in station order, and the report carries identity and health."""
    report = check_lifecycle(FullHooks, {})

    assert report.steps == ["build", "open", "identify", "health", "safe_state", "close"]
    assert report.identity == Identity(serial="S1")
    assert report.instance.calls == ["open", "safe", "close"]


def test_failing_step_is_named():
    """A hook that raises is reported with the step name and the original error."""

    @driver("acme.bad-open")
    class BadOpen:
        def open(self) -> None:
            raise RuntimeError("no power")

    with pytest.raises(AssertionError, match="step 'open' failed.*no power"):
        check_lifecycle(BadOpen, {})


def test_unhealthy_driver_fails():
    """A driver reporting itself unhealthy at rest fails conformance."""

    @driver("acme.sick")
    class Sick:
        def health(self) -> Health:
            return Health(ok=False, detail="fault")

    with pytest.raises(AssertionError, match="health"):
        check_lifecycle(Sick, {})


def test_identify_must_return_identity():
    """``identify()`` returning anything else (e.g. a raw string) fails conformance."""

    @driver("acme.raw-idn")
    class RawIdn:
        def identify(self):
            return "ACME,X,1,1"

    with pytest.raises(AssertionError, match="not an Identity"):
        check_lifecycle(RawIdn, {})


def test_missing_io_fake_is_reported():
    """Forgetting to pass a fake for an I/O parameter is caught before building."""
    with pytest.raises(AssertionError, match="provide fakes"):
        check_lifecycle(ExamplePsu, {"transport": {"kind": "tcp", "host": "h", "port": 1}})


def test_assert_satisfies_lists_problems():
    """A class missing contract methods fails with one line per problem."""

    class Half:
        def output(self, enabled: bool) -> None: ...

    with pytest.raises(AssertionError, match="set_voltage: missing"):
        assert_satisfies(Half, PowerSupply)
