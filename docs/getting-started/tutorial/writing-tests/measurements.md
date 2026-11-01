# Measurements and units

Our test measures a current, compares it against a limit and records the answer. Before
we get to limits, let's look closely at the number itself. It's the thing the entire
system exists to produce, so it deserves a chapter.

!!! success "Works today"
    Everything on this page runs against the current code, with no hardware.

## The problem with a bare number

Suppose a driver hands you this:

```python title="the value we want to avoid"
reading = 0.18
```

What does it mean? It could be 0.18 amperes. It could be 0.18 volts, or milliamperes, if
the instrument happened to be set to a different range. The only way to find out is to read
the driver, and hope that the person who wrote the next layer did the same.

Now imagine that value travelling through a system. A driver returns amperes, a helper
assumes milliamperes, and a limit was written in amperes because the datasheet was. Each
piece looks correct on its own. The comparison `0.18 < 250` is true, and your test passes
every board you ever build, including the ones drawing 200 amperes.

This is a nasty kind of bug, because nothing crashes. A factor of a thousand doesn't raise
an exception, and it produces a green report.

So the principle is:

> **A physical value and its unit travel together, from the driver that reads it to the
> record that stores it.** They separate only at a boundary that genuinely requires a bare
> number, such as a command being sent to an instrument.

## Quantities

In mastif, that pairing is called a `Quantity`. You make one by multiplying a number by a
unit:

```python
from mastif.kernel.units import A, V, mA

current = 0.18 * A
print(current)              # 0.18 A
print(current.to("mA"))     # 180 mA
print(current.magnitude("mA"))  # 180.0
```

There are two ways to change units, and they have different purposes. `.to()` gives you
another `Quantity`, still safely carrying its unit. `.magnitude()` gives you a bare `float`
in the unit you name. That's your way out of the system, and notice that it can't be used
without saying which unit you mean.

Because a quantity knows its unit, comparison works across scales:

```python
from mastif.kernel.units import A, mA

print(300 * mA < 1 * A)  # True: converted before comparing
```

And here's the part that catches the bug from earlier:

```python title="this raises"
from mastif.kernel.errors import UnitError
from mastif.kernel.units import A, V

try:
    5 * V < 1 * A
except UnitError as error:
    print(error)  # cannot convert 'A' to 'V'
```

Volts and amperes can't be compared. This isn't a wrong answer, it's no answer, and the
error appears at the line with the mistake, while you're writing the test, rather than as
a mysterious pass on the production floor months later.

### Levels and gains

If you work with RF, you'll appreciate that the same care extends to decibels. A level in
dBm plus a gain in dB is a meaningful sum. Two levels in dBm added together are not, even
though the arithmetic would happily produce a number:

```python
from mastif.kernel.errors import UnitError
from mastif.kernel.units import dB, dBm

print(10 * dBm + 3 * dB)  # 13 dBm

try:
    10 * dBm + 3 * dBm
except UnitError as error:
    print(error)  # cannot add 'dBm' and 'dBm'
```

### What about a unit mastif doesn't know?

Your organisation will have its own. You don't need to register them first:

```python
from mastif.kernel.units import Unit

pressure = 1 * Unit("psi")
print(pressure)  # 1 psi
```

An unknown unit works, but it converts only to itself, since mastif would rather refuse
than guess: asking for `.to("bar")` raises a `UnitError`.

!!! info "Technical details"
    You might wonder why we wrote our own unit system instead of using
    [pint](https://pint.readthedocs.io/). The short version is that `mastif.kernel` must be
    small and pure, its values must serialise cleanly to JSON so that they can later cross
    a process boundary, and a test system needs its dB semantics to be strict and exact.
    [ADR-0003](../../../adr/0003-units.md) has the full comparison.

## From a quantity to a measurement

A quantity is a value in memory. A **measurement** is a claim about the world: this thing
had this value, and this is what was acceptable. It's a named record, and it's the basic
unit of evidence in mastif.

```python
from mastif.kernel.limits import Limits
from mastif.kernel.results import Measurement
from mastif.kernel.units import mA

result = Measurement("idle_current", 180 * mA, Limits.at_most(250 * mA))

print(result.name)     # idle_current
print(result.value)    # 180.0
print(result.unit)     # mA
print(result.verdict)  # pass
```

Here's what to notice. We gave it a name, a value and a limit. We did not give it a verdict.
**The verdict is computed**, and there's no parameter that would let you pass one in. It
isn't possible to create a `Measurement` that says 300 mA against a 250 mA limit and also
says it passed. Whatever else might be wrong with a report from this system, the verdict
can't disagree with the numbers beside it.

A measurement can't be edited after the fact, either. It's frozen, so assigning to
`result.value` raises an error. The chapter on [results](../first-results/results.md) shows how far this
guarantee reaches.

### The unit check happens here too

Measurements won't accept nonsense. Say we measured the wrong thing:

```python title="this raises"
from mastif.kernel.errors import UnitError
from mastif.kernel.limits import Limits
from mastif.kernel.results import Measurement
from mastif.kernel.units import V, mA

try:
    Measurement("idle_current", 5 * V, Limits.at_most(250 * mA))
except UnitError as error:
    print(error)  # cannot convert 'V' to 'mA'
```

That's a bug in the test, and it's reported as one. It isn't a FAIL, because nothing has
been learned about the board.

## Putting it together

Here's a small but complete program. It's the one you ran during installation:

```python title="docs/examples/first_measurement.py"
--8<-- "examples/first_measurement.py"
```

<!-- termynal: {title: "Real transcript · first_measurement.py"} -->
```console
$ uv run python docs/examples/first_measurement.py
idle_current: 180 mA -> PASS
idle_current: 300 mA -> FAIL
```

## A missing reading is not a zero

There's one more situation to think about before we move on, and it's a principle that
comes up again and again. Suppose the instrument doesn't answer. What should the driver
return?

It might be tempting to return `0 * mA`, so that the program keeps going. But look at what
that does: the reading becomes 0 mA, which is comfortably under 250 mA, so the test passes.
**A broken cable would produce a green result.**

So a driver never invents a value. If it can't get a reading, it raises an exception,
`TransportTimeout` for example. There's simply no measurement, and the run reports an ERROR.
We'll follow that exception all the way up in [Failed checks and execution
errors](failures.md).

## What units can't tell you

Units protect you from a specific class of mistake, and it's worth being precise about
where that protection ends.

```text
180 mA at the supply's output terminals
180 mA at the board's input connector
```

Those have the same unit, and they might not be the same current. Wiring, instrument
accuracy, calibration and when you took the reading are all physics that a type system
can't see. A `Quantity` makes sure that you and the computer agree on what the number *says*.
Whether it's the right number is still your job as an engineer, which is why tasks have
`setup` hooks and why you'll read about [settling time](../deploying/hardware.md) soon.

## Recap

- A `Quantity` is a value and its unit, travelling together. `.to()` stays safe, and
  `.magnitude("mA")` is the deliberate exit to a bare number.
- Mismatched dimensions raise `UnitError` at the point of the mistake.
- A `Measurement` is a named, frozen record, and it computes its own verdict.
- A driver that can't read a value raises an exception. It never makes up a number.

We've been using `Limits.at_most` without really explaining it. Let's fix that next.

**Next:** [Limits, checks, and verdicts](limits.md)
