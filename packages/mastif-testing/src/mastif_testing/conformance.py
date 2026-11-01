"""Conformance checks that org SDKs run against their own drivers in plain pytest.

Why this exists:
    Every driver should behave the same way towards the station: build from its
    config, open, identify, report health, reach a safe state and close, all without
    errors and without hardware. Writing those checks per driver is repetitive, and
    easy to get subtly wrong. These helpers run the standard sequence against a driver
    with fake I/O injected, and report exactly which step failed.

Where it fits:
    In an org SDK's test suite::

        from mastif_testing import FakeLineIO, assert_satisfies, check_lifecycle
        from mastif.resources.transports import Scpi

        def test_psu_x_conforms():
            io = Scpi(FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4"}))
            report = check_lifecycle(PsuX, {"transport": {...}}, io=io)
            assert report.identity.serial == "A123"

        def test_psu_x_is_a_power_supply():
            assert_satisfies(PsuX, PowerSupply)
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from mastif.resources.contracts import contract_problems
from mastif.resources.driver import build_resource, call_hook, has_hook, make_safe, spec_of
from mastif.resources.identity import Health, Identity


def assert_satisfies(cls: type, contract: type) -> None:
    """Assert that a class satisfies a contract, listing every problem if not.

    Args:
        cls: The class to check (usually a driver).
        contract: The contract Protocol.

    Raises:
        AssertionError: With one line per problem.

    Examples:
        >>> from mastif.resources._examples import ExamplePsu
        >>> from mastif.resources.std import PowerSupply, Shell
        >>> assert_satisfies(ExamplePsu, PowerSupply)
        >>> assert_satisfies(ExamplePsu, Shell)
        Traceback (most recent call last):
        ...
        AssertionError: ExamplePsu does not satisfy Shell:
          execute: missing
    """
    problems = contract_problems(cls, contract)
    if problems:
        lines = "\n".join(f"  {p}" for p in problems)
        raise AssertionError(f"{cls.__name__} does not satisfy {contract.__name__}:\n{lines}")


@dataclass
class LifecycleReport:
    """What `check_lifecycle` observed, for further assertions.

    Attributes:
        instance: The driver object that was exercised.
        identity: What ``identify()`` returned, if the driver has it.
        health: What ``health()`` returned, if the driver has it.
        safe_state_ran: Whether any safe-state action ran.
        steps: The lifecycle steps run, in order.

    Examples:
        ``report.steps`` is ``["build", "open", "identify", "health", "safe_state", "close"]``
        for a driver with every hook.
    """

    instance: Any
    identity: Identity | None = None
    health: Health | None = None
    safe_state_ran: bool = False
    steps: list[str] = field(default_factory=list)


def check_lifecycle(cls: type, config: Mapping[str, Any], **io: object) -> LifecycleReport:
    """Run a driver through the station's lifecycle with fake I/O, checking each step.

    Steps: build (validate config, inject I/O), ``open``, ``identify``, ``health``, safe
    state, ``close``. Hooks the driver doesn't define are skipped. Each step must not
    raise. ``identify`` must return an `Identity`, and ``health`` a healthy `Health`.

    Args:
        cls: The driver class.
        config: The ``config:`` mapping a station profile would contain.
        **io: The fake to inject for each I/O parameter, by parameter name.

    Returns:
        A report for further assertions.

    Raises:
        AssertionError: Naming the step that failed and why.

    Examples:
        >>> from mastif_testing import FakeLineIO
        >>> from mastif.resources._examples import ExamplePsu
        >>> from mastif.resources.transports import Scpi
        >>> io = FakeLineIO()
        >>> report = check_lifecycle(
        ...     ExamplePsu, {"transport": {"kind": "tcp", "host": "h", "port": 1}}, io=Scpi(io))
        >>> report.steps, report.safe_state_ran, io.written
        (['build', 'safe_state'], True, ['OUTP OFF'])
    """
    spec = spec_of(cls)
    missing = set(spec.io_params) - set(io)
    if missing:
        raise AssertionError(f"provide fakes for I/O parameters: {sorted(missing)}")

    def inject(want: type, transport: object, log: object) -> object:
        """Hand out the caller's fakes by parameter type.

        Examples:
            For ``io: Scpi`` this returns the fake passed as ``io=``.
        """
        for param, kind in spec.io_params.items():
            if kind is want:
                return io[param]
        raise AssertionError(f"no fake for {want.__name__}")

    report = LifecycleReport(instance=None)

    def step(name: str, fn: Any) -> Any:
        """Run one step, recording it and turning any exception into a clear assertion.

        Examples:
            ``step("open", lambda: call_hook(obj, "open"))``
        """
        try:
            result = fn()
        except Exception as exc:
            raise AssertionError(f"{spec.id}: step {name!r} failed: {exc!r}") from exc
        report.steps.append(name)
        return result

    built = step("build", lambda: build_resource(spec, config, name="dut", io_factory=inject))
    report.instance = built.instance
    if has_hook(built.instance, "open"):
        step("open", lambda: call_hook(built.instance, "open"))
    if has_hook(built.instance, "identify"):
        identity = step("identify", lambda: call_hook(built.instance, "identify"))
        if not isinstance(identity, Identity):
            raise AssertionError(f"{spec.id}: identify() returned {identity!r}, not an Identity")
        report.identity = identity
    if has_hook(built.instance, "health"):
        health = step("health", lambda: call_hook(built.instance, "health"))
        if not isinstance(health, Health) or not health.ok:
            raise AssertionError(f"{spec.id}: health() returned {health!r}")
        report.health = health
    ran = make_safe(built)
    if ran:
        report.steps.append("safe_state")
    report.safe_state_ran = ran
    if has_hook(built.instance, "close"):
        step("close", lambda: call_hook(built.instance, "close"))
    return report
