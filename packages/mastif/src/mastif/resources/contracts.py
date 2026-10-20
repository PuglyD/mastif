"""Contracts: what a test needs a resource to be able to do.

Why this exists:
    A test that measures standby current needs *something that can set a voltage and
    read a current*. It doesn't care whether that is a particular vendor's bench supply
    or a simulator. Writing tests against such capabilities, rather than against device
    models, lets one test run on stations with different hardware, and lets drivers be
    swapped without touching tests.

    In mastif that capability is a **contract**: a plain `typing.Protocol`. No mastif
    import or base class is needed to define one, so an organisation can write its
    contracts in a few lines::

        from typing import Protocol
        from mastif.kernel.units import Volts, Amps

        class PowerSupply(Protocol):
            def set_voltage(self, v: Volts) -> None: ...
            def measure_current(self) -> Amps: ...

Where it fits:
    - Test tasks request resources by contract: ``psu: PowerSupply = requires("psu_main")``.
    - Drivers declare what they provide: ``@driver("acme.psu-x", provides=[PowerSupply])``.
      The decorator calls `check_provides`, so a driver that forgets a method fails when
      its module is imported, not at a test station.
    - Static type checkers verify the same match at development time.

The optional `contract` decorator adds metadata the runtime can use, currently how to
put a resource providing this contract into a safe state.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, TypeVar

from mastif.resources.errors import ContractMismatch

T = TypeVar("T", bound=type)

type SafeStateAction = str | Callable[[Any], None]

_IGNORED_BASES = {object, Protocol}


@dataclass(frozen=True, slots=True)
class ContractInfo:
    """Metadata attached to a contract by `@contract`.

    Attributes:
        name: Display name used in error messages and reports.
        safe_state: How to make a resource that provides this contract safe. Either the
            name of a method taking no arguments, or a function receiving the resource.

    Example:
        >>> ContractInfo(name="PowerSupply", safe_state="disable").safe_state
        'disable'
    """

    name: str
    safe_state: SafeStateAction | None = None


def contract(
    *, name: str | None = None, safe_state: SafeStateAction | None = None
) -> Callable[[T], T]:
    """Optionally annotate a contract Protocol with runtime metadata.

    Contracts work without this decorator. Use it when the station should know how to
    make any resource providing the contract safe, for example by switching a supply's
    output off when a run is aborted. The station calls this action only if the driver
    has no ``safe_state()`` method of its own.

    Args:
        name: Display name; defaults to the class name.
        safe_state: A method name taking no arguments (``"disable_output"``), or a
            function receiving the resource (``lambda psu: psu.output(False)``).

    Returns:
        A class decorator that attaches `ContractInfo` and returns the class unchanged.

    Example:
        >>> from typing import Protocol
        >>> @contract(safe_state=lambda psu: psu.output(False))
        ... class PowerSupply(Protocol):
        ...     def output(self, enabled: bool) -> None: ...
        >>> contract_info(PowerSupply).name
        'PowerSupply'
    """

    # No functools.wraps here: wraps copies metadata onto a *new* wrapper object. This
    # decorator creates no wrapper; it returns the very same class with one attribute
    # added, so the name, docstring and type identity are untouched.
    def decorate(cls: T) -> T:
        """Attach the metadata to the Protocol class.

        Example:
            ``decorate(PowerSupply)`` sets ``PowerSupply.__mastif_contract__``.
        """
        setattr(cls, "__mastif_contract__", ContractInfo(name or cls.__name__, safe_state))  # noqa: B010
        return cls

    return decorate


def contract_info(proto: type) -> ContractInfo:
    """Return a contract's metadata, with defaults for undecorated Protocols.

    Args:
        proto: The contract Protocol.

    Returns:
        The attached `ContractInfo`, or one with only the class name.

    Example:
        >>> from typing import Protocol
        >>> class Thermometer(Protocol):
        ...     def read(self) -> float: ...
        >>> contract_info(Thermometer)
        ContractInfo(name='Thermometer', safe_state=None)
    """
    info = proto.__dict__.get("__mastif_contract__")
    return info if isinstance(info, ContractInfo) else ContractInfo(proto.__name__)


def contract_members(proto: type) -> dict[str, Any]:
    """List the public methods and properties a contract requires, including inherited ones.

    Contracts can extend each other (``class SweepingSource(SignalSource, Protocol)``),
    so members are collected from the whole Protocol hierarchy. Plain attribute
    annotations (``channel_count: int``) are not listed. A driver usually sets those in
    ``__init__``, so they can't be checked on the class.

    Args:
        proto: The contract Protocol.

    Returns:
        Member name to the member object (function or property), in definition order.

    Example:
        >>> from typing import Protocol
        >>> class Source(Protocol):
        ...     def output(self, enabled: bool) -> None: ...
        >>> class SweepingSource(Source, Protocol):
        ...     def sweep(self, start: float, stop: float) -> None: ...
        >>> list(contract_members(SweepingSource))
        ['sweep', 'output']
    """
    members: dict[str, Any] = {}
    for base in proto.__mro__:
        if base in _IGNORED_BASES or not getattr(base, "_is_protocol", False):
            continue
        for name, value in vars(base).items():
            if name.startswith("_") or name in members:
                continue
            if callable(value) or isinstance(value, property):
                members[name] = value
    return members


def _accepts_same_call(required: Any, provided: Any) -> bool:
    """Tell whether ``provided`` can be called the way the contract's ``required`` is.

    The check binds dummy arguments shaped like the contract's full signature (every
    positional parameter positionally, every keyword-only one by name) to the
    implementation. The implementation may add optional parameters or accept
    ``*args``/``**kwargs``. It may not require more than the contract offers, or accept
    fewer.

    Args:
        required: The contract's function.
        provided: The implementation's function.

    Returns:
        True if every call valid for the contract is valid for the implementation.

    Example:
        >>> def need(self, v): ...
        >>> def impl_ok(self, v, settle=0.1): ...
        >>> def impl_bad(self): ...
        >>> _accepts_same_call(need, impl_ok), _accepts_same_call(need, impl_bad)
        (True, False)
    """
    try:
        need = inspect.signature(required)
        have = inspect.signature(provided)
    except (TypeError, ValueError):
        return True
    args: list[object] = []
    kwargs: dict[str, object] = {}
    for p in need.parameters.values():
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD):
            args.append(None)
        elif p.kind is p.KEYWORD_ONLY:
            kwargs[p.name] = None
    try:
        have.bind(*args, **kwargs)
    except TypeError:
        return False
    return True


class ProblemKind(StrEnum):
    """The ways a class can fail to satisfy a contract.

    Using an enum, not free text, lets tooling react to a problem. For example, a
    driver scaffolder could generate stubs for every `MISSING` member.

    Example:
        >>> ProblemKind.MISSING.value
        'missing'
    """

    MISSING = "missing"
    NOT_CALLABLE = "not callable"
    NOT_A_PROPERTY = "expected a property"
    INCOMPATIBLE_PARAMETERS = "incompatible parameters"


@dataclass(frozen=True, slots=True)
class ContractProblem:
    """One reason a class does not satisfy a contract.

    Attributes:
        member: The contract member concerned, e.g. ``"output"``.
        kind: What is wrong with it.

    Example:
        >>> str(ContractProblem("output", ProblemKind.MISSING))
        'output: missing'
    """

    member: str
    kind: ProblemKind

    def __str__(self) -> str:
        """Render as ``"<member>: <kind>"`` for error messages.

        Example:
            >>> str(ContractProblem("route", ProblemKind.INCOMPATIBLE_PARAMETERS))
            'route: incompatible parameters'
        """
        return f"{self.member}: {self.kind.value}"


def contract_problems(cls: type, proto: type) -> list[ContractProblem]:
    """List every way a class fails to satisfy a contract.

    Why not ``typing.runtime_checkable`` and ``isinstance``? The standard runtime check
    only looks at member *names*, never parameters. It also needs every contract to be
    decorated, works on instances rather than classes (``issubclass`` refuses
    protocols with properties), and answers with a bare ``False``. Static checkers do
    compare signatures, but only in projects that run one, and not when mastif loads a
    driver. This function adds a parameter-compatibility check and explains each
    problem.

    Args:
        cls: The candidate implementation (usually a driver class).
        proto: The contract Protocol.

    Returns:
        One `ContractProblem` per problem, in contract order; empty if satisfied.

    Example:
        >>> from typing import Protocol
        >>> class Switch(Protocol):
        ...     def route(self, a: str, b: str) -> None: ...
        ...     def clear(self) -> None: ...
        >>> class HalfSwitch:
        ...     def route(self, a): ...
        >>> [str(p) for p in contract_problems(HalfSwitch, Switch)]
        ['route: incompatible parameters', 'clear: missing']
    """
    problems: list[ContractProblem] = []
    for name, required in contract_members(proto).items():
        provided = inspect.getattr_static(cls, name, None)
        kind: ProblemKind | None = None
        if provided is None:
            kind = ProblemKind.MISSING
        elif isinstance(required, property):
            if not isinstance(provided, property):
                kind = ProblemKind.NOT_A_PROPERTY
        elif not callable(provided):
            kind = ProblemKind.NOT_CALLABLE
        elif not _accepts_same_call(required, provided):
            kind = ProblemKind.INCOMPATIBLE_PARAMETERS
        if kind is not None:
            problems.append(ContractProblem(name, kind))
    return problems


def satisfies(cls: type, proto: type) -> bool:
    """Tell whether a class satisfies a contract (has every member, with compatible calls).

    Use this for yes/no decisions, such as the station checking that a role's resource
    can serve a task. Use `contract_problems` when you need to explain the answer.

    Args:
        cls: The candidate implementation.
        proto: The contract Protocol.

    Returns:
        True if `contract_problems` finds nothing.

    Example:
        >>> from typing import Protocol
        >>> class Thermometer(Protocol):
        ...     def read(self) -> float: ...
        >>> class Fake:
        ...     def read(self) -> float:
        ...         return 21.5
        >>> satisfies(Fake, Thermometer)
        True
    """
    return not contract_problems(cls, proto)


def check_provides(owner: str, cls: type, contracts: tuple[type, ...]) -> None:
    """Raise if a class does not satisfy every contract it claims to provide.

    `@driver` calls this when the class is decorated. Errors therefore surface when the
    org's driver module is imported, typically in its own unit tests.

    Args:
        owner: Driver id, for the error message.
        cls: The driver class.
        contracts: The contracts it claims to provide.

    Raises:
        ContractMismatch: Listing every problem with every contract.

    Example:
        >>> from typing import Protocol
        >>> class Probe(Protocol):
        ...     def read(self) -> float: ...
        >>> class Broken: ...
        >>> check_provides("acme.t1", Broken, (Probe,))
        Traceback (most recent call last):
        ...
        mastif.resources.errors.ContractMismatch: acme.t1 does not provide Probe: read: missing
    """
    errors = []
    for proto in contracts:
        problems = contract_problems(cls, proto)
        if problems:
            errors.append(f"{contract_info(proto).name}: {', '.join(map(str, problems))}")
    if errors:
        raise ContractMismatch(f"{owner} does not provide " + "; ".join(errors))
