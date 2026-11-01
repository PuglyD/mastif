# Verdicts, dispositions, and audit

A unit fails a check, and an engineer sends it for rework. After the repair, it passes a second run. Which result should a report show? Both: the first run explains why the repair happened, and the second records what was measured afterwards. Replacing the first FAIL with the later PASS would lose part of the story.

The same distinction matters whenever a person makes a decision about test evidence. We need to preserve what was measured separately from what someone decided to do next.

!!! example "Generic integration principle"
    Computed verdicts are implemented in the kernel. The discussion of dispositions and audit below explains how an application can preserve their meaning. mastif does not currently provide a disposition model, approval workflow or audit service.

## Two different facts

A **verdict** is an evaluation of evidence. A **disposition** is a decision about the subject of that evidence: for example, send a unit for rework or request another test. They answer different questions, so combining them in one editable status creates ambiguity.

| | Verdict | Disposition |
|---|---|---|
| **Answers** | Did this observation meet its requirement? | What should happen next? |
| **Comes from** | A value or check evaluated against its criterion | An application workflow or an accountable decision |
| **Examples** | PASS, FAIL, ERROR | Rework, retest, accept under a documented deviation |
| **Relationship** | Preserved with the original evidence | Refers to that evidence without replacing it |

A [`Measurement`](../../getting-started/tutorial/first-results/results.md#evidence-cant-contradict-itself) computes its verdict from its value and limits. A person accepting a deviation doesn't change either of those inputs. The measured result therefore remains a FAIL, even if the surrounding workflow allows the unit to proceed.

This is also why retesting should produce a new record. If the fixture was repaired or a limit was corrected, record that context with the new attempt. Readers need to distinguish a fresh observation from a correction or a decision about an earlier one.

## Give each record a clear owner

The test owns the observation and the requirement it evaluates. The framework supplies the result model and, in the planned engine, the run and task context. The application owns what a result means for its wider workflow.

An application recording a disposition needs an unambiguous reference to the relevant evidence. A run-level decision and a decision about one measurement aren't interchangeable. It should also retain the action, reason, actor and time so someone can understand the decision later. These are information needs, not a proposed mastif schema; names, permissions and workflow states depend on the application.

That boundary lets the same test code serve different uses. A development bench might simply record a note and rerun a task. A production application might have a formal review process. Neither needs a different definition of PASS.

## Keep a history of decisions

An **audit log** records actions and their context. An append-only design preserves earlier entries and adds a correction when a decision changes, rather than editing away the earlier action. That makes the sequence explainable: the first decision happened, and a later decision superseded it for a stated reason.

Append-only is a behaviour the storage and application must enforce. An ordinary file that a user can freely rewrite doesn't become tamper-resistant merely because the UI has no edit button. Likewise, a computed verdict establishes consistency between a result's fields; it doesn't prove the stored input was never altered or that a sensor was accurate.

The framework's [result model](../architecture/kernel.md#results-evidence-that-cant-contradict-itself) supplies one useful guarantee at one boundary. Retention, access control and any stronger integrity guarantees belong to the system storing and using that evidence.

## What this means for your UI

Show an automated outcome and a later decision as separate facts. For example, “FAIL — sent for rework” explains more than a single “handled” status. If a later run passes, link it to the earlier attempt rather than hiding the earlier failure.

An [operator interface](../operations/operator-ui.md) should also distinguish requests from completed actions. Clicking a button to request a retest is not evidence that the retest ran, just as clicking Stop is not evidence that an instrument reached a safe state. Show the outcome reported by the component that owns the action.

## Recap

- A **verdict** evaluates evidence; a **disposition** records what happens because of it.
- New tests, corrections and decisions should remain distinguishable in the record.
- Computed verdicts protect consistency, not storage integrity or physical accuracy.
- Applications own their decision workflows and audit policies; they can build around mastif's evidence without rewriting it.

Next, we'll follow the planned execution lifecycle that produces that evidence in the first place.

**Next:** [From starting a run to receiving a result](run-lifecycle.md)
