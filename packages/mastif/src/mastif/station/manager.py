"""Opening, verifying, making safe and closing a station's resources, in the right order.

Why this exists:
    Bringing up a station is where real-world failures concentrate. A supply is
    switched off, the wrong unit is on the bench, a console never shows a prompt. The
    station must never be left half-open: if the third resource fails, the first two
    are closed again. When a run ends or is aborted, every resource must be put into a
    safe state, even if one of them fails to respond. Getting this right once, centrally,
    means no test or driver has to think about it.

What "open" means for one resource, in order:
    1. open its injected I/O (sockets, ports)
    2. open its DUT channels (each one a resource in its own right)
    3. call the driver's ``open()``
    4. ``identify()`` and compare with the profile's ``expect:``, which fails before
       anything else is done to the wrong device
    5. ``health()``; an unhealthy resource is refused
    6. collect ``children()``, e.g. the axes of a positioner controller

Close runs the same steps backwards, for every resource that got anywhere at all, and
continues past errors so nothing is left open.

Where it fits:
    `mastif.station.station.Station` owns a `ResourceManager`. The engine opens the
    station at run start, calls `ResourceManager.safe_state_all` on abort or failure,
    and closes it at run end. Each step is reported as a `ResourceEvent` to an optional
    listener; the engine turns these into run events.
"""

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from mastif.resources.driver import BuiltResource, DriverSpec, call_hook, has_hook, make_safe
from mastif.resources.errors import IdentityMismatch, ResourceError, ResourceFault
from mastif.resources.identity import Health, Identity
from mastif.station.profile import ResourceEntry

type Phase = Literal[
    "opening", "opened", "open_failed", "safe_state", "safe_state_failed", "closed", "close_failed"
]


@dataclass(frozen=True, slots=True)
class ResourceEvent:
    """One lifecycle step of one resource, reported to the station's listener.

    Attributes:
        resource: Resource name (``dut.console`` for a DUT channel).
        phase: What happened.
        detail: Extra information, e.g. the error message or the identity.

    Example:
        >>> ResourceEvent("bench_psu", "opened", "serial=A123")
        ResourceEvent(resource='bench_psu', phase='opened', detail='serial=A123')
    """

    resource: str
    phase: Phase
    detail: str = ""


type Listener = Callable[[ResourceEvent], None]


@dataclass
class ResourceHandle:
    """A built resource plus everything the station learns about it while it is open.

    Attributes:
        name: Resource name from the profile.
        built: The driver instance, its config and its injected I/O.
        entry: The profile entry it was built from.
        channels: For DUTs, the channel resources by channel name.
        children: Sub-resources reported by ``children()`` once open.
        identity: What ``identify()`` reported, once open.
        health: What ``health()`` reported, once open.
        is_open: Whether the resource is fully open.

    Example:
        ``station.resource("bench_psu").identity.serial`` returns ``"A123"`` once the
        station is open.
    """

    name: str
    built: BuiltResource
    entry: ResourceEntry
    channels: dict[str, "ResourceHandle"] = field(default_factory=dict)
    children: dict[str, Any] = field(default_factory=dict)
    identity: Identity | None = None
    health: Health | None = None
    is_open: bool = False
    _driver_opened: bool = False

    @property
    def instance(self) -> Any:
        """The driver or DUT object itself.

        Example:
            ``station.resource("bench_psu").instance.measure_current()``
        """
        return self.built.instance

    @property
    def spec(self) -> DriverSpec:
        """The driver's spec.

        Example:
            ``handle.spec.id`` returns ``"acme.psu-x"``.
        """
        return self.built.spec

    def state_snapshot(self) -> dict[str, Any] | None:
        """Return the resource's live state as plain data, for run snapshots.

        Returns:
            ``state.model_dump()`` for resources declaring ``state=``, else ``None``.

        Example:
            ``station.resource("dut").state_snapshot()`` returns ``{"booted": True}``.
        """
        state = getattr(self.instance, "state", None)
        if self.spec.state_model is not None and state is not None:
            return state.model_dump(mode="json")
        return None


class ResourceManager:
    """Opens, makes safe and closes a set of resource handles, emitting events.

    Example:
        Used through `Station`::

            station.open()           # ResourceManager.open_all
            station.safe_state()     # ResourceManager.safe_state_all
            station.close()          # ResourceManager.close_all
    """

    def __init__(
        self,
        handles: Iterable[ResourceHandle],
        listener: Listener | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Manage the given handles; they are opened in the order given.

        Args:
            handles: Resources in profile order.
            listener: Receives a `ResourceEvent` for every lifecycle step.
            logger: Where lifecycle steps are logged.

        Example:
            ``ResourceManager(station.handles.values(), listener=events.append)``
        """
        self.handles = list(handles)
        self.listener = listener
        self.log = logger or logging.getLogger("mastif.station")
        self._opened: list[ResourceHandle] = []

    def _emit(self, resource: str, phase: Phase, detail: str = "") -> None:
        """Log a lifecycle step and pass it to the listener.

        Listener errors are logged and ignored, so a broken UI can't stop a shutdown.

        Example:
            ``self._emit("bench_psu", "opened")``
        """
        self.log.info("%s: %s %s", resource, phase, detail)
        if self.listener is not None:
            try:
                self.listener(ResourceEvent(resource, phase, detail))
            except Exception:
                self.log.exception("resource event listener failed")

    def open_all(self, expect: Mapping[str, Mapping[str, object]] | None = None) -> None:
        """Open every resource in order; on any failure, close what was opened and re-raise.

        Args:
            expect: Extra identity expectations per resource, merged over the profile's
                ``expect:``. This is how an operator-scanned serial number is checked
                against the DUT that is actually connected.

        Raises:
            ResourceError: From the first resource that failed. Every resource opened
                before it is closed again.

        Example:
            ``manager.open_all(expect={"dut": {"serial": "SN-0042"}})``
        """
        extra = expect or {}
        for handle in self.handles:
            try:
                self._open_one(handle, extra.get(handle.name, {}))
            except BaseException:
                for opened in reversed(self._opened):
                    self._close_one(opened)
                self._opened.clear()
                raise
            self._opened.append(handle)

    def _open_one(self, h: ResourceHandle, extra_expect: Mapping[str, object]) -> None:
        """Open one resource (and its channels), verify it, or undo and re-raise.

        Example:
            Called by `open_all` for each handle in order.
        """
        self._emit(h.name, "opening")
        try:
            for io in h.built.io:
                io.open()
            for ch in h.channels.values():
                self._open_one(ch, {})
            call_hook(h.instance, "open")
            h._driver_opened = True
            self._verify_identity(h, {**h.entry.expect, **extra_expect})
            if has_hook(h.instance, "health"):
                h.health = call_hook(h.instance, "health")
                if h.health is not None and not h.health.ok:
                    raise ResourceFault(f"{h.name}: unhealthy: {h.health.detail or 'no detail'}")
            if has_hook(h.instance, "children"):
                h.children = dict(call_hook(h.instance, "children") or {})
        except BaseException as exc:
            self._emit(h.name, "open_failed", str(exc))
            self._close_one(h, report=False)
            raise
        h.is_open = True
        detail = f"serial={h.identity.serial}" if h.identity and h.identity.serial else ""
        self._emit(h.name, "opened", detail)

    def _verify_identity(self, h: ResourceHandle, expected: Mapping[str, object]) -> None:
        """Ask the resource who it is and compare with what the profile expects.

        Raises:
            IdentityMismatch: If any expected field differs, or there are expectations
                but the driver can't identify itself.

        Example:
            ``expect: {serial: A123}`` against a unit reporting ``B999`` raises.
        """
        if has_hook(h.instance, "identify"):
            h.identity = call_hook(h.instance, "identify")
        if not expected:
            return
        if h.identity is None:
            raise IdentityMismatch(f"{h.name}: expect: is set but the driver can't identify()")
        wrong = h.identity.mismatches(expected)
        if wrong:
            parts = ", ".join(f"{k} is {a!r}, expected {e!r}" for k, (e, a) in wrong.items())
            raise IdentityMismatch(f"{h.name}: {parts}")

    def _close_one(self, h: ResourceHandle, report: bool = True) -> list[Exception]:
        """Close one resource in reverse order of opening, continuing past errors.

        Args:
            h: The resource.
            report: Emit a ``closed`` / ``close_failed`` event.

        Returns:
            The errors raised along the way (closing never stops early).

        Example:
            ``errors = self._close_one(handle)``
        """
        errors: list[Exception] = []
        if h._driver_opened:
            try:
                call_hook(h.instance, "close")
            except Exception as exc:
                errors.append(exc)
            h._driver_opened = False
        for ch in reversed(list(h.channels.values())):
            errors.extend(self._close_one(ch, report=False))
        for io in reversed(h.built.io):
            try:
                io.close()
            except Exception as exc:
                errors.append(exc)
        h.is_open = False
        h.children = {}
        if report:
            if errors:
                self._emit(h.name, "close_failed", "; ".join(map(str, errors)))
            else:
                self._emit(h.name, "closed")
        return errors

    def close_all(self) -> None:
        """Close every open resource in reverse order, even if some fail to close.

        Raises:
            ResourceError: After everything has been attempted, if anything failed to
                close; the first error is chained as the cause.

        Example:
            ``manager.close_all()`` at the end of a run.
        """
        errors: list[Exception] = []
        for h in reversed(self._opened):
            errors.extend(self._close_one(h))
        self._opened.clear()
        if errors:
            raise ResourceError(f"{len(errors)} error(s) while closing: {errors[0]}") from errors[0]

    def safe_state_all(self) -> dict[str, Exception]:
        """Put every open resource into its safe state, in reverse order, never stopping early.

        A failure on one resource must not prevent the others from being made safe, so
        errors are collected and returned instead of raised.

        Returns:
            Resource name to the error it raised; empty if all succeeded.

        Example:
            ``failures = manager.safe_state_all()`` when an operator presses abort.
        """
        failures: dict[str, Exception] = {}
        for h in reversed(self._opened):
            try:
                ran = make_safe(h.built)
            except Exception as exc:
                failures[h.name] = exc
                self._emit(h.name, "safe_state_failed", str(exc))
                continue
            self._emit(h.name, "safe_state", "" if ran else "no safe-state action")
        return failures

    @property
    def opened(self) -> list[ResourceHandle]:
        """The resources currently open, in opening order.

        Example:
            ``[h.name for h in manager.opened]`` returns ``["bench_psu", "dut"]``.
        """
        return list(self._opened)
