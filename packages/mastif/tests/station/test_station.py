"""Unit tests for `mastif.station`: profiles, building, roles and the resource lifecycle.

The station is where configuration meets hardware, so these tests pin down:

- broken profiles fail at build time, with the resource name, before any I/O
- resources open in profile order and close in reverse
- a failure while opening closes everything already opened
- identity expectations, including operator-supplied ones, are enforced
- unhealthy resources are refused
- safe-state continues past failures
- DUT channels are built, contract-checked and attached
- roles resolve to resources, channels and children
"""

from typing import Any

import pytest
from pydantic import BaseModel

from mastif.resources import IdentityMismatch, ResourceFault
from mastif.resources.driver import DriverConfig, channel, driver, dut
from mastif.resources.identity import Health, Identity
from mastif.resources.registry import Registry
from mastif.resources.std import MessageChannel, PowerSupply, Relay, Shell, ShellResult
from mastif.station import RoleError, Station, StationError, StationProfile

LOG: list[str] = []


@pytest.fixture(autouse=True)
def _clear_log():
    """Start every test with an empty lifecycle log."""
    LOG.clear()


class _Recorder:
    """Base for test drivers: records lifecycle calls in `LOG` as ``"<name>.<hook>"``."""

    class Config(DriverConfig):
        """Test knobs."""

        name: str
        serial: str = "S1"
        fail_open: bool = False
        healthy: bool = True
        fail_safe: bool = False

    def __init__(self, cfg: Config) -> None:
        """Keep the config."""
        self.cfg = cfg

    def open(self) -> None:
        """Record, optionally failing."""
        LOG.append(f"{self.cfg.name}.open")
        if self.cfg.fail_open:
            raise ResourceFault(f"{self.cfg.name} would not open")

    def identify(self) -> Identity:
        """Report the configured serial."""
        return Identity(serial=self.cfg.serial)

    def health(self) -> Health:
        """Report the configured health."""
        return Health(ok=self.cfg.healthy, detail="" if self.cfg.healthy else "overheated")

    def safe_state(self) -> None:
        """Record, optionally failing."""
        LOG.append(f"{self.cfg.name}.safe")
        if self.cfg.fail_safe:
            raise RuntimeError("stuck")

    def close(self) -> None:
        """Record."""
        LOG.append(f"{self.cfg.name}.close")


@driver("test.psu", provides=[PowerSupply])
class RecPsu(_Recorder):
    """A recording power supply."""

    def set_voltage(self, voltage: Any) -> None:
        """Do nothing."""

    def set_current_limit(self, current: Any) -> None:
        """Do nothing."""

    def output(self, enabled: bool) -> None:
        """Do nothing."""

    def measure_voltage(self) -> Any:
        """Do nothing."""

    def measure_current(self) -> Any:
        """Do nothing."""


@driver("test.shell", provides=[Shell])
class RecShell(_Recorder):
    """A recording shell channel."""

    def execute(self, command: str, timeout: float = 5.0) -> ShellResult:
        """Echo the command."""
        return ShellResult(command=command, output=command)


class BoardState(BaseModel):
    """DUT state for tests."""

    booted: bool = False


@dut("test.board", state=BoardState)
class RecBoard(_Recorder):
    """A recording DUT with one required and one optional channel."""

    console: Shell = channel()
    ctrl: MessageChannel = channel(optional=True)
    state: BoardState

    def open(self) -> None:
        """Use the console during open, proving channels are open first."""
        super().open()
        self.console.execute("hello")
        self.state.booted = True


@driver("test.controller")
class RecController(_Recorder):
    """A composite resource exposing children once open."""

    def children(self) -> dict[str, Any]:
        """Two axes."""
        return {"az": "azimuth-axis", "el": "elevation-axis"}


REGISTRY = Registry([RecPsu, RecShell, RecBoard, RecController])


def _station(yaml_text: str, **kwargs) -> Station:
    """Build a station from YAML using the test registry.

    Args:
        yaml_text: The profile.
        **kwargs: Passed to `Station.build`.

    Returns:
        The built (closed) station.
    """
    return Station.build(StationProfile.from_yaml(yaml_text), REGISTRY, **kwargs)


BENCH = """
station: bench-01
resources:
  psu: {driver: test.psu, config: {name: psu}, expect: {serial: S1}}
  dut:
    driver: test.board
    config: {name: dut, serial: SN-42}
    channels:
      console: {driver: test.shell, config: {name: console}}
  pos: {driver: test.controller, config: {name: pos}}
roles: {psu_main: psu, turntable: pos.az, console: dut.console}
sim:
  psu: {driver: test.psu, config: {name: simpsu}}
"""


def test_profile_rejects_role_to_unknown_resource():
    """A role pointing at nothing is a profile error, found before building."""
    with pytest.raises(StationError, match="unknown resource 'nope'"):
        StationProfile.from_yaml("station: s\nresources: {}\nroles: {r: nope}")


def test_profile_reports_missing_fields_readably():
    """Validation errors are listed one per line with their location."""
    with pytest.raises(StationError, match="resources.psu.driver: Field required"):
        StationProfile.from_yaml("station: s\nresources: {psu: {config: {}}}")


def test_profile_rejects_dotted_resource_names():
    """Dots are reserved for ``resource.child`` role targets."""
    with pytest.raises(StationError, match="invalid name"):
        StationProfile.from_yaml("station: s\nresources: {a.b: {driver: test.psu}}")


def test_profile_load_reports_missing_file(tmp_path):
    """A missing profile file is a StationError naming the path."""
    with pytest.raises(StationError, match="cannot read"):
        StationProfile.load(tmp_path / "missing.yaml")


def test_build_rejects_invalid_config_with_resource_name():
    """A config typo is reported with the resource and field, before any I/O."""
    with pytest.raises(StationError, match=r"resource 'psu': invalid config:.*nmae: Extra inputs"):
        _station("station: s\nresources: {psu: {driver: test.psu, config: {nmae: x}}}")


def test_build_rejects_unmapped_required_channel():
    """A DUT whose required channel isn't mapped can't be built."""
    with pytest.raises(StationError, match="channel 'console' is not mapped"):
        _station("station: s\nresources: {dut: {driver: test.board, config: {name: d}}}")


def test_build_rejects_unknown_channel():
    """Mapping a channel the DUT doesn't declare is a profile error."""
    yaml_text = """
station: s
resources:
  dut:
    driver: test.board
    config: {name: d}
    channels:
      console: {driver: test.shell, config: {name: c}}
      debug: {driver: test.shell, config: {name: x}}
"""
    with pytest.raises(StationError, match="no channel"):
        _station(yaml_text)


def test_build_rejects_channel_with_wrong_contract():
    """A channel driver that can't serve the declared contract is refused."""
    yaml_text = """
station: s
resources:
  dut:
    driver: test.board
    config: {name: d}
    channels:
      console: {driver: test.psu, config: {name: c}}
"""
    with pytest.raises(StationError, match="needs Shell"):
        _station(yaml_text)


def test_build_does_no_io():
    """Building validates everything but opens nothing."""
    _station(BENCH)

    assert LOG == []


def test_open_order_and_reverse_close():
    """Resources open in profile order (channels before their DUT) and close in reverse."""
    st = _station(BENCH)

    st.open()
    st.close()

    assert LOG == [
        "psu.open",
        "console.open",
        "dut.open",
        "pos.open",
        "pos.close",
        "dut.close",
        "console.close",
        "psu.close",
    ]


def test_failure_while_opening_closes_what_was_opened():
    """If the third resource fails, the first two are closed again, then the error surfaces."""
    st = _station(BENCH.replace("config: {name: pos}", "config: {name: pos, fail_open: true}"))

    with pytest.raises(ResourceFault, match="would not open"):
        st.open()

    assert LOG[-3:] == ["dut.close", "console.close", "psu.close"]
    assert st.manager.opened == []


def test_identity_mismatch_stops_open():
    """The wrong unit on the bench fails before anything else is done to it."""
    st = _station(BENCH.replace("expect: {serial: S1}", "expect: {serial: A123}"))

    with pytest.raises(IdentityMismatch, match="serial is 'S1', expected 'A123'"):
        st.open()


def test_operator_expectation_is_checked():
    """A serial scanned by the operator is checked against the connected DUT."""
    st = _station(BENCH)

    with pytest.raises(IdentityMismatch, match="dut: serial is 'SN-42', expected 'SN-99'"):
        st.open(expect={"dut": {"serial": "SN-99"}})


def test_unhealthy_resource_is_refused():
    """A resource reporting itself unhealthy can't be used."""
    st = _station(BENCH.replace("config: {name: psu}", "config: {name: psu, healthy: false}"))

    with pytest.raises(ResourceFault, match="unhealthy: overheated"):
        st.open()


def test_safe_state_continues_past_failures():
    """One stuck resource doesn't stop the others from being made safe."""
    st = _station(BENCH.replace("config: {name: dut,", "config: {name: dut, fail_safe: true,"))
    st.open()

    failures = st.safe_state()

    assert list(failures) == ["dut"]
    assert [e for e in LOG if e.endswith(".safe")] == ["pos.safe", "dut.safe", "psu.safe"]


def test_context_manager_makes_safe_then_closes():
    """Leaving a ``with`` block runs safe state, then close, even after an exception."""
    with pytest.raises(RuntimeError, match="test failed"), _station(BENCH):
        raise RuntimeError("test failed")

    assert LOG.index("psu.safe") < LOG.index("pos.close")


def test_roles_resolve_to_resources_channels_and_children():
    """Roles reach resources, DUT channels, and children reported once open."""
    st = _station(BENCH)
    st.open()

    assert isinstance(st.require("psu_main", PowerSupply), RecPsu)
    assert isinstance(st.role("console"), RecShell)
    assert st.role("turntable") == "azimuth-axis"


def test_child_role_before_open_explains_why():
    """Children only exist once open; asking earlier says so."""
    with pytest.raises(RoleError, match="only once the station is open"):
        _station(BENCH).role("turntable")


def test_require_rejects_wrong_contract():
    """Asking a supply to be a relay bank is refused with both names."""
    with pytest.raises(RoleError, match=r"role 'psu_main' \(test.psu\) does not provide Relay"):
        _station(BENCH).require("psu_main", Relay)


def test_role_problems_for_preflight():
    """Preflight lists unknown roles and contract mismatches, and skips not-yet-open children."""
    problems = _station(BENCH).role_problems(
        {"psu_main": PowerSupply, "console": Relay, "scope": Shell, "turntable": Relay}
    )

    assert problems == [
        "role 'console' (RecShell) does not provide Relay",
        "no role 'scope'; known roles: console, dut, pos, psu, psu_main, turntable",
    ]


def test_sim_mode_uses_sim_entries():
    """``sim=True`` swaps in the profile's simulator entries."""
    st = _station(BENCH, sim=True)
    st.open()

    assert "simpsu.open" in LOG and "psu.open" not in LOG


def test_identities_and_dut_state_are_recorded():
    """Identities and DUT state are available for the run manifest and snapshots."""
    st = _station(BENCH)
    st.open()

    assert st.identities()["dut"].serial == "SN-42"
    assert st.resource("dut").state_snapshot() == {"booted": True}


def test_listener_receives_lifecycle_events():
    """Every lifecycle step is reported, so the engine can turn it into run events."""
    events: list[tuple[str, str]] = []
    st = _station(BENCH, listener=lambda e: events.append((e.resource, e.phase)))

    st.open()
    st.close()

    assert events[:2] == [("psu", "opening"), ("psu", "opened")]
    assert events[-1] == ("psu", "closed")
