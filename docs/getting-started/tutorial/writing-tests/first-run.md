# Your first test run

Welcome to the tutorial. Over the next few sections we're going to build one test
system, and it starts with a question simple enough to fit in a sentence:

> Does this widget board draw no more than 250 mA while idle?

The widget board is fictional, and so is the bench it sits on. That suits us, because
nothing in this tutorial needs real hardware until we choose to add it. The question
itself, though, is exactly the sort that real test systems ask thousands of times a day.

In this chapter we'll go straight to the end. We'll look at the complete test as you would
write it, watch it run, and then spend the rest of the tutorial understanding how each part
works. That's the order we think is most useful, since it's much easier to care about a
mechanism once you've seen what it's for.

!!! example "Design preview"
    The `Task` class and the `mastif` command belong to the engine, which we are designing
    in these pages, so this code won't run yet. The quantities, limits, results and
    contracts it uses are all implemented. At the end of this chapter you'll run the same
    measurement for real, using the layers that exist today.

## The test

A test in mastif is called a **task**. Here's ours, complete:

```python title="demo_tests/idle_current.py — preview"
from mastif.api import Task, TaskConfig, requires
from mastif.kernel.limits import Limits
from mastif.kernel.units import Quantity, V, mA
from mastif.resources.std import PowerSupply


class IdleCurrentConfig(TaskConfig):
    voltage: Quantity = 5 * V
    max_current: Quantity = 250 * mA


class IdleCurrent(Task[IdleCurrentConfig]):
    """Check that the board stays within its idle current budget."""

    id = "idle_current"

    supply: PowerSupply = requires("supply")

    def setup(self, ctx):
        self.supply.set_voltage(self.config.voltage)
        self.supply.set_current_limit(500 * mA)
        self.supply.output(True)

    def run(self, ctx):
        ctx.measure(
            "idle_current",
            self.supply.measure_current(),
            Limits.at_most(self.config.max_current),
        )

    def teardown(self, ctx):
        self.supply.output(False)
```

Let's read it from top to bottom, because almost every decision in the framework is
visible in these thirty lines.

### The configuration

`IdleCurrentConfig` lists the values that someone might reasonably want to change without
touching the test's logic: the supply voltage and the limit. It's a validated model, so a
plan that tries to set `max_current: banana` is rejected before any hardware is powered.

Notice the type is `Quantity`, not `float`. It would be perfectly possible to write
`max_current_ma: float = 250`, and to rely on everyone remembering what that means. We'll
see in [Measurements and units](measurements.md) why we don't.

### The requirement

```python title="excerpt — preview"
supply: PowerSupply = requires("supply")
```

This one line carries most of the design. It says: *this test needs something that behaves
like a `PowerSupply`, and on any given bench it will be whichever resource has the role
`supply`.*

There's no address here, no model number, no import of a driver. The test states what it
needs, and leaves *which instrument* to the bench. And because the requirement is a
declaration on the class, rather than a call buried inside a method, the engine can read
it **before running anything**, and tell you this bench can't run this test before a single
output has been switched on.

### The structure

A task is a class with named hooks, because a test on real hardware has a shape that
repeats: prepare the conditions, make the observation, and put things back. Those aren't
just three blocks of code. They have different rules:

| Hook | Its job | If it raises |
|---|---|---|
| `setup` | Establish the conditions for this test | `run` is skipped, and the task is an ERROR |
| `run` | Observe the device and record results | The task is an ERROR |
| `teardown` | Undo what `setup` did | Reported, and it can't hide an earlier failure |

The important property is the last column of the last row. **`teardown` runs whatever
happened in `setup` and `run`**, so `output(False)` doesn't get skipped by the exception
that killed our script back in [What mastif wants to solve](../../intro/problem.md). The framework guarantees that the
attempt is made, and every test gets this for free, instead of each author remembering to
write a careful `try/finally`.

### The measurement

```python title="excerpt — preview"
ctx.measure(
    "idle_current",
    self.supply.measure_current(),
    Limits.at_most(self.config.max_current),
)
```

`ctx` is the task's connection to the engine. Here's the thing to notice: we hand over a
*value* and a *limit*. We never say whether the test passed. The result works that out for
itself, and the engine records it along with where in the run it happened.

There's also no `assert`, and nothing that stops the task when the value is out of limits.
A measurement that fails is a perfectly successful observation: the task keeps going, and
the verdict reflects what it found.

## The station

The task asked for a role called `supply`. Somebody has to say what that is on this bench,
and that's the job of a **station profile**:

```yaml title="stations/demo.yaml"
station: demo-bench
resources:
  bench_supply:
    driver: demo.learn-supply
    config: {current_ma: 180}
    expect: {serial: SIM-001}
roles:
  supply: bench_supply
```

This bench has one resource, a simulated supply configured to report 180 mA. The role
`supply` maps to it. On a real bench the same two lines of `roles` would point at a real
instrument, and the task above wouldn't change at all.

## Run it

First, ask mastif to check that all of this fits together. This step touches no hardware:

<!-- termynal: {title: "Mock of the intended experience · validate"} -->
```console
$ mastif validate demo_tests.idle_current --station stations/demo.yaml
Task idle_current
  ✓ config is valid
  ✓ role 'supply' -> bench_supply (demo.learn-supply) provides PowerSupply
Nothing was opened. Ready to run.
```

Now run it:

<!-- termynal: {title: "Mock of the intended experience · a passing run"} -->
```console
$ mastif task demo_tests.idle_current --station stations/demo.yaml
Run 20261031T090000Z-3fa9c2 on demo-bench

Opening
  bench_supply  demo,learn-supply,SIM-001  ✓ identity  ✓ health

idle_current
  setup      output on, 5 V, 500 mA limit
  measure    idle_current  180 mA  (<= 250 mA)  PASS
  teardown   output off

Closing
  bench_supply  ✓ safe state  ✓ closed

PASS  1 passed in 0.02 s
Run folder: runs/20261031T090000Z-3fa9c2/
```

Take a moment with that output, since a lot happened around the one line we wrote.

Before the test ran, the instrument was opened, and mastif checked that its serial number
was the one the profile expected. After it finished, the output was turned off by our
`teardown`, then the station made the resource safe and closed the connection. All of it
was recorded, in a folder you can open tomorrow, or next year when somebody asks.

## When the board is bad

Change `current_ma` in the profile to `300`, and run it again:

<!-- termynal: {title: "Mock of the intended experience · a failing run"} -->
```console
$ mastif task demo_tests.idle_current --station stations/demo.yaml
Run 20261031T090112Z-81bd04 on demo-bench

idle_current
  measure    idle_current  300 mA  (<= 250 mA)  FAIL

FAIL  1 failed in 0.02 s
```

Now it's a FAIL. The run itself went fine, though: the instrument answered, the
measurement is valid, and the output was switched off. mastif is telling you something true
about the board.

That's a different situation from an instrument that never answers, which is an **ERROR**.
It tells you nothing about the board, and you should retest it rather than scrap it. We'll
give this distinction a [whole chapter](failures.md) later, because it matters more than it
might seem to right now.

## Run something real

Here's the same measurement today, using the implemented layers directly. The engine's job
is done by hand: building the station, opening it, and recording the result ourselves.

```python title="docs/examples/learn_station.py"
--8<-- "examples/learn_station.py"
```

<!-- termynal: {title: "Real transcript · learn_station.py"} -->
```console
$ uv run python docs/examples/learn_station.py
idle_current: 180 mA -> PASS
after cleanup: output enabled = False
idle_current: 300 mA -> FAIL
after cleanup: output enabled = False
```

Don't worry about understanding all of this yet. Find the `with station:` block near the
end, and see how similar its contents are to our task's `setup` and `run`. The output state
on the last line is proof that the station turned the supply off when the block ended,
though nothing in the block asked it to.

**Try it.** Change the readings at the bottom of the script from `(180, 300)` to
`(250, 251)`, and predict which one passes before you run it. We'll check your answer in
[Limits, checks, and verdicts](limits.md).

## Recap

You've now seen the shape of a mastif test:

- A **task** declares its configuration and the capabilities it requires, then does its
  work in `setup`, `run` and `teardown`.
- A **station profile** says what those capabilities are on one particular bench.
- A **result** judges itself from a value and a limit, and the run keeps the evidence.

Over the next few chapters we'll take this apart, starting with the structure of the task itself.

**Next:** [Writing a reusable test](reusable-tests.md)
