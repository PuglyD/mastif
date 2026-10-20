"""The kernel: the small, pure vocabulary that every mastif layer shares.

Why "kernel":
    The name comes from the "shared kernel" idea in domain-driven design: a deliberately
    small model that every part of a system agrees on and depends on. It plays the
    same role as the kernel of a seed, the core everything else grows from. It is not
    an operating-system kernel and has nothing to do with Jupyter.

What it contains:
    - `units`: quantities with units (``12 * V``).
    - `limits`: acceptance ranges and the pure `evaluate` function.
    - `verdict`: the `Verdict` enum and `aggregate`.
    - `results`: `Measurement`, `Check` and `Table`, which compute their own verdicts.
    - `ids`: run ids, slot ids and plan positions.
    - `errors`: the root of the `MastifError` hierarchy.

Rules:
    The kernel is pure: no I/O, no threads, no hardware, no imports from other mastif
    layers. Every other layer (resources, station, engine, API) imports from it, and the
    import-linter contract in ``pyproject.toml`` enforces that direction.

Example:
    >>> from mastif.kernel import Limits, Measurement, Verdict
    >>> from mastif.kernel.units import V
    >>> Measurement("rail_5v", 5.02 * V, Limits.between(4.75 * V, 5.25 * V)).verdict
    <Verdict.PASS: 'pass'>
"""

from mastif.kernel.errors import LimitsError, MastifError, UnitError
from mastif.kernel.ids import DEFAULT_SLOT, Position, RunId, SlotId, new_run_id
from mastif.kernel.limits import IndexedLimits, Limits, Range, evaluate
from mastif.kernel.results import Check, Measurement, Result, Table
from mastif.kernel.units import Quantity, Unit, as_quantity, convert, convertible
from mastif.kernel.verdict import Verdict, aggregate

__all__ = [
    "DEFAULT_SLOT",
    "Range",
    "Check",
    "IndexedLimits",
    "Limits",
    "LimitsError",
    "MastifError",
    "Measurement",
    "Position",
    "Quantity",
    "Result",
    "RunId",
    "SlotId",
    "Table",
    "Unit",
    "UnitError",
    "Verdict",
    "aggregate",
    "as_quantity",
    "convert",
    "convertible",
    "evaluate",
    "new_run_id",
]
