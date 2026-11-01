# Combining tests into a plan

A task answers one question. A real procedure asks many of them, in a particular order, under particular conditions. In this chapter we'll
write our first **plan**, and meet an idea that we've borrowed from an unexpected place: you should be able to read exactly what a run is
going to do before it does anything.

!!! example "Design preview"
    The plan format and the `mastif` command belong to the engine, which we're designing in these pages. See the
    [roadmap](../../../wiki/roadmap.md) for what is built.

## Why not just write it in Python?

You could call your tasks from a Python script, in order. It works, and for a while it's fine. So why add a file format?

Because a sequence written as code has the same problem we solved for individual tests: nothing can read it without running it. If the
sequence lives inside a function, then no tool can answer "what's about to happen?", or "how many items is this?", or "which instruments does this
need?". It also makes it awkward for anyone but a programmer to change the order or a limit.

So a plan is **data**. It says which tasks to run with which values, and it contains no logic of its own.

## A first plan

```yaml title="plans/idle-check.yaml — preview"
name: idle-check

sequence:
  - task: power_on
  - task: firmware_version
  - task: idle_current
    config:
      max_current: 300 mA
  - task: power_off
```

Each entry refers to a task by its `id`, and can set values on that task's config. Nothing more is going on here. Tasks come from your test
package, which advertises them through an entry point the same way your SDK advertises drivers, so `mastif` can find them by name.

The same task can appear more than once with different values, as long as you give each one its own name, so that their results aren't
ambiguous:

```yaml title="preview"
sequence:
  - task: idle_current
    id: idle_nominal
    config: {voltage: 5 V}
  - task: idle_current
    id: idle_brownout
    config: {voltage: 4.5 V, max_current: 200 mA}
```

`task` says what to run, and `id` says which occurrence this is, which is what appears in the results.

## Plan, then apply

Here's the idea we've borrowed. [OpenTofu](https://opentofu.org/) is a tool for managing infrastructure, which has nothing to do with test
equipment, and it has a workflow we've come to admire. Before it changes anything, it computes a **plan**, and shows it to you: here's precisely
what I'm about to do. You read it, and then you say go.

This turns out to suit test execution remarkably well, especially when you consider what a run can involve: reconfiguring a product, cycling power, running
for hours. Finding out it was going to do the wrong thing should not require watching it happen.

So `mastif plan` expands everything, checks everything, and prints the result without touching any hardware:

<!-- termynal: {title: "Mock of the intended experience · mastif plan"} -->
```console
$ mastif plan plans/idle-check.yaml --station stations/bench-01.yaml
Plan idle-check on bench-01

  Station
    ✓ all roles resolve and provide their contracts
    · bench_supply  acme.psu-x  expects serial A123

  Will run, in this order
    1  power_on
    2  firmware_version
    3  idle_current     max_current=300 mA, voltage=5 V
    4  power_off

  Requires: supply, dut
  4 items. Nothing was opened.

$ mastif run plans/idle-check.yaml --station stations/bench-01.yaml
```

Look at item 3: its configuration has been *resolved*, with defaults and overrides combined into what will actually be used. That's the same data that goes
in the manifest. There's no gap between what you were shown and what runs, because the plan the engine executes is the expanded one that it printed.

## Expansion is a pure function

There's a technical decision behind that output, and it's worth knowing about because it has so many pleasant consequences.

Turning a plan file into an ordered list of work is a **pure function**: no I/O, no hardware, no clock. The same inputs always produce the same list.

```python title="preview"
execution_plan = expand(plan, request)
# -> an ordered list of Item(position, task_id, slot)
```

Everything else follows from that.

- `mastif plan` can show you the real order, because it's running the real code.
- The order can be tested with **golden files**: the expected expansion is checked into your repository, and a change to the sequence shows up as a diff in code
  review.
- It's trivially fast, so you can do it in CI for every plan.
- It's what makes crash recovery possible. To resume, the engine expands the frozen plan again, and gets the identical list. Then it can skip what's done.

## What should happen when something fails?

A sequence is easy until something goes wrong. Suppose `firmware_version` fails. Should `idle_current` still run?

It depends, and there isn't a right answer in general. Sometimes carrying on gathers useful evidence, as you'd like to see every failing measurement on this board,
not only the first. Sometimes the next step assumes the last one worked, and running it is a waste of time, or possibly dangerous. So this is a decision you make in the plan,
and it has its own name: a **policy**.

```yaml title="preview"
name: idle-check

policies:
  on_fail: continue    # A task's verdict was FAIL: keep going
  on_error: stop_run   # The test broke: stop, and make everything safe
  retries: 0

sequence:
  - task: power_on
    policies: {on_fail: stop_run}   # No power means no point continuing
  - task: firmware_version
  - task: idle_current
  - task: power_off
    always: true                    # Runs even if the run is being stopped
```

The two settings are separate because FAIL and ERROR are separate facts, and they usually call for different responses. A common combination is the one above: a failed
measurement means keep gathering evidence, whereas a broken test means stop, since you can no longer trust what you're doing.

| Policy | What it does |
|---|---|
| `continue` | Record the outcome and move on to the next item |
| `stop_loop:<name>` | Skip the rest of this loop, and carry on after it |
| `stop_run` | Stop the run, unwinding through exits and teardowns |
| `retries: n` | Try a failing or erroring task up to *n* more times. [Be careful](../../../learn/system-design/recovery.md) |

You can see `always: true` on `power_off`. When the run is stopping, whether by policy or by an operator pressing abort, tasks marked this way still run, so the procedure can unwind
what it set up. The station's safe state remains the backstop after that.

## A plan isn't a profile

It's worth setting these two side by side, since they're both YAML, and they answer different questions.

| | Station profile | Plan |
|---|---|---|
| **Answers** | What's connected to this bench? | What are we going to do? |
| **Changes when** | Equipment changes | The procedure changes |
| **Owned by** | Whoever runs the bench | The test author |
| **Shared by** | One bench | Every bench that runs it |

Keeping them apart is what lets one plan run on many benches, and one bench run many plans. Neither one should ever reach into the other's job. If you see a host name in a plan, or
a pass limit in a profile, something's in the wrong file.

Also, like a profile, **a plan isn't a programming language**. There's no `if`, no arithmetic and no custom expressions. Conditions you do need go in `should_run`, as ordinary Python
that can be tested. We're wary of YAML that slowly grows into a language nobody can debug.

??? question "Still open in this design"
    Two questions remain open, and we'd welcome your opinion. Should `mastif run` print the plan and ask for confirmation by default, as OpenTofu's `apply` does, or should that be a
    flag? And should a plan be able to include another plan, or does that introduce the sort of complexity we've been trying to keep out?

## Recap

- A **plan** is data, so tools can read it without running anything.
- **`mastif plan`** shows exactly what will run, with resolved values, before anything is touched. Then `mastif run` does precisely that.
- **Expansion is a pure function**, which gives you golden tests, fast CI checks, and the foundation for crash recovery.
- **Policies** decide what a failure means for the rest of the run, and `on_fail` and `on_error` are separate on purpose.

So far our plan has been a straight line. But the real shape of testing is nested: every task, at every voltage, on every firmware configuration. And it turns out that the *order* of those
loops matters a great deal more than you might think.

**Next:** [Repeats, sweeps, and DUT slots](loops.md)
