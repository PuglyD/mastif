# Your first measurement

A device must draw at most **250 milliamperes (mA)** while idle. You have a reading.
How do you record both the evidence and the decision?

In this tutorial you will create two measurements from simulated readings and see why
one passes and the other fails. No hardware, driver, or running engine is needed.

## 1. Prepare your environment

You need Python 3.12 or newer, Git, and [uv](https://docs.astral.sh/uv/).
For this development version, work from the source checkout:

```console
git clone https://github.com/PuglyD/mastif.git
cd mastif
uv sync --group docs
```

If you already have the repository, run the last command from its root directory.
The docs dependency group also lets you preview this site with `uv run mkdocs serve`.

## 2. Attach meaning to the number

`180 * mA` creates a quantity: a magnitude together with a unit. Keeping the unit with
the value allows mastif to compare compatible units and reject incompatible ones.

`Limits.at_most(250 * mA)` describes the inclusive upper bound. The acceptance rule
belongs to the test's requirements, not to the instrument driver.

Create `first_measurement.py` in the repository root with this code, or use the
[downloadable example](../examples/first_measurement.py):

```python title="first_measurement.py"
--8<-- "examples/first_measurement.py"
```

The two numbers stand in for instrument readings. The first is below the limit; the
second is above it. [`Measurement`][mastif.kernel.results.Measurement] records each
reading and computes the verdict. You do not supply a separate pass/fail flag.

## 3. Run it

```console
uv run python first_measurement.py
```

The terminal below is a **recorded demonstration** of that command. It does not run
Python in your browser. The complete transcript is visible before playback; motion
is disabled when your system requests reduced motion.

<!-- termynal: {title: "mastif · first measurement"} -->
```console
$ uv run python first_measurement.py
idle_current: 180 mA -> PASS
idle_current: 300 mA -> FAIL
```

You can also run the checked-in example directly:

```console
uv run python docs/examples/first_measurement.py
```

## 4. Understand what the verdict means

**FAIL means the measured value is outside the acceptance limit.** The measurement
itself succeeded. A disconnected instrument is a different situation: there is no
valid reading to evaluate, so a driver should raise an appropriate exception rather
than substitute a number.

Try changing the readings to `250` and `251`. The bound is inclusive, so the first
passes and the second fails.

??? note "What happens with incompatible units?"
    A current limit cannot be applied to a voltage reading. mastif raises
    [`UnitError`][mastif.kernel.errors.UnitError] rather than producing a verdict
    from incompatible quantities. See [Units](../adr/0003-units.md) for the design.

## Where this fits

You have exercised the **kernel**: pure logic with no sockets, device handles, or
background runtime. In a hardware-backed application, a driver supplies the reading;
the same result model evaluates it.

| Learn more | Why it matters |
|---|---|
| [Kernel concepts](kernel.md) | Understand limits, checks, tables, and aggregation |
| [Measurement reference][mastif.kernel.results.Measurement] | Inspect constructor parameters and result fields |
| [Result design](../adr/0006-results.md) | Understand why verdicts are derived from evidence |
| [Resource concepts](resources.md) | Replace simulated input with an instrument capability |

**Next:** [Understand resources](resources.md), or [return to the guided tour](walkthrough.md).
