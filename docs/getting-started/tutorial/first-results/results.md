# Understanding the results

Imagine you receive a report in six months' time. It's about a unit that came back from a
customer, and it says only `FAIL`.

You still need to know what was measured, by how much it missed, what the limit was on the
day, whether anyone has changed that limit since, and whether the instrument was behaving
that morning. If the report can't answer those, then the test may as well not have happened.

So let's look at what a result contains, and what it refuses to let you do.

!!! example "Part implemented, part preview"
    Result models and JSON serialisation work today, and the code on this page down to
    [The record of a run](#the-record-of-a-run) runs now. The run folder described after that
    belongs to the engine, and it's a design preview.

## A result is data

A result isn't a line printed to a console. It's a structured record that you can inspect,
store and reload:

```python
from mastif.kernel.limits import Limits
from mastif.kernel.results import Measurement
from mastif.kernel.units import mA

result = Measurement("idle_current", 300 * mA, Limits.at_most(250 * mA))
print(result.model_dump_json(indent=2))
```

```json title="Real output"
{
  "kind": "measurement",
  "name": "idle_current",
  "value": 300.0,
  "unit": "mA",
  "limits": {
    "passing": {
      "low": null,
      "high": 250.0,
      "inclusive": true,
      "unit": "mA"
    },
    "warning": null
  },
  "verdict": "fail"
}
```

Everything needed to understand the decision is right there. The value and its unit are
stored, so the magnitude can't be misread. The limit is stored in full, including whether the
bound was inclusive, so changing the specification next year won't alter what this record says
was tested. `kind` lets anything reading the file tell a measurement from a check or a table.

## Evidence can't contradict itself

Let's try to break it. Suppose someone edits a stored result by hand to change its verdict,
or a buggy tool writes one that disagrees with itself:

```python
from mastif.kernel.limits import Limits
from mastif.kernel.results import Measurement
from mastif.kernel.units import mA

tampered = """{
  "name": "idle_current",
  "value": 300,
  "unit": "mA",
  "limits": %s,
  "verdict": "pass"
}""" % Limits.at_most(250 * mA).model_dump_json()

loaded = Measurement.model_validate_json(tampered)
print(loaded.verdict)  # fail
```

The file claims `pass`, and it was ignored. **Every time a result is loaded, its verdict is
recomputed from the value and limits.** A saved report can't disagree with its own numbers.

Let's be clear about what this does and doesn't give you. It stops contradictions. It doesn't
stop forgery: someone determined could edit the `value` as well, and everything would be
consistent. If you need tamper evidence, you'd want signatures or a controlled store on top.
This is about honesty against mistakes, and it isn't a cryptographic guarantee.

## The three kinds of result

You've now met all three, and they share a common shape.

| Kind | Holds | Its verdict comes from |
|---|---|---|
| `Measurement` | A named value, a unit, and optional limits | Comparing the value with the limits |
| `Check` | A pass or fail, and a human explanation | The `passed` flag |
| `Table` | Rows of values with per-column limits | The worst cell |

## The record of a run

!!! example "Design preview"
    From here on, this page describes the engine's run store.

A measurement tells you *what* was observed. On its own, it doesn't tell you *when*, or under
which conditions, or on which unit. That context belongs to the run. You might be tempted to
squeeze it into the result's name, and end up with something like
`current_slot2_voltage5_repeat3`. Don't: names like that can't be queried, and they're never
quite consistent.

Instead, every run gets its own folder, and we think of that folder as the single source of
truth about what happened. It's the equivalent of the state file in a tool like OpenTofu, and
it's the reason a four-hour run can survive a crash.

```text title="A run folder — preview"
runs/20261031T090000Z-3fa9c2/
├── manifest.json    # What was asked for, frozen at the start
├── events.ndjson    # What happened, in order, flushed as it happens
├── snapshot.json    # Where we had got to, rewritten after each item
└── report.json      # The final answer, derived from the events
```

Each file has a distinct job, and the differences are deliberate.

**`manifest.json` is the question.** It's written before anything runs and never changes: the
plan, the configuration, a hash of the station profile, the identity of every instrument, and
the version of every package. Six months later, this is how you know exactly what ran.

**`events.ndjson` is the history.** It's one event per line, appended and flushed as each thing
happens. If the power fails, everything up to that moment is still on disk, and a half-written
last line is easy to detect and discard.

```json title="events.ndjson — preview, wrapped for reading"
{"seq": 7, "ts": "2026-10-31T09:00:01.204Z", "type": "TaskStarted",
 "task": "idle_current", "position": {"voltage": "5 V"}, "slot": "0"}
{"seq": 8, "ts": "2026-10-31T09:00:01.219Z", "type": "ResultRecorded",
 "task": "idle_current", "position": {"voltage": "5 V"}, "slot": "0",
 "result": {"kind": "measurement", "name": "idle_current", "value": 180.0,
            "unit": "mA", "verdict": "pass"}}
```

See how the context travels *beside* the measurement, as structured fields. The result stays
clean, and you can ask for "every idle current at 5 V on slot 0" without parsing a single name.

**`snapshot.json` is the bookmark.** It's rewritten atomically after each item, holding which
items are finished and the current shared values. It's what [`mastif
resume`](progress.md#surviving-a-crash) reads.

**`report.json` is the summary.** It's produced from the event stream by a pure function, which
has a useful consequence: the summary can always be regenerated, and a bug in reporting can
never damage the evidence.

## Keep the story straight

A final thought about reporting. Consider these two outcomes:

> 300 mA, FAIL. Output disabled successfully.

> 180 mA, PASS. Could not disable the output.

The second one has a passing measurement, and it's the one you need to walk over and deal with
right now, because a supply might still be energised. Squashing a run down to one colour hides
exactly the information you'd want. So mastif keeps the measurement outcome and the cleanup
outcome as separate facts, and it reports both.

## Recap

- A result is **structured data** that holds the value, unit and limit together.
- Verdicts are **recomputed on load**, so stored evidence can't contradict itself, though that
  isn't tamper-proofing.
- The **run folder** holds the rest of the story: what was asked, what happened, how far it got,
  and what it adds up to.

A result tells you about one observation. Next, let's look at the run as a whole: how to watch it, and what happens if it's interrupted.

**Next:** [Inspecting progress and saved results](progress.md)
