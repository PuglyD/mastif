"""The station: the composition root that turns a profile into live, role-addressable resources.

Why this exists:
    Tests ask for capabilities by role (``psu: PowerSupply = requires("psu_main")``).
    Something must decide which concrete driver plays that role, build it with the
    right config and I/O, attach DUT channels, and check that the role's resource can
    actually do what the test needs. Doing all of this in one place (a "composition
    root") keeps drivers ignorant of each other, and keeps tests ignorant of hardware.

Two phases, deliberately separate:
    - ``Station.build(profile, registry)`` validates **everything** without touching
      hardware: driver ids, configs, DUT channel mappings and contracts. A broken profile
      fails here, in seconds, with the resource name in the message.
    - ``station.open()`` does the I/O, through the `ResourceManager`.

Where it fits:
    The engine builds the station at run start, runs preflight checks with
    `Station.role_problems`, opens it, resolves each task's ``requires(...)`` with
    `Station.require`, and calls ``safe_state()`` / ``close()`` at the end. In org tests
    and notebooks it can be used directly::

        with Station.build(StationProfile.load("bench-01.yaml"), Registry.discover()) as st:
            psu = st.require("psu_main", PowerSupply)
            psu.set_voltage(12 * V)
"""

import logging
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Self

from pydantic import ValidationError

from mastif.infra.config import Settings
from mastif.resources.contracts import contract_info
from mastif.resources.driver import IoFactory, build_resource
from mastif.resources.errors import DriverDefinitionError, DriverNotFound, ResourceError
from mastif.resources.identity import Identity
from mastif.resources.registry import Registry
from mastif.resources.transports.factory import build_io
from mastif.station.errors import RoleError, StationError
from mastif.station.manager import Listener, ResourceHandle, ResourceManager
from mastif.station.profile import ChannelEntry, ResourceEntry, StationProfile


def _config_error(where: str, exc: ValidationError) -> StationError:
    """Turn a Pydantic config error into a `StationError` naming the resource and fields.

    Example:
        ``resource 'bench_psu': invalid config: chanel: Extra inputs are not permitted``
    """
    details = "; ".join(
        f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors()
    )
    return StationError(f"{where}: invalid config: {details}")


class Station:
    """A built station: resources by name, roles, and their lifecycle.

    Example:
        >>> from mastif.resources._examples import ExamplePsu
        >>> from mastif.resources.std import PowerSupply
        >>> profile = StationProfile.from_yaml('''
        ... station: bench-01
        ... resources:
        ...   bench_psu:
        ...     driver: demo.example-psu
        ...     config: {transport: {kind: tcp, host: 10.0.0.5, port: 5025}}
        ... roles: {psu_main: bench_psu}
        ... ''')
        >>> st = Station.build(profile, Registry([ExamplePsu]))
        >>> st.role_problems({"psu_main": PowerSupply})
        []
    """

    def __init__(
        self,
        profile: StationProfile,
        handles: dict[str, ResourceHandle],
        *,
        sim: bool = False,
        listener: Listener | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Wrap already-built handles; use `Station.build` rather than calling this.

        Example:
            ``Station(profile, handles)`` is what `build` returns.
        """
        self.profile = profile
        self.handles = handles
        self.sim = sim
        self.manager = ResourceManager(handles.values(), listener, logger)
        self.settings: Settings | None = None

    @property
    def name(self) -> str:
        """The station name from the profile.

        Example:
            ``station.name`` returns ``"bench-01"``.
        """
        return self.profile.station

    @classmethod
    def build(
        cls,
        profile: StationProfile,
        registry: Registry,
        *,
        sim: bool = False,
        io_factory: IoFactory = build_io,
        listener: Listener | None = None,
        logger: logging.Logger | None = None,
        settings: Settings | None = None,
    ) -> "Station":
        """Build every resource in the profile, without opening anything.

        Args:
            profile: The station profile.
            registry: Where driver ids are looked up.
            sim: Apply the profile's ``sim:`` replacements.
            io_factory: Builds injected I/O; pass a function returning fakes in tests.
            listener: Receives a `ResourceEvent` for every lifecycle step.
            logger: Parent logger for drivers and the manager.
            settings: Application settings (see `mastif.infra.config`), injected into
                every driver whose ``__init__`` asks for them.

        Returns:
            The station, closed.

        Raises:
            StationError: Naming the resource, for unknown drivers, invalid configs,
                missing, unknown or incompatible DUT channels, and impossible I/O.

        Example:
            >>> Station.build(StationProfile.from_yaml(
            ...     "station: s\\nresources: {psu: {driver: acme.nope}}"), Registry(builtin=False))
            Traceback (most recent call last):
            ...
            mastif.station.errors.StationError: resource 'psu': no driver 'acme.nope'; known: (none)
        """
        log = logger or logging.getLogger("mastif.station")
        handles = {
            name: cls._build_handle(name, entry, registry, io_factory, log, settings)
            for name, entry in profile.entries(sim).items()
        }
        station = cls(profile, handles, sim=sim, listener=listener, logger=log)
        station.settings = settings
        return station

    @staticmethod
    def _build_handle(
        name: str,
        entry: ResourceEntry | ChannelEntry,
        registry: Registry,
        io_factory: IoFactory,
        log: logging.Logger,
        settings: Settings | None = None,
    ) -> ResourceHandle:
        """Build one resource and, for DUTs, its channels; translate errors to `StationError`.

        Example:
            ``Station._build_handle("dut", entry, registry, build_io, log)``
        """
        where = f"resource {name!r}"
        try:
            spec = registry.get(entry.driver)
            built = build_resource(
                spec, entry.config, name=name, io_factory=io_factory, logger=log, settings=settings
            )
        except DriverNotFound as exc:
            raise StationError(f"{where}: {exc}") from exc
        except ValidationError as exc:
            raise _config_error(where, exc) from exc
        except (DriverDefinitionError, ResourceError) as exc:
            raise StationError(f"{where}: {exc}") from exc
        resource_entry = (
            entry if isinstance(entry, ResourceEntry) else ResourceEntry(driver=entry.driver)
        )
        handle = ResourceHandle(name=name, built=built, entry=resource_entry)
        given = entry.channels if isinstance(entry, ResourceEntry) else {}
        unknown = set(given) - set(spec.channels)
        if unknown:
            raise StationError(f"{where}: {spec.id} has no channel(s) {sorted(unknown)}")
        for ch_name, ch_spec in spec.channels.items():
            ch_entry = given.get(ch_name)
            if ch_entry is None:
                if ch_spec.optional:
                    continue
                raise StationError(f"{where}: channel {ch_name!r} is not mapped in the profile")
            child = Station._build_handle(
                f"{name}.{ch_name}", ch_entry, registry, io_factory, log, settings
            )
            if not child.spec.provides_contract(ch_spec.contract):
                raise StationError(
                    f"{where}: channel {ch_name!r} needs "
                    f"{contract_info(ch_spec.contract).name}, "
                    f"but {child.spec.id} doesn't provide it"
                )
            setattr(built.instance, ch_name, child.instance)
            handle.channels[ch_name] = child
        return handle

    def resource(self, name: str) -> ResourceHandle:
        """Return a resource's handle by its profile name.

        Raises:
            StationError: If there is no such resource.

        Example:
            ``station.resource("bench_psu").identity``
        """
        try:
            return self.handles[name]
        except KeyError:
            raise StationError(
                f"no resource {name!r}; known: {', '.join(self.handles) or '(none)'}"
            ) from None

    def role(self, role: str) -> Any:
        """Return the object playing a role: a resource, a DUT channel, or a child.

        ``resource.child`` targets resolve to a DUT channel (available once built) or to
        an entry of ``children()`` (available once open).

        Args:
            role: A role name, or a resource name used directly.

        Returns:
            The object.

        Raises:
            RoleError: If the role or its target doesn't exist (yet).

        Example:
            ``station.role("psu_main").measure_current()``
        """
        target = self.profile.target_of(role)
        root, _, child = target.partition(".")
        if root not in self.handles:
            known = sorted({*self.profile.roles, *self.handles})
            raise RoleError(f"no role {role!r}; known roles: {', '.join(known)}")
        handle = self.handles[root]
        if not child:
            return handle.instance
        if child in handle.channels:
            return handle.channels[child].instance
        if child in handle.children:
            return handle.children[child]
        state = "" if handle.is_open else " (children are known only once the station is open)"
        raise RoleError(f"role {role!r}: {root!r} has no channel or child {child!r}{state}")

    def require(self, role: str, contract: type) -> Any:
        """Return the object playing a role, checking it provides the contract a task needs.

        Args:
            role: The role name.
            contract: The contract the caller will use it as.

        Returns:
            The object.

        Raises:
            RoleError: If the role doesn't exist or can't serve the contract.

        Example:
            ``psu = station.require("psu_main", PowerSupply)``
        """
        obj = self.role(role)
        problem = self._contract_problem(role, contract, obj)
        if problem:
            raise RoleError(problem)
        return obj

    def _contract_problem(self, role: str, contract: type, obj: Any) -> str | None:
        """Explain why a role's object can't serve a contract, or return ``None``.

        Example:
            ``"role 'psu_main' (demo.example-psu) does not provide Shell"``
        """
        from mastif.resources.contracts import satisfies  # noqa: PLC0415

        target = self.profile.target_of(role)
        handle = self.handles.get(target)
        if handle is not None:
            ok = handle.spec.provides_contract(contract)
            what = handle.spec.id
        else:
            ok = satisfies(type(obj), contract)
            what = type(obj).__name__
        if ok:
            return None
        return f"role {role!r} ({what}) does not provide {contract_info(contract).name}"

    def role_problems(self, requirements: Mapping[str, type]) -> list[str]:
        """Check, before opening anything, that every required role exists and fits.

        This is the station half of the engine's preflight. Roles pointing at children
        that only appear once open can't be checked yet, so they are skipped here and
        checked again by `require` at run time.

        Args:
            requirements: Role name to required contract, collected from tasks.

        Returns:
            One message per problem; empty if everything fits.

        Example:
            >>> from mastif.resources._examples import ExamplePsu
            >>> from mastif.resources.std import Shell
            >>> st = Station.build(StationProfile.from_yaml('''
            ... station: s
            ... resources: {psu: {driver: demo.example-psu,
            ...   config: {transport: {kind: tcp, host: h, port: 1}}}}
            ... '''), Registry([ExamplePsu]))
            >>> for problem in st.role_problems({"psu": Shell, "scope": Shell}):
            ...     print(problem)
            role 'psu' (demo.example-psu) does not provide Shell
            no role 'scope'; known roles: psu
        """
        problems = []
        for role, contract in requirements.items():
            try:
                obj = self.role(role)
            except RoleError as exc:
                if "only once the station is open" in str(exc):
                    continue
                problems.append(str(exc))
                continue
            problem = self._contract_problem(role, contract, obj)
            if problem:
                problems.append(problem)
        return problems

    def identities(self) -> dict[str, Identity]:
        """Return every identity reported while opening, for the run manifest.

        Example:
            ``station.identities()["bench_psu"].serial`` returns ``"A123"``.
        """
        return {n: h.identity for n, h in self.handles.items() if h.identity is not None}

    def open(self, expect: Mapping[str, Mapping[str, object]] | None = None) -> None:
        """Open, identify and health-check every resource; see `ResourceManager.open_all`.

        Example:
            ``station.open(expect={"dut": {"serial": scanned_serial}})``
        """
        self.manager.open_all(expect)

    def safe_state(self) -> dict[str, Exception]:
        """Make every open resource safe; see `ResourceManager.safe_state_all`.

        Example:
            ``failures = station.safe_state()``
        """
        return self.manager.safe_state_all()

    def close(self) -> None:
        """Close every open resource in reverse order; see `ResourceManager.close_all`.

        Example:
            ``station.close()``
        """
        self.manager.close_all()

    def __enter__(self) -> Self:
        """Open the station for a ``with`` block.

        Example:
            ``with Station.build(profile, registry) as st: ...``
        """
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Make everything safe, then close, even when the block raised.

        Example:
            Runs when the ``with`` block ends.
        """
        try:
            self.safe_state()
        finally:
            self.close()
