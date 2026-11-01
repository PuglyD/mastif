# Limits, checks, and verdicts

In the last chapter we saw that a measurement judges itself. Now let's look at how it does
that, and what the answer means. This is where a number turns into a decision, so it's
worth being careful about what that decision can and can't say.

!!! success "Works today"
    Everything on this page runs against the current code, with no hardware.

## A limit is a statement of a requirement

Our requirement is "no more than 250 mA while idle". That's easy to write as `current <=
250`, and it's tempting to write it exactly that way, in an `if` statement, inside a test.
But then the requirement exists only as behaviour. It can't be displayed on a report, or
stored with the result, or compared with last year's limit. A year from now, someone reading
a saved `FAIL` will have no way of knowing what the limit was on the day.

So a limit in mastif is an object, and it's stored alongside the value it judged:

```python
from mastif.kernel.limits import Limits, evaluate
from mastif.kernel.units import V, mA

upper = Limits.at_most(250 * mA)
print(evaluate(180 * mA, upper))   # pass
print(evaluate(300 * mA, upper))   # fail

window = Limits.between(4.75 * V, 5.25 * V)
print(evaluate(5 * V, window))     # pass

floor = Limits.at_least(4 * V)
print(evaluate(3.9 * V, floor))    # fail
```

Earlier we asked you to predict what happens with 250 mA and 251 mA. Bounds are inclusive,
so 250 mA passes and 251 mA fails:

```python
from mastif.kernel.limits import Limits, evaluate
from mastif.kernel.units import mA

upper = Limits.at_most(250 * mA)
print(evaluate(250 * mA, upper))  # pass
print(evaluate(251 * mA, upper))  # fail
```

A limit converts before it compares, so you never need to line up units yourself:

```python
from mastif.kernel.limits import Limits, evaluate
from mastif.kernel.units import A, mA

print(evaluate(0.2 * A, Limits.at_most(250 * mA)))  # pass: 200 mA
```

## Warnings: passing, but keep an eye on it

Often the interesting information isn't whether a unit passed, but how close it came. Say a
rail must stay between 4.75 V and 5.25 V, but anything beyond 4.9 to 5.1 V suggests
something is drifting. The unit is still good, and you'd still like to know.

mastif handles this with a *warning band*. Take care with the direction here, as it's easy
to get backwards. The passing range is the good zone, and the warning range is a wider one
around it. Anything inside the warning range but outside the passing range is a WARN, and
anything outside both is a FAIL:

```python
from mastif.kernel.limits import Limits, evaluate
from mastif.kernel.units import V

rail = Limits.between(4.75 * V, 5.25 * V, warn_low=4.5 * V, warn_high=5.5 * V)

print(evaluate(5.0 * V, rail))  # pass
print(evaluate(5.4 * V, rail))  # warn: outside passing, inside warning
print(evaluate(5.6 * V, rail))  # fail: outside both
```

## Different limits per channel

Real products often have a table of limits: channel 1 must be near 10 dBm, and channel 2
near 12 dBm. Rather than writing an `if` per channel, you can index them. Indexed limits are
used through a `Table`, which we'll meet properly in a moment, with one column naming the
channel:

```python
from mastif.kernel.limits import IndexedLimits, Limits
from mastif.kernel.results import Table
from mastif.kernel.units import dBm

power = Table(
    name="output_power",
    columns=("channel", "power"),
    index="channel",
    units={"power": "dBm"},
    limits={
        "power": IndexedLimits(
            by_index={
                1: Limits.between(9 * dBm, 11 * dBm),
                2: Limits.between(11 * dBm, 13 * dBm),
            }
        )
    },
    rows=((1, 10.0), (2, 10.0)),
)
print(power.row_verdicts[0])  # pass
print(power.row_verdicts[1])  # fail
```

Both channels read 10 dBm, which is fine for channel 1 and too low for channel 2. An index that
isn't listed is an error unless you provide a default, because a channel with
no limit is more likely a mistake in the specification than an instruction to accept
anything.

## Checks: requirements that aren't numbers

Not everything has a magnitude. Did the board report idle mode? Is the firmware version the
right one? For these, there's `Check`:

```python
from mastif.kernel.results import Check

good = Check(name="idle_mode", passed=True, detail="board reports idle")
bad = Check(name="idle_mode", passed=False, detail="expected idle, received active")

print(good.verdict)  # pass
print(bad.verdict)   # fail
```

Take a look at `detail`. Write it as if you're leaving a note for the person who'll be
reading this report at 2 a.m. "expected idle, received active" gets them moving. "bad mode"
doesn't.

## Tables: judging a whole sweep

Say that instead of one reading, you measured the current at three supply voltages. You
could record three measurements, but they really belong together. A `Table` keeps them in
one place while still judging every cell:

```python
from mastif.kernel.limits import Limits
from mastif.kernel.results import Table
from mastif.kernel.units import mA

sweep = Table(
    name="idle_vs_supply",
    columns=("voltage_V", "current"),
    units={"current": "mA"},
    limits={"current": Limits.at_most(250 * mA)},
    rows=((4.75, 171.0), (5.0, 180.0), (5.25, 263.0)),
)

print(sweep.row_verdicts[2])  # fail
print(sweep.verdict)          # fail: the worst row wins
```

Only the columns listed in `limits` get judged. `voltage_V` here is the coordinate, and it's
carried along for context. If a judged cell is missing or isn't a number, it's a FAIL,
because an absent reading must not quietly pass.

## Six verdicts

We've seen pass, warn and fail. There are six in all, and the reason there are so many is
that they answer genuinely different questions.

| Verdict | What it tells you | What you do about it |
|---|---|---|
| **PASS** | A requirement was checked and met | Nothing |
| **WARN** | It was met, but inside your warning band | Watch the trend |
| **FAIL** | A valid observation did not meet the requirement | Investigate the *unit* |
| **ERROR** | The test could not produce the evidence | Investigate the *test or bench*, then retest |
| **SKIPPED** | The work wasn't performed | See the stated reason |
| **ABORTED** | The work was started and deliberately stopped | Decide whether to run it again |

The line to dwell on is the one between FAIL and ERROR. A FAIL means you learned something
bad about the unit. An ERROR means you learned nothing about it at all. We'll spend a [whole
chapter](failures.md) on why those can't be allowed to blur together.

## Rolling up to one answer

A run produces many results, and someone will want one word at the top. `aggregate` takes
the worst:

```python
from mastif.kernel.verdict import Verdict, aggregate

print(aggregate([Verdict.PASS, Verdict.WARN]))   # warn
print(aggregate([Verdict.PASS, Verdict.FAIL]))   # fail
print(aggregate([Verdict.FAIL, Verdict.ERROR]))  # error
print(aggregate([]))                             # skipped
```

Two of these are decisions worth pointing out.

**ERROR outranks FAIL.** If some of a run's evidence is missing, you can't call it a clean
FAIL, because you don't know what the unmeasured part would have said.

**An empty list is SKIPPED, not PASS.** This one matters more than it looks. If you ran
nothing, you verified nothing. A framework that reports "all zero tests passed" in green has
told you something false, and [ADR-0005](../../../adr/0005-verdicts-and-aggregation.md) explains
why we refuse to.

!!! warning "A measurement without limits passes"
    `Measurement("idle_current", 180 * mA)`, with no limits, has a verdict of PASS. It's
    useful to log a value purely for information, and nothing has failed. But it also means
    that a green verdict doesn't by itself prove a limit was applied. Have a look at the
    `limits` field when it matters, and treat a missing limit on a safety-relevant
    measurement as a review comment.

## Recap

- A **limit** is a stored object, not an `if` statement, so the requirement survives
  alongside the evidence.
- **Warning bands** flag a marginal unit without failing it.
- **Checks** cover requirements that aren't numbers, and **tables** keep a sweep together
  while judging every cell.
- **Aggregation** takes the worst verdict, ERROR outranks FAIL, and nothing verified is not
  the same as a pass.

We've seen what happens when a valid reading misses its limit. But what if there's no valid reading at all? That's a different situation, and it deserves its own chapter.

**Next:** [Failed checks and execution errors](failures.md)
