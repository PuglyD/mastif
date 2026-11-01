# Inspecting progress and saved results

While a run is going, an operator wants to know what's happening right now. When it's finished, an engineer wants to know exactly what happened. And sometimes, three hours into a four-hour run, the machine
loses power, and everyone wants to know how much of those three hours is lost.

All three questions have the same answer in mastif: a stream of events, written down as they happen.

!!! example "Design preview"
    The event stream, run store, and `resume` belong to the engine, which we're designing in these pages. Result serialisation is implemented. See the [roadmap](../../../wiki/roadmap.md) for what is built.

## Events, not logs

The simplest way to show progress is to print lines of text. And then someone builds a dashboard, so they parse those lines with a regular expression. Then someone improves a log message, and the dashboard
breaks. Logs are written for people, and they change whenever it helps people. If a program depends on them, they've become an API that nobody has agreed to maintain.

So mastif has a separate channel, designed for programs. It's a sequence of typed **events**, and each one carries the same envelope:

```python title="mastif/events — preview"
class Event(BaseModel):
    seq: int               # Increases by one with every event
    ts: datetime           # When it happened
    run_id: str            # Which run
    slot: str              # Which DUT slot
    position: Position     # Where in the loops
```

The sequence number is what makes it reliable. If a consumer sees 41, then 43, it knows that it missed one, and it can ask for it again. It never needs to guess.

Here are the event types, which are essentially the vocabulary of what can happen in a run:

| Family | Events |
|---|---|
| **Run** | `RunStarted`, `PreflightFinished`, `RunFinished` |
| **Loops** | `LoopEntered`, `LoopExited` |
| **Tasks** | `TaskStarted`, `TaskFinished`, `StepStarted`, `StepFinished` |
| **Results** | `ResultRecorded` |
| **Operator** | `PromptRequested`, `PromptAnswered` |
| **Resources** | `ResourceOpened`, `ResourceFault` |

`mastif schema events` exports all of this as JSON Schema, so that a UI written in another language can generate its types directly from the source of truth.

## Watching a run

The terminal output you've seen isn't special. It's one consumer of the event stream. You can attach others in your own application, by implementing a small protocol:

```python title="my_app/listeners.py — preview"
from mastif.api import Event, EventSink, ResultRecorded


class FailureAlert(EventSink):
    def emit(self, event: Event) -> None:
        if isinstance(event, ResultRecorded) and event.result.verdict == "fail":
            notify_quality_team(event)
```

This is also how you handle artifacts. Suppose a passing calibration run has to produce a calibration file. You might be tempted to write that file from inside a task, but then every
test run would produce one, including those that failed. Instead, a sink can respond to `RunFinished`, look at the verdict, and write the file only when it's meaningful. The test
stays focused on testing, and your organisation's post-processing lives elsewhere.

## What gets saved

We introduced the run folder in [Understanding the results](results.md#the-record-of-a-run). Here's what each file contains, and when it's written.

```text title="preview"
runs/20261031T090000Z-3fa9c2/
├── manifest.json    # Written once, before anything runs
├── events.ndjson    # Appended and flushed after every event
├── snapshot.json    # Replaced atomically after every completed item
└── report.json      # Generated at the end from the events
```

The manifest records everything that defines this run: the expanded plan with its resolved configuration, a hash of the station profile, the identity of each instrument as reported when it opened,
and the version of every package. Sensitive values are a real concern here. Anything held as a secret, a password in a transport's configuration for example, is stored as a redacted placeholder.

You'd query these however you like, as they're plain files:

<!-- termynal: {title: "Mock of the intended experience · looking back at a run"} -->
```console
$ mastif show runs/20261031T090000Z-3fa9c2
Run 20261031T090000Z-3fa9c2   widget-acceptance   FAIL
  Station  bench-01   ·   mastif 0.4.0   demo-sdk 2.1.3   demo-tests 1.7.0
  Unit     SN-42
  16 items: 15 passed, 1 failed

  FAIL  idle_current  profile=lowpower voltage=5.25 V
        idle_current  263 mA  (<= 250 mA)

$ grep '"verdict":"fail"' runs/20261031T090000Z-3fa9c2/events.ndjson | wc -l
1
```

Plain files make the proposed run record easy to inspect with ordinary tools, so they're what we show here. The engine owns writing that record; an application's reporting or export code consumes it. Choosing a storage location still matters: a network share can disappear, a disk can fill, and a completed write is only as durable as the storage contract promises. The engine must report a recording failure rather than silently present the run as fully recorded. Distribution and long-term retention are separate application concerns.

The [concept system design](../../../learn/system-design/station-and-server.md#the-outbox-pattern) explores how durable local records can reach shared storage later through an outbox. That is a system-level pattern, not an additional feature implemented by the run-folder preview.

## Surviving a crash

Now for the feature that we most wanted from the start. Consider a run that takes hours, and that fails near the end for a reason unrelated to the unit: the PC reboots for updates, or the
process runs out of memory. Without this, everything's lost, and the run starts over.

The pieces we've built up make this quite tractable. After each completed item, the engine replaces `snapshot.json` **atomically**: it writes to a temporary file, then renames it. If the
power fails in the middle of that, you've still got either the old snapshot or the new one, never half of one.

<!-- termynal: {title: "Mock of the intended experience · resuming after a crash"} -->
```console
$ mastif resume 20261031T090000Z-3fa9c2
Resuming run 20261031T090000Z-3fa9c2
  Plan unchanged (manifest hash matches)
  11 of 16 items complete
  Opening station... bench_supply ✓ identity  ✓ health
  Entering profile=lowpower
  Entering voltage=4.75 V

  Continuing from item 12: idle_current
```

Here's what's happening under the hood, and why each earlier design decision was needed.

1. **Reload the manifest.** That gives the exact plan and configuration that were used.
2. **Expand it again.** [Expansion is pure](../writing-tests/plans.md#expansion-is-a-pure-function), so this gives the identical list of work.
3. **Skip what's complete.** The snapshot lists it.
4. **Restore the context.** [Context values](../writing-tests/parameters.md#passing-values-between-tasks) are Pydantic models, so they come back from the snapshot, and later tasks can still have that offset measured three hours ago.
5. **Re-enter the loops.** The engine calls `enter` on each loop at the resume position, as though it had just arrived. This is what restores the bench, since the bench's physical state couldn't be
   saved. Our firmware profile's `enter` installs the profile and restarts the board.
6. **Carry on.** The interrupted item runs again from the beginning.

The goal, which we'd hold ourselves to with a golden test, is that **a resumed run's final report equals that of an uninterrupted run**.

Now, resuming isn't always valid, and we should say so. If a unit has been swapped, its identity won't match. If hours have passed and a physical property has drifted, then the earlier measurements may
no longer describe the same conditions. mastif can check the first of those. The second is an engineering judgement. The chapter on [recovery](../../../learn/system-design/recovery.md) goes deeper. A resumed run is always
marked as such in its record, so nobody's misled later.

## Telling a finished run from a crashed one

A folder containing a half-finished run must never look like a finished one. It's easy to tell them apart, and that's by design: only a completed run has a `report.json`, and its event stream ends with
`RunFinished`. Anything else is, by definition, incomplete, and `mastif show` says so. If the final line in `events.ndjson` is half-written because the power went off mid-write, then it's detected and ignored, and
everything up to it is valid.

??? question "Still open in this design"
    What exactly does `ctx.measure` acknowledge? If it returns once the event is flushed to disk, then every measurement costs a disk flush, which is the safe choice and the one we lean towards. A very fast sweep might
    prefer batching, and that's a place where a `Table` already helps. We haven't closed this question yet.

## Recap

- **Events are for programs, and logs are for people.** Events have a schema and sequence numbers, so a consumer can depend on them.
- Your own code plugs in as an **event sink**, for dashboards, notifications and artifacts.
- A **run folder** holds what was asked, what happened and how far it got, as plain files.
- **`mastif resume`** picks up after a crash, because the plan expansion is pure, the context is serialisable, and loop `enter` can restore the bench.

You can now write a test and read what it produced. So far, though, the instruments have come from somewhere else. It's time to provide them yourself.

**Next:** [Your first driver](../hardware-integration/first-driver.md)
