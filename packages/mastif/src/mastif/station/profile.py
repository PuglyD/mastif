"""The station profile: the facts about one physical test station, as YAML.

Why this exists:
    Two stations running the same tests rarely have identical hardware. One has a
    different supply model, another has its DUT console on a different COM port. The
    profile captures these facts: which resources exist, which driver each uses, where
    each is connected, what identity to expect, and which **role** names tests use to
    reach them. It holds facts only; all control flow stays in Python. Swapping a
    station is therefore a matter of swapping a file.

Where it fits:
    `StationProfile.load` reads and validates the YAML. ``Station.build`` turns it into
    live objects with the `Registry`. Tests never read profiles; they ask for roles.

Example profile::

    station: bench-01
    resources:
      bench_psu:
        driver: acme.psu-x
        config: {transport: {kind: tcp, host: 10.0.0.5, port: 5025}}
        expect: {serial: A123}
      dut:
        driver: demo.widget-board
        channels:
          console: {driver: mastif.line-shell,
                    config: {transport: {kind: serial, port: COM3, baudrate: 115200}, prompt: "# "}}
    roles:
      psu_main: bench_psu
    sim:
      bench_psu: {driver: demo.psu-sim}

``sim:`` replaces whole resource entries when the station is built with ``sim=True``,
so the same profile drives both the real bench and a simulator.
"""

import re
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from mastif.kernel.ids import SlotId
from mastif.station.errors import StationError

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class ChannelEntry(BaseModel):
    """How one DUT channel is connected: a channel driver and its config.

    Attributes:
        driver: Id of a driver providing the channel's contract, e.g. ``mastif.udp``.
        config: That driver's config.

    Examples:
        >>> ChannelEntry(driver="mastif.udp", config={"transport": {"kind": "udp",
        ...     "host": "192.168.1.50", "port": 9000}}).driver
        'mastif.udp'
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    driver: str
    config: dict[str, Any] = Field(default_factory=dict)


class ResourceEntry(BaseModel):
    """One instrument or DUT at the station.

    Attributes:
        driver: Driver id, e.g. ``acme.psu-x``.
        config: The driver's config (validated against its ``Config`` class).
        channels: For DUTs, how each declared channel is connected.
        expect: Identity fields that must match before the resource is used, e.g.
            ``{serial: A123}``. Checked against what the driver's ``identify()`` reports.
        shared: Whether the resource may be shared between DUT slots (reserved for
            multi-DUT stations).
        slot: The DUT slot this resource belongs to, for multi-DUT stations (reserved).

    Examples:
        >>> ResourceEntry(driver="acme.psu-x", expect={"serial": "A123"}).expect
        {'serial': 'A123'}
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    driver: str
    config: dict[str, Any] = Field(default_factory=dict)
    channels: dict[str, ChannelEntry] = Field(default_factory=dict)
    expect: dict[str, str | int | float] = Field(default_factory=dict)
    shared: bool = False
    slot: SlotId | None = None


class StationProfile(BaseModel):
    """A whole station: its resources, role names, and simulator overrides.

    Attributes:
        schema_version: Profile format version; bumped when the format changes shape.
        station: Station name, recorded with every run.
        description: Free text for humans.
        resources: Resources by name, opened in the order listed and closed in reverse.
        roles: Role name to resource name (or ``resource.child``). A resource's own
            name always works as a role too.
        sim: Replacement entries used when building in simulation mode.

    Examples:
        >>> p = StationProfile.from_yaml('''
        ... station: bench-01
        ... resources:
        ...   psu: {driver: acme.psu-x}
        ... roles: {psu_main: psu}
        ... sim:
        ...   psu: {driver: demo.psu-sim}
        ... ''')
        >>> p.target_of("psu_main"), p.entries(sim=True)["psu"].driver
        ('psu', 'demo.psu-sim')
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    station: str
    description: str = ""
    resources: dict[str, ResourceEntry]
    roles: dict[str, str] = Field(default_factory=dict)
    sim: dict[str, ResourceEntry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        """Check names, role targets and sim keys refer to things that exist.

        Resource and role names may not contain dots: a dot means "child of" in role
        targets such as ``positioner.azimuth``.

        Returns:
            The profile.

        Raises:
            StationError: Naming every inconsistency found.

        Examples:
            >>> StationProfile(station="s", resources={}, roles={"psu": "missing"})
            Traceback (most recent call last):
            ...
            mastif.station.errors.StationError: role 'psu' points to unknown resource 'missing'
        """
        problems = []
        for name in [*self.resources, *self.roles]:
            if not _NAME.match(name):
                problems.append(f"invalid name {name!r} (letters, digits, '_' and '-' only)")
        for role, target in self.roles.items():
            root = target.split(".", 1)[0]
            if root not in self.resources:
                problems.append(f"role {role!r} points to unknown resource {root!r}")
        for name in self.sim:
            if name not in self.resources:
                problems.append(f"sim entry {name!r} replaces no resource")
        if problems:
            raise StationError("; ".join(problems))
        return self

    @classmethod
    def from_yaml(cls, text: str, *, source: str = "<string>") -> "StationProfile":
        """Parse and validate a profile from YAML text.

        Args:
            text: The YAML document.
            source: Where it came from, for error messages.

        Returns:
            The profile.

        Raises:
            StationError: If the YAML is malformed or doesn't match the profile format.

        Examples:
            >>> StationProfile.from_yaml("station: s\\nresources: {}").station
            's'
            >>> StationProfile.from_yaml("station: s")
            Traceback (most recent call last):
            ...
            mastif.station.errors.StationError: <string>: invalid station profile:
            resources: Field required
        """
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise StationError(f"{source}: not valid YAML: {exc}") from exc
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            details = "\n".join(
                f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors()
            )
            raise StationError(f"{source}: invalid station profile:\n{details}") from exc

    @classmethod
    def load(cls, path: str | Path) -> "StationProfile":
        """Read and validate a profile file.

        Args:
            path: Path to the YAML file.

        Returns:
            The profile.

        Raises:
            StationError: If the file can't be read or is invalid.

        Examples:
            ``StationProfile.load("stations/bench-01.yaml")``
        """
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise StationError(f"{p}: cannot read station profile: {exc}") from exc
        return cls.from_yaml(text, source=str(p))

    def entries(self, sim: bool = False) -> dict[str, ResourceEntry]:
        """Return the resource entries to build, with sim replacements applied if asked.

        Args:
            sim: Use the ``sim:`` entries where they exist.

        Returns:
            Resource name to entry, in profile order.

        Examples:
            >>> p = StationProfile(station="s",
            ...     resources={"a": ResourceEntry(driver="x.real")},
            ...     sim={"a": ResourceEntry(driver="x.sim")})
            >>> p.entries()["a"].driver, p.entries(sim=True)["a"].driver
            ('x.real', 'x.sim')
        """
        if not sim:
            return dict(self.resources)
        return {name: self.sim.get(name, entry) for name, entry in self.resources.items()}

    def target_of(self, role: str) -> str:
        """Resolve a role name to the resource (or ``resource.child``) it refers to.

        Args:
            role: A role from ``roles:``, or a resource name used directly as a role.

        Returns:
            The target name.

        Examples:
            >>> p = StationProfile(station="s", resources={"psu": ResourceEntry(driver="x.y")},
            ...     roles={"psu_main": "psu"})
            >>> p.target_of("psu_main"), p.target_of("psu")
            ('psu', 'psu')
        """
        return self.roles.get(role, role)
