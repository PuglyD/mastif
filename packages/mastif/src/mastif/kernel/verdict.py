"""Verdicts, and how many verdicts combine into one.

Why this exists:
    Every level of a test run needs a single answer: a measurement, a step, a task, a
    loop iteration, the whole run. Operators read it at a glance, and automation (yield
    statistics, MES uploads, stop-on-fail policies) acts on it. Having one enum and one
    combining rule keeps every report, UI and API in agreement.

Where it fits:
    Results (`mastif.kernel.results`) produce verdicts. The engine adds ERROR (an
    unexpected exception), SKIPPED (a task chose not to run, or its inputs were missing)
    and ABORTED (an operator or monitor stopped the run). It then calls `aggregate` at
    every level of the run tree.
"""

from collections.abc import Iterable
from enum import StrEnum


class Verdict(StrEnum):
    """The outcome of a result, step, task, loop iteration or run.

    - ``PASS``: everything judged was within the passing limits.
    - ``WARN``: nothing failed, but something was in a marginal (warning) range.
    - ``FAIL``: the device under test did not meet a limit or a check.
    - ``ERROR``: the test itself could not complete (an exception, a lost instrument).
      This says nothing about the device, so it is kept separate from FAIL.
    - ``SKIPPED``: deliberately not run.
    - ``ABORTED``: stopped early by an operator or a safety monitor.

    Values are lowercase strings, so they read naturally in JSON and YAML.

    Examples:
        >>> Verdict("fail") is Verdict.FAIL
        True
        >>> str(Verdict.WARN)
        'warn'
    """

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"
    ABORTED = "aborted"


_RANK = {
    Verdict.SKIPPED: 0,
    Verdict.PASS: 1,
    Verdict.WARN: 2,
    Verdict.FAIL: 3,
    Verdict.ERROR: 4,
    Verdict.ABORTED: 5,
}


def aggregate(verdicts: Iterable[Verdict]) -> Verdict:
    """Combine child verdicts into their parent's verdict: the worst one wins.

    Precedence is ABORTED > ERROR > FAIL > WARN > PASS > SKIPPED. As a result, skipped
    children don't affect the parent unless every child was skipped, and a single
    failure anywhere fails the whole run.

    This is a pure function, used identically at every level (step, task, loop, run),
    so a parent's verdict can always be recomputed from its children.

    Args:
        verdicts: Child verdicts, in any order.

    Returns:
        The parent verdict; SKIPPED when there are no children (nothing was judged).

    Examples:
        >>> aggregate([Verdict.PASS, Verdict.WARN, Verdict.PASS])
        <Verdict.WARN: 'warn'>
        >>> aggregate([Verdict.PASS, Verdict.SKIPPED])
        <Verdict.PASS: 'pass'>
        >>> aggregate([])
        <Verdict.SKIPPED: 'skipped'>
    """
    return max(verdicts, key=_RANK.__getitem__, default=Verdict.SKIPPED)
