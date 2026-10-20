"""Identifiers that name runs, test slots and positions inside a plan.

Why this exists:
    Every event, snapshot and report must say exactly which run it belongs to, which
    DUT slot produced it, and where in the plan's loops it happened. These identifiers
    are the shared keys for that. They are defined here, at the bottom of the stack, so
    the engine, the stores and the API all use the same ones.

Where it fits:
    - `RunId`: names a run folder and appears in every event. Created with `new_run_id`.
    - `SlotId`: names a DUT position on a multi-DUT fixture. mastif runs one slot
      (`DEFAULT_SLOT`) today, but carries the id everywhere so that parallel slots can be
      added later without changing data formats.
    - `Position`: the current value of every loop in a plan, e.g. firmware profile
      ``"std"`` and channel ``2``. The engine uses positions to decide which loop
      transitions to run, and to resume a run at the right place.
"""

import secrets
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

type RunId = str
type SlotId = str
type LoopValue = str | int | float | bool

DEFAULT_SLOT: SlotId = "0"


def new_run_id(now: datetime | None = None) -> RunId:
    """Create a unique run id that sorts by start time, e.g. ``20261020T101500Z-3fa9c2``.

    The timestamp prefix makes run folders list chronologically. The random suffix keeps
    two runs started in the same second distinct.

    Args:
        now: Timestamp to use; defaults to the current UTC time. Pass one in tests to
            get a predictable prefix.

    Returns:
        The run id.

    Example:
        >>> rid = new_run_id(datetime(2026, 10, 20, 10, 15, tzinfo=UTC))
        >>> rid.startswith("20261020T101500Z-"), len(rid)
        (True, 23)
    """
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(3)}"


class Position(BaseModel):
    """Where in a plan's loops a task runs: an ordered list of loop values.

    A plan can nest loops, for example "for each firmware profile, for each channel, run
    these tasks". A position records one point in that nesting, outermost loop first.
    Order matters, because the engine compares consecutive positions to decide which
    loops to exit and enter. Positions are immutable and hashable, so they can be used
    as dictionary keys (for example, context values scoped to a position).

    Attributes:
        loops: ``(loop name, value)`` pairs, outermost loop first. Empty for tasks that
            run outside any loop (the root).

    Example:
        >>> p = Position.of(profile="std", channel=2)
        >>> p.key
        'profile=std/channel=2'
        >>> p.get("channel")
        2
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    loops: tuple[tuple[str, LoopValue], ...] = ()

    @classmethod
    def of(cls, **values: LoopValue) -> "Position":
        """Build a position from keyword arguments, keeping their order.

        Args:
            **values: Loop name to value, outermost first.

        Returns:
            The position.

        Example:
            >>> Position.of(temperature=25, channel=1).names
            ('temperature', 'channel')
        """
        return cls(loops=tuple(values.items()))

    def get(self, name: str) -> LoopValue:
        """Return the current value of one loop.

        Tasks use this through their context, e.g. to read the channel being tested.

        Args:
            name: Loop name.

        Returns:
            The loop's value.

        Raises:
            KeyError: If the loop is not part of this position.

        Example:
            >>> Position.of(channel=3).get("channel")
            3
        """
        for loop, value in self.loops:
            if loop == name:
                return value
        raise KeyError(name)

    def as_dict(self) -> dict[str, Any]:
        """Return the loop values as a dict (outermost first), for display or templating.

        Example:
            >>> Position.of(profile="std", channel=1).as_dict()
            {'profile': 'std', 'channel': 1}
        """
        return dict(self.loops)

    @property
    def names(self) -> tuple[str, ...]:
        """Loop names, outermost first.

        Example:
            >>> Position.of(a=1, b=2).names
            ('a', 'b')
        """
        return tuple(name for name, _ in self.loops)

    @property
    def key(self) -> str:
        """A stable text form, used in item ids, logs and file names; empty for the root.

        Example:
            >>> Position.of(profile="std", channel=1).key
            'profile=std/channel=1'
            >>> Position().key
            ''
        """
        return "/".join(f"{name}={value}" for name, value in self.loops)

    def __str__(self) -> str:
        """Render for humans: the key, or ``"<root>"`` outside any loop.

        Example:
            >>> str(Position())
            '<root>'
        """
        return self.key or "<root>"
