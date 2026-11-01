"""Drivers and DUT types: how an organisation teaches mastif about its hardware.

Why this exists:
    A driver is the one place where knowledge of a specific device lives: which
    commands to send and how to read the replies. Everything else (tests, the station,
    the engine) should only see the contracts the driver provides. mastif keeps the
    ceremony for writing one as small as possible:

    - mark the class with ``@driver(id, provides=[...])``; no base class needed
    - declare its settings as a nested ``Config(DriverConfig)``
    - ask for I/O by annotating ``__init__`` parameters (``io: Scpi``)
    - optionally implement lifecycle hooks: ``open``, ``identify``, ``health``,
      ``safe_state``, ``close``

    The decorator validates all of this when the module is imported, and attaches a
    `DriverSpec` to the class. It does not register the class anywhere. Importing a
    driver module has no global side effects; discovery is the `Registry`'s job.

A DUT is just a resource with **channels**:
    A device under test usually needs several ways in at once, e.g. a serial console
    for commands and a UDP channel for data. ``@dut`` is ``@driver`` for such classes.
    Each channel is declared with `channel` and a contract type. The station builds
    each channel from the profile (as a resource of its own) and attaches it before the
    DUT's ``open()`` runs::

        @dut("demo.widget-board", state=WidgetState)
        class WidgetBoard:
            console: Shell = channel()
            ctrl: MessageChannel = channel()

            def identify(self) -> Identity:
                return Identity(serial=self.console.execute("serial").output)

Where it fits:
    `Registry` collects classes carrying a `DriverSpec`. The station uses
    `build_resource` to turn a profile entry into a live object, and the lifecycle
    helpers (`call_hook`, `make_safe`) to open, check and close it.
"""

import inspect
import logging
import re
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict

from mastif.infra.config import Settings
from mastif.resources.contracts import check_provides, contract_info
from mastif.resources.errors import DriverDefinitionError, ResourceError
from mastif.resources.transports.config import TransportConfig
from mastif.resources.transports.factory import IO_TYPES, build_io

T = TypeVar("T", bound=type)
"""Class type variable preserving the type returned by driver and DUT decorators."""

type Kind = Literal["instrument", "dut"]
"""Resource category recorded in a driver specification."""
type IoFactory = Callable[[type, TransportConfig, logging.Logger | None], object]
"""Factory receiving the requested I/O type, transport configuration, and optional logger."""

_ID_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_-]+)+$")
LIFECYCLE_HOOKS: tuple[str, ...] = ("open", "identify", "health", "safe_state", "close")
"""Hook names validated for no-argument calls; this tuple is not an execution schedule."""


class DriverConfig(BaseModel):
    """Base class for a driver's settings, as written under ``config:`` in a station profile.

    Subclass it as a nested class named ``Config``. Unknown keys are rejected, so a
    typo in a profile fails clearly when the station is built. If the driver asks for
    injected I/O, declare a ``transport`` field typed with one of the transport configs.

    Examples:
        >>> from mastif.resources.transports import TcpConfig
        >>> class Config(DriverConfig):
        ...     transport: TcpConfig
        ...     channel: int = 1
        >>> raw = {"transport": {"kind": "tcp", "host": "10.0.0.5", "port": 5025}}
        >>> Config.model_validate(raw).channel
        1
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class NoConfig(DriverConfig):
    """The config of a driver that declares none: accepts only an empty mapping.

    Examples:
        >>> NoConfig.model_validate({})
        NoConfig()
    """


@dataclass(frozen=True, slots=True)
class ChannelSpec:
    """One declared DUT channel: its attribute name and the contract it must provide.

    Attributes:
        name: Attribute name on the DUT class, and key under ``channels:`` in the profile.
        contract: The contract the channel's driver must satisfy.
        optional: If True, the profile may leave the channel out; the attribute is then ``None``.

    Examples:
        >>> from mastif.resources.std import Shell
        >>> ChannelSpec("console", Shell).optional
        False
    """

    name: str
    contract: type
    optional: bool = False


class _ChannelMarker:
    """Class-level placeholder created by `channel`, replaced per instance by the station.

    It is a non-data descriptor, so the instance attribute the station sets takes
    precedence. Reading the attribute before that happens raises a clear error instead
    of returning the placeholder.

    Examples:
        ``console: Shell = channel()`` puts a marker on the class until the station attaches
        a real channel.
    """

    def __init__(self, optional: bool) -> None:
        """Remember whether the channel is optional.

        Examples:
            ``_ChannelMarker(optional=False)``
        """
        self.optional = optional
        self.name = ""

    def __set_name__(self, owner: type, name: str) -> None:
        """Learn the attribute name the marker was assigned to.

        Examples:
            For ``console: Shell = channel()`` the name is ``"console"``.
        """
        self.name = name

    def __get__(self, instance: object, owner: type | None = None) -> Any:
        """Return the marker on the class; raise when read on an unconnected instance.

        Raises:
            ResourceError: If the channel hasn't been attached by the station.

        Examples:
            ``WidgetBoard.console`` returns the marker; ``board.console`` before attachment raises.
        """
        if instance is None:
            return self
        if self.optional:
            return None
        raise ResourceError(
            f"channel {self.name!r} is not connected; DUT channels are attached by the station"
        )


def channel(*, optional: bool = False) -> Any:
    """Declare a DUT channel; the annotation names the contract it must provide.

    Args:
        optional: Allow station profiles to omit this channel (attribute is then ``None``).

    Returns:
        A placeholder the station replaces with the real channel object per instance.

    Examples:
        >>> from mastif.resources.std import Shell
        >>> @dut("demo.board")
        ... class Board:
        ...     console: Shell = channel()
        >>> spec_of(Board).channels["console"].contract is Shell
        True
    """
    return _ChannelMarker(optional)


@dataclass(frozen=True)
class DriverSpec:
    """Everything mastif learned about a driver class when it was decorated.

    Attributes:
        id: Globally unique id, ``"<org>.<name>"``, used in station profiles.
        cls: The driver class.
        kind: ``"instrument"`` or ``"dut"``.
        provides: Contracts the class claims (and was checked) to satisfy.
        config_model: The class's ``Config`` (or `NoConfig`).
        config_param: Name of the ``__init__`` parameter receiving the config, if any.
        io_params: ``__init__`` parameter name to the I/O type to inject.
        logger_param: Name of the ``__init__`` parameter receiving a logger, if any.
        settings_param: Name of the ``__init__`` parameter receiving the application
            settings (annotated `mastif.infra.config.Settings`), if any.
        channels: Declared channels, by name.
        state_model: Pydantic model for the resource's live state, if declared.

    Examples:
        >>> from mastif.resources.std import PowerSupply
        >>> from mastif.resources._examples import ExamplePsu
        >>> spec_of(ExamplePsu).io_params
        {'io': <class 'mastif.resources.transports.scpi.Scpi'>}
    """

    id: str
    cls: type
    kind: Kind
    provides: tuple[type, ...]
    config_model: type[DriverConfig]
    config_param: str | None
    io_params: dict[str, type]
    logger_param: str | None
    channels: dict[str, ChannelSpec] = field(default_factory=dict)
    state_model: type[BaseModel] | None = None
    settings_param: str | None = None

    def provides_contract(self, proto: type) -> bool:
        """Tell whether resources of this driver can serve a role needing ``proto``.

        A contract counts if it was declared in ``provides``, or if the class satisfies
        it structurally. Orgs can therefore use contracts the driver author never knew
        about.

        Args:
            proto: The required contract.

        Returns:
            True if the driver can serve it.

        Examples:
            >>> from mastif.resources.std import PowerSupply, Shell
            >>> from mastif.resources._examples import ExamplePsu
            >>> spec_of(ExamplePsu).provides_contract(PowerSupply)
            True
            >>> spec_of(ExamplePsu).provides_contract(Shell)
            False
        """
        from mastif.resources.contracts import satisfies  # noqa: PLC0415  (avoid cycle)

        return proto in self.provides or satisfies(self.cls, proto)


def _hints(fn: Callable[..., Any], cls: type) -> dict[str, Any]:
    """Resolve a function's annotations, letting them refer to names in the class body.

    ``def __init__(self, cfg: Config, ...)`` refers to the nested ``Config`` class, which
    only resolves with the class namespace available.

    Raises:
        DriverDefinitionError: If an annotation can't be resolved.

    Examples:
        ``_hints(PsuX.__init__, PsuX)`` returns ``{"cfg": PsuX.Config, "io": Scpi, ...}``.
    """
    try:
        return typing.get_type_hints(fn, localns=dict(vars(cls)))
    except Exception as exc:
        raise DriverDefinitionError(f"{cls.__name__}: cannot resolve annotations: {exc}") from exc


@dataclass
class _InitPlan:
    """Which ``__init__`` parameters receive which injected values.

    Examples:
        ``def __init__(self, cfg: Config, io: Scpi)`` gives
        ``_InitPlan(config_param="cfg", io_params={"io": Scpi})``.
    """

    config_param: str | None = None
    io_params: dict[str, type] = field(default_factory=dict)
    logger_param: str | None = None
    settings_param: str | None = None


def _inspect_init(driver_id: str, cls: type, config_model: type[DriverConfig]) -> _InitPlan:
    """Work out which ``__init__`` parameters receive the config, I/O, logger and settings.

    The rules, by annotation:

    - the driver's ``Config`` (or any `DriverConfig`): the validated config
    - an injectable I/O type: that I/O
    - ``logging.Logger``: a logger named after the resource
    - `mastif.infra.config.Settings`: the application settings given to the station

    Any other parameter must have a default value.

    Returns:
        The injection plan.

    Raises:
        DriverDefinitionError: For parameters mastif can't supply, or I/O without a
            ``transport`` config field.

    Examples:
        ``def __init__(self, cfg: Config, io: Scpi, settings: Settings)`` gives
        ``config_param="cfg"``, ``io_params={"io": Scpi}``, ``settings_param="settings"``.
    """
    plan = _InitPlan()
    init = cls.__init__
    if init is object.__init__:
        return plan
    hints = _hints(init, cls)
    params = list(inspect.signature(init).parameters.values())[1:]
    for p in params:
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        hint = hints.get(p.name)
        if isinstance(hint, type) and issubclass(hint, DriverConfig):
            plan.config_param = p.name
        elif hint in IO_TYPES:
            plan.io_params[p.name] = hint
        elif hint is logging.Logger:
            plan.logger_param = p.name
        elif isinstance(hint, type) and issubclass(hint, Settings):
            plan.settings_param = p.name
        elif p.default is p.empty:
            raise DriverDefinitionError(
                f"{driver_id}: __init__ parameter {p.name!r} can't be supplied by mastif; "
                "annotate it with the Config class, an I/O type, logging.Logger, Settings, "
                "or give it a default"
            )
    if plan.io_params and "transport" not in config_model.model_fields:
        raise DriverDefinitionError(
            f"{driver_id}: asks for injected I/O but Config has no 'transport' field"
        )
    return plan


def _collect_channels(driver_id: str, cls: type) -> dict[str, ChannelSpec]:
    """Find `channel` declarations and the contracts their annotations name.

    Raises:
        DriverDefinitionError: If a channel has no annotation.

    Examples:
        ``console: Shell = channel()`` gives ``{"console": ChannelSpec("console", Shell)}``.
    """
    markers = {
        name: value
        for base in reversed(cls.__mro__)
        for name, value in vars(base).items()
        if isinstance(value, _ChannelMarker)
    }
    if not markers:
        return {}
    hints = _hints(lambda: None, cls) | typing.get_type_hints(cls)
    channels = {}
    for name, marker in markers.items():
        proto = hints.get(name)
        if not isinstance(proto, type):
            raise DriverDefinitionError(
                f"{driver_id}: channel {name!r} needs a contract annotation, "
                f"e.g. '{name}: Shell = channel()'"
            )
        channels[name] = ChannelSpec(name, proto, marker.optional)
    return channels


def _decorate(
    driver_id: str, kind: Kind, provides: tuple[type, ...], state: type[BaseModel] | None
) -> Callable[[T], T]:
    """Build the class decorator shared by `driver` and `dut`.

    Examples:
        ``_decorate("acme.psu-x", "instrument", (PowerSupply,), None)(PsuX)``
    """

    def decorate(cls: T) -> T:
        """Validate the class and attach its `DriverSpec`; the class itself is unchanged.

        Examples:
            Runs once, when ``@driver(...)`` is applied at import time.
        """
        if not _ID_PATTERN.match(driver_id):
            raise DriverDefinitionError(
                f"driver id {driver_id!r} must look like 'org.name' (lowercase, dot-separated)"
            )
        config_model = getattr(cls, "Config", NoConfig)
        if not (isinstance(config_model, type) and issubclass(config_model, DriverConfig)):
            raise DriverDefinitionError(f"{driver_id}: Config must subclass DriverConfig")
        if state is not None and not issubclass(state, BaseModel):
            raise DriverDefinitionError(f"{driver_id}: state must be a pydantic model")
        check_provides(driver_id, cls, provides)
        plan = _inspect_init(driver_id, cls, config_model)
        spec = DriverSpec(
            id=driver_id,
            cls=cls,
            kind=kind,
            provides=provides,
            config_model=config_model,
            config_param=plan.config_param,
            io_params=plan.io_params,
            logger_param=plan.logger_param,
            settings_param=plan.settings_param,
            channels=_collect_channels(driver_id, cls),
            state_model=state,
        )
        setattr(cls, "__mastif_driver__", spec)  # noqa: B010
        return cls

    return decorate


def driver(
    driver_id: str,
    *,
    provides: list[type] | tuple[type, ...] = (),
    state: type[BaseModel] | None = None,
) -> Callable[[T], T]:
    """Mark a class as an instrument driver.

    Everything is checked when the class is defined: id format, the ``Config`` class,
    the contracts in ``provides``, and that mastif can supply every ``__init__``
    parameter. A mistake therefore fails the import of the org's driver module, which
    its own tests will catch.

    Args:
        driver_id: Unique id ``"<org>.<name>"``, referenced by station profiles.
        provides: Contracts this driver implements.
        state: Optional Pydantic model for live state; an instance is created as
            ``self.state`` unless ``__init__`` sets it.

    Returns:
        A class decorator that returns the class unchanged, with a `DriverSpec` attached.

    Raises:
        DriverDefinitionError: Or its subclass `ContractMismatch`, if anything is wrong.

    Examples:
        >>> from mastif.resources.std import Relay
        >>> @driver("acme.relays", provides=[Relay])
        ... class AcmeRelays:
        ...     def set(self, channel, closed): ...
        ...     def is_closed(self, channel): return False
        ...     def open_all(self): ...
        >>> spec_of(AcmeRelays).id
        'acme.relays'
    """
    return _decorate(driver_id, "instrument", tuple(provides), state)


def dut(
    driver_id: str,
    *,
    provides: list[type] | tuple[type, ...] = (),
    state: type[BaseModel] | None = None,
) -> Callable[[T], T]:
    """Mark a class as a DUT type: a resource that usually has channels and live state.

    Identical to `driver` apart from the recorded kind. The engine uses the kind to
    attach DUT identity and state to results and run snapshots.

    Args:
        driver_id: Unique id ``"<org>.<name>"``.
        provides: Contracts the DUT itself implements (often none).
        state: Pydantic model for the DUT's live state (firmware loaded, mode...). mastif
            creates ``self.state`` from it. Also annotate ``state: MyState`` on the class,
            so type checkers know the attribute exists.

    Returns:
        A class decorator.

    Examples:
        >>> from pydantic import BaseModel
        >>> from mastif.resources.std import Shell
        >>> class BoardState(BaseModel):
        ...     booted: bool = False
        >>> @dut("demo.board-x", state=BoardState)
        ... class BoardX:
        ...     console: Shell = channel()
        ...     state: BoardState
        >>> spec_of(BoardX).kind, list(spec_of(BoardX).channels)
        ('dut', ['console'])
    """
    return _decorate(driver_id, "dut", tuple(provides), state)


def spec_of(cls: type) -> DriverSpec:
    """Return the `DriverSpec` attached by ``@driver`` or ``@dut``.

    Args:
        cls: A decorated class.

    Returns:
        Its spec.

    Raises:
        DriverDefinitionError: If the class was not decorated.

    Examples:
        >>> from mastif.resources._examples import ExamplePsu
        >>> spec_of(ExamplePsu).id
        'demo.example-psu'
        >>> spec_of(int)
        Traceback (most recent call last):
        ...
        mastif.resources.errors.DriverDefinitionError: int is not decorated with @driver or @dut
    """
    spec = cls.__dict__.get("__mastif_driver__")
    if not isinstance(spec, DriverSpec):
        raise DriverDefinitionError(f"{cls.__name__} is not decorated with @driver or @dut")
    return spec


def is_driver(obj: object) -> bool:
    """Tell whether an object is a class decorated with ``@driver`` or ``@dut``.

    Examples:
        >>> from mastif.resources._examples import ExamplePsu
        >>> is_driver(ExamplePsu), is_driver(int)
        (True, False)
    """
    return isinstance(obj, type) and isinstance(obj.__dict__.get("__mastif_driver__"), DriverSpec)


@dataclass
class BuiltResource:
    """A driver instance together with the config and I/O objects created for it.

    The station keeps one of these per resource, so it knows what to open before the
    driver and close after it.

    Attributes:
        name: The resource's name in the station profile.
        spec: The driver's spec.
        instance: The driver object.
        config: The validated config.
        io: Injected I/O objects, in parameter order.

    Examples:
        ``build_resource(spec_of(PsuX), {...}, name="bench_psu").instance`` is a ``PsuX``.
    """

    name: str
    spec: DriverSpec
    instance: Any
    config: DriverConfig
    io: list[Any] = field(default_factory=list)


def build_resource(
    spec: DriverSpec,
    raw_config: Mapping[str, Any],
    *,
    name: str,
    io_factory: IoFactory = build_io,
    logger: logging.Logger | None = None,
    settings: Settings | None = None,
) -> BuiltResource:
    """Validate a profile's config and construct the driver, injecting what it asked for.

    No I/O happens here: transports are created but not opened. Building every resource
    is therefore cheap and safe, and the station can validate a whole profile before
    anything is touched.

    Args:
        spec: The driver's spec.
        raw_config: The ``config:`` mapping from the station profile.
        name: The resource name, used for the logger and messages.
        io_factory: Builds I/O objects; pass a function returning fakes in tests.
        logger: Parent logger; the driver gets a child named after the resource.
        settings: The application settings, given to drivers that ask for them with a
            parameter annotated `Settings`.

    Returns:
        The built resource.

    Raises:
        pydantic.ValidationError: If the config is invalid.
        DriverDefinitionError: If the requested I/O can't be built from the transport.
        ResourceError: If the driver asks for settings and none were given.

    Examples:
        >>> from mastif_testing import FakeLineIO
        >>> from mastif.resources._examples import ExamplePsu
        >>> from mastif.resources.transports import Scpi
        >>> fake = Scpi(FakeLineIO({"MEAS:CURR?": "0.18"}))
        >>> built = build_resource(
        ...     spec_of(ExamplePsu),
        ...     {"transport": {"kind": "tcp", "host": "10.0.0.5", "port": 5025}},
        ...     name="bench_psu",
        ...     io_factory=lambda want, cfg, log: fake,
        ... )
        >>> built.instance.measure_current()
        Quantity(value=0.18, unit='A')
    """
    log = (logger or logging.getLogger("mastif.resources")).getChild(name)
    config = spec.config_model.model_validate(dict(raw_config))
    kwargs: dict[str, Any] = {}
    io: list[Any] = []
    if spec.config_param:
        kwargs[spec.config_param] = config
    for param, want in spec.io_params.items():
        obj = io_factory(want, getattr(config, "transport"), log)  # noqa: B009
        kwargs[param] = obj
        io.append(obj)
    if spec.logger_param:
        kwargs[spec.logger_param] = log
    if spec.settings_param:
        if settings is None:
            raise ResourceError(
                f"{name}: driver {spec.id} needs application settings; "
                "pass settings= when building the station"
            )
        kwargs[spec.settings_param] = settings
    instance = spec.cls(**kwargs)
    if spec.state_model is not None and "state" not in vars(instance):
        instance.state = spec.state_model()
    return BuiltResource(name=name, spec=spec, instance=instance, config=config, io=io)


def call_hook(instance: object, hook: str) -> Any:
    """Call an optional lifecycle hook if the driver defines it.

    Args:
        instance: The driver object.
        hook: One of `LIFECYCLE_HOOKS`.

    Returns:
        The hook's return value, or ``None`` if the driver doesn't define it.

    Examples:
        >>> class D:
        ...     def health(self): return "fine"
        >>> call_hook(D(), "health"), call_hook(D(), "open")
        ('fine', None)
    """
    fn = getattr(instance, hook, None)
    return fn() if callable(fn) else None


def has_hook(instance: object, hook: str) -> bool:
    """Tell whether a driver defines an optional lifecycle hook.

    Examples:
        >>> class D:
        ...     def identify(self): ...
        >>> has_hook(D(), "identify"), has_hook(D(), "health")
        (True, False)
    """
    return callable(getattr(instance, hook, None))


def make_safe(built: BuiltResource) -> bool:
    """Put a resource into its safe state.

    The driver's own ``safe_state()`` takes precedence. Otherwise, the safe-state
    actions of every contract it provides are run (e.g. "output off" for
    `PowerSupply`).

    Args:
        built: The resource.

    Returns:
        True if any safe-state action ran, False if the resource has none.

    Examples:
        >>> from mastif_testing import FakeLineIO
        >>> from mastif.resources._examples import ExamplePsu
        >>> from mastif.resources.transports import Scpi
        >>> io = FakeLineIO()
        >>> built = build_resource(
        ...     spec_of(ExamplePsu),
        ...     {"transport": {"kind": "tcp", "host": "h", "port": 1}},
        ...     name="psu",
        ...     io_factory=lambda *_: Scpi(io),
        ... )
        >>> make_safe(built), io.written
        (True, ['OUTP OFF'])
    """
    if has_hook(built.instance, "safe_state"):
        built.instance.safe_state()
        return True
    ran = False
    for proto in built.spec.provides:
        action = contract_info(proto).safe_state
        if action is None:
            continue
        if isinstance(action, str):
            getattr(built.instance, action)()
        else:
            action(built.instance)
        ran = True
    return ran
