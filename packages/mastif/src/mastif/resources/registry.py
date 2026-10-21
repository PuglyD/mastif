"""The registry: how mastif finds the drivers an organisation has installed.

Why this exists:
    A station profile says ``driver: acme.psu-x``. Something has to map that id to a
    class, without mastif knowing anything about the org's packages and without
    importing modules having side effects. Global registration-at-import makes the
    set of available drivers depend on which modules happened to be imported. That
    leads to "works on my machine" failures and to tests that leak into each other.

    The registry is an explicit, ordinary object. It is built either from a list of
    classes (in tests) or by asking Python's packaging metadata which installed
    packages advertise drivers (at a station).

Where it fits:
    An org SDK advertises its driver modules in its ``pyproject.toml``::

        [project.entry-points."mastif.drivers"]
        acme = "acme_sdk.drivers"

    ``Registry.discover()`` imports those modules and collects every class decorated
    with ``@driver`` or ``@dut``. ``Station.build`` then looks up each profile entry with
    `Registry.get`. mastif's own built-in channel drivers (``mastif.udp``,
    ``mastif.line-shell``) are always included.
"""

import importlib.metadata
from collections.abc import Iterable
from types import ModuleType

from mastif.resources.driver import DriverSpec, is_driver, spec_of
from mastif.resources.errors import DriverDefinitionError, DriverNotFound

ENTRY_POINT_GROUP = "mastif.drivers"


def _classes_in(obj: object) -> list[type]:
    """Return the decorated driver classes in a module, iterable, or single class.

    Example:
        ``_classes_in(acme_sdk.drivers)`` returns every ``@driver`` class defined there.
    """
    if isinstance(obj, type) and is_driver(obj):
        return [obj]
    if isinstance(obj, ModuleType):
        return [v for v in vars(obj).values() if isinstance(v, type) and is_driver(v)]
    if isinstance(obj, Iterable) and not isinstance(obj, str | bytes):
        return [c for item in obj for c in _classes_in(item)]
    return []


class Registry:
    """A lookup table from driver id to `DriverSpec`.

    Example:
        >>> from mastif.resources._examples import ExamplePsu
        >>> reg = Registry([ExamplePsu])
        >>> reg.get("demo.example-psu").cls is ExamplePsu
        True
        >>> "demo.example-psu" in reg
        True
    """

    def __init__(self, classes: Iterable[object] = (), *, builtin: bool = True) -> None:
        """Create a registry from driver classes.

        Args:
            classes: Classes decorated with ``@driver`` or ``@dut``, or modules containing them.
            builtin: Also include mastif's built-in channel drivers.

        Raises:
            DriverDefinitionError: If two different classes share an id.

        Example:
            >>> Registry(builtin=False).ids()
            []
        """
        self._specs: dict[str, DriverSpec] = {}
        if builtin:
            from mastif.resources.channels import BUILTIN_DRIVERS  # noqa: PLC0415

            self.add(*BUILTIN_DRIVERS)
        self.add(*classes)

    @classmethod
    def discover(cls, group: str = ENTRY_POINT_GROUP, *, builtin: bool = True) -> "Registry":
        """Build a registry from every installed package advertising drivers.

        Each entry point may name a module, a class, or a list of classes. Discovery
        imports only those modules, and only when this method is called.

        Args:
            group: Entry-point group to read.
            builtin: Also include mastif's built-in channel drivers.

        Returns:
            The registry.

        Raises:
            DriverDefinitionError: If an advertised module fails to import, or two
                drivers share an id.

        Example:
            >>> "mastif.udp" in Registry.discover()
            True
        """
        found: list[type] = []
        for ep in importlib.metadata.entry_points(group=group):
            try:
                loaded = ep.load()
            except Exception as exc:
                raise DriverDefinitionError(
                    f"entry point {ep.name!r} ({ep.value}) failed to load: {exc}"
                ) from exc
            found.extend(_classes_in(loaded))
        return cls(found, builtin=builtin)

    def add(self, *items: object) -> None:
        """Add driver classes, or modules and lists containing them.

        Adding the same class twice is harmless. Two *different* classes with one id are
        an error, because a profile entry would then be ambiguous.

        Args:
            *items: Classes, modules or iterables of classes.

        Raises:
            DriverDefinitionError: On a conflicting id.

        Example:
            >>> from mastif.resources._examples import ExamplePsu
            >>> reg = Registry(builtin=False)
            >>> reg.add(ExamplePsu, ExamplePsu)
            >>> reg.ids()
            ['demo.example-psu']
        """
        for item in items:
            for driver_cls in _classes_in(item):
                spec = spec_of(driver_cls)
                existing = self._specs.get(spec.id)
                if existing is not None and existing.cls is not spec.cls:
                    raise DriverDefinitionError(
                        f"driver id {spec.id!r} is used by both "
                        f"{existing.cls.__module__}.{existing.cls.__qualname__} and "
                        f"{spec.cls.__module__}.{spec.cls.__qualname__}"
                    )
                self._specs[spec.id] = spec

    def get(self, driver_id: str) -> DriverSpec:
        """Return the spec for a driver id.

        Args:
            driver_id: The id from a station profile.

        Returns:
            The spec.

        Raises:
            DriverNotFound: Listing the known ids, which helps spot a typo.

        Example:
            >>> Registry(builtin=False).get("acme.nope")
            Traceback (most recent call last):
            ...
            mastif.resources.errors.DriverNotFound: no driver 'acme.nope'; known: (none)
        """
        try:
            return self._specs[driver_id]
        except KeyError:
            known = ", ".join(sorted(self._specs)) or "(none)"
            raise DriverNotFound(f"no driver {driver_id!r}; known: {known}") from None

    def ids(self) -> list[str]:
        """Return all known driver ids, sorted.

        Example:
            >>> Registry().ids()
            ['mastif.line-shell', 'mastif.udp']
        """
        return sorted(self._specs)

    def __contains__(self, driver_id: object) -> bool:
        """Tell whether a driver id is known.

        Example:
            >>> "mastif.udp" in Registry()
            True
        """
        return driver_id in self._specs
