# Repeats, sweeps, and DUT slots

Now we get to the part of test execution that's easy to underestimate. A real procedure is rarely a straight line. It's every
task, at every frequency, in every software configuration of the product, and sometimes on several units at once.

If you've maintained a test system, you probably know how this ends up: a set of nested `for` loops, hardcoded, at the centre of
the whole program. And then one day, somebody needs to change the order.

!!! example "Design preview"
    Loops and expansion belong to the engine, which we're designing in these pages. `Position` and `SlotId` in `mastif.kernel.ids`
    are implemented. See the [roadmap](../../../wiki/roadmap.md) for what is built.

## A story about loop order

Here's a situation that comes up in real calibration work, generalised a little.

A product has to be calibrated at many frequencies, with a handful of tasks at each. For years the procedure is written **task first**:
do all the frequencies for task A, then all the frequencies for task B. There's a reason for that: changing the product's frequency is slow,
so you'd rather do your tuning in bulk, per task.

```python title="task first — not mastif"
for task in tasks:
    for frequency in frequencies:
        retune(frequency)     # Slow: thousands of times
        task.run(frequency)
```

Then an embedded software update arrives, and now some models can change frequency on the fly. All at once, the efficient order is the opposite one,
**frequency first**:

```python title="frequency first — not mastif"
for frequency in frequencies:
    retune(frequency)         # Far fewer times
    for task in tasks:
        task.run(frequency)
```

Same tasks and same frequencies, with a large change in run time. But in a hardcoded system, this is no small refactoring. The loops are mixed
into the logic, tasks have come to rely on what ran before them, and so a change that's obvious on a whiteboard takes weeks to do safely. It's also
different for different models, so now you have two copies of the program.

And here's the second half of the story. The product can also run in several software configurations, and switching between them requires restarting a
binary, which takes minutes. So that's another loop, with its own expensive transition, and it needs to go on the outside, so that it happens as rarely as
possible.

The lesson we took from this:

> **What to loop over, and in what order, is a decision about the procedure. It should be one line of configuration, and it shouldn't be part of the structure of
> your program.**

## Loops in a plan

Here's how that looks in a plan:

```yaml title="plans/widget-acceptance.yaml — preview"
name: widget-acceptance

loops:
  profile:
    type: demo.firmware_profile     # An org-defined loop type: see below
    values: [std, lowpower]
  voltage:
    type: values                    # The built-in: just a list of values
    values: [4.75 V, 5 V, 5.25 V]

order: [profile, voltage, task]     # This line is the whole story

sequence:
  - task: power_on
    when: {voltage: first}          # Once per profile, not once per voltage
  - task: idle_current
  - task: ripple
  - task: power_off
    when: {voltage: last}
```

`order` reads outside to inside. It says: for each profile, for each voltage, run the tasks. `task` is itself one of the dimensions, and this is where the
flexibility comes from. To swap the order, change one line:

```yaml title="preview"
order: [profile, task, voltage]     # For each task, sweep the voltage
```

Look at the difference with `mastif plan`, before anything runs:

<!-- termynal: {title: "Mock of the intended experience · two orders, compared"} -->
```console
$ mastif plan plans/widget-acceptance.yaml --station stations/demo.yaml
  order: profile > voltage > task
  profile=std
    voltage=4.75 V   power_on · idle_current · ripple
    voltage=5 V      idle_current · ripple
    voltage=5.25 V   idle_current · ripple · power_off
  profile=lowpower
    ...
  Loop transitions: profile 2, voltage 6   ·   Items: 16

$ mastif plan plans/widget-acceptance.yaml --station stations/demo.yaml --order profile,task,voltage
  order: profile > task > voltage
  profile=std
    idle_current     4.75 V · 5 V · 5.25 V
    ripple           4.75 V · 5 V · 5.25 V
  ...
  Loop transitions: profile 2, voltage 12   ·   Items: 16
```

It's the same work with a different cost, and you can see that cost, as a number, before you've powered anything. That's what we set out to achieve.

!!! warning "Order can change the experiment"
    Reordering a sequence isn't always innocent. If a board warms up, then measuring all three voltages first and then all three ripple values is physically a
    different experiment from interleaving them. mastif can make it easy to change and show you what changes, but deciding whether a reordering is still a valid test
    remains an engineering judgement.

## What a loop type does

The built-in `values` loop simply iterates over a list, doing nothing in particular as it goes. The interesting behaviour comes from the transitions, and that's what
an organisation-defined loop type provides. Switching the product's firmware profile is meaningful only to you, so it belongs in your SDK:

```python title="demo_sdk/loops.py — preview"
from mastif.api import loop


@loop("demo.firmware_profile")
class FirmwareProfile:
    """Switch the board to a software configuration, and restart it."""

    def enter(self, value, ctx):
        board = ctx.station.require("dut", WidgetBoard)
        board.install_profile(value)
        board.restart()
        board.wait_until_idle(timeout=120.0)

    def exit(self, value, ctx):
        ctx.station.require("dut", WidgetBoard).restore_default_profile()

    def can_change_inline(self, previous, following):
        # Some models can switch without a restart.
        return False
```

There's a clear division of labour in that. mastif knows nothing about firmware, or what a profile is. Your SDK knows nothing about nesting, ordering or crash recovery.
The tasks don't even know the loop exists, because by the time a task runs, the loop has already put the world into the right state. That's what lets you reorder loops
freely.

`can_change_inline` is for that situation from our story, where certain models can change on the fly. It lets the loop type say that a transition can be cheap, without any task
needing to know.

## Transitions are computed, too

When the engine moves between two items, it has to work out which loops to leave and which to enter. It does this by comparing their positions:

```python
from mastif.kernel.ids import Position

here = Position.of(profile="std", voltage="5 V")
print(here)
```

So a position is an ordered list of loop values, outermost first. That type exists today. Moving from `profile=std, voltage=5.25 V` to `profile=lowpower, voltage=4.75 V` means
exiting `voltage`, then exiting `profile`, then entering `profile`, then entering `voltage`. It's innermost first on the way out, and outermost first on the way in, just the way a
stack unwinds.

Like plan expansion, this is a **pure function**, `transitions(previous, next)`, with no hardware in it. That means it can have golden tests covering every ordering, which is good news
considering how much depends on it. A bug here could leave a product in the wrong configuration for an entire run.

## Knowing where a result came from

Now that a task runs many times, "idle current failed" isn't enough. Which voltage? Which profile? The usual answer is to put it in the name, and you end up with
`idle_current_std_5v_rep3`, which can't be queried or relied upon.

In mastif you don't need to do that. A result keeps a simple name, and the engine records its position beside it:

```json title="an event — preview, wrapped for reading"
{"type": "ResultRecorded", "task": "idle_current",
 "position": {"profile": "std", "voltage": "5 V"}, "slot": "0",
 "result": {"name": "idle_current", "value": 180.0, "unit": "mA", "verdict": "pass"}}
```

A task can read the same position through `ctx.position`, should it need to. Usually, though, a loop value that a task needs is better passed in through its configuration.

## Inner sweeps: tables instead of items

Not every loop should be a plan loop. It's worth drawing the line, because it's a judgement call you'll make often.

**Use a plan loop** when each point deserves its own setup and verdict, or when the transition has real cost and needs managing.

**Use a [`Table`](limits.md#tables-judging-a-whole-sweep) inside one task** when the points are one tightly coupled observation, such as a hundred-point frequency response where the
sweep takes a second. Making that a hundred items would be noisy and slow.

## Several units at once

The same kind of thinking applies to testing more than one unit. A fixture may hold two boards, in *slots*. It's tempting to treat a slot as just another loop, but it's a bit different,
because it brings up the question of what's shared.

```yaml title="a profile with slots — preview"
resources:
  supply_a: {driver: acme.psu-x, slot: left, ...}
  supply_b: {driver: acme.psu-x, slot: right, ...}
  analyser: {driver: acme.sa-1, shared: true, ...}
```

The two supplies can work in parallel. The analyser can't: only one slot at a time can use it, or the measurements will corrupt one another. The profile already has fields for `slot` and
`shared`, though they're reserved vocabulary today, and nothing enforces them yet. Multi-DUT scheduling comes later, and when it does, it'll be built on the [control
leases](../../../learn/system-design/resource-lifetimes.md) that we'll describe further on.

## Recap

- **What to loop over, and in what order, is one line of configuration**: `order: [profile, voltage, task]`.
- **`mastif plan` shows the cost** of an order before you run it.
- **Loop types** belong to your SDK, and they supply the `enter` and `exit` transitions. Tasks never know about them.
- **Expansion and transitions are pure functions**, so they can have golden tests.
- **Results keep a simple name**, and the position is recorded beside them as structured data.

All of those loop transitions imply things to undo. A run needs to back out carefully, particularly when it's stopped halfway through. That's next.

**Next:** [Setup, cleanup, and cancellation](cleanup.md)
