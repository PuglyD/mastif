# ADR-NNNN: Title (name the module or the decision)

| | |
|---|---|
| **Status** | proposed \| accepted \| superseded by ADR-XXXX |
| **Date** | YYYY-MM-DD |
| **Module(s)** | `mastif.layer.module` |
| **Layer** | kernel \| resources \| station \| engine \| api \| cli \| testing |
| **Related** | ADR-XXXX (why it's related) |

> **Who this is for:** an engineer who joined today. Assume they know Python and test
> engineering in general, and know nothing about mastif. Explain every mastif term the
> first time it appears, and link to the [glossary](../wiki/glossary.md).

## 1. Summary

Three to five sentences: what this module is, the problem it solves, and the one idea
to remember about it.

## 2. The problem, from first principles

Start from the physical or organisational reality, not from the code.

- **What real situation makes this necessary?** For example: "instruments are reached over
  different media, and a cable can fall out mid-run".
- **What goes wrong without it?** Give concrete failure stories.
- **Forces and constraints.** List what pulls the design in different directions: safety,
  traceability, ease of writing org code, testability without hardware, performance,
  dependencies.

## 3. Where it sits in the system

- **Layer**, and why it belongs in that layer.
- **Upstream:** who calls or uses it.
- **Downstream:** what it depends on.
- **What flows through it:** data in and out.

Include a mermaid diagram:

```mermaid
flowchart LR
    caller[Who uses it] --> this[This module] --> dep[What it uses]
```

## 4. Decision

State plainly what we decided. Use numbered points when there are several.

## 5. Abstractions

For **every public type and function**, give:

- **Purpose:** why it exists.
- **Invariants:** what is always true about it.
- **Key behaviour:** what it does, including edge cases.
- **Example:** a short snippet.

Private helpers worth understanding may be listed briefly.

## 6. Data flow

A mermaid sequence or flow diagram of the main path(s), then a step-by-step
walk-through. Cover both the happy path and the main failure path.

## 7. Errors

| Exception | Raised when | What it means | Who should catch it, and what they should do |
|---|---|---|---|
| `SomeError` | ... | ... | ... |

Also state which errors pass through from lower layers unchanged.

## 8. Guarantees and invariants

What callers can rely on. For example: thread safety, idempotency, ordering, "no I/O",
"never returns a sentinel".

## 9. Consequences

- **Positive:** what becomes easier.
- **Negative / costs:** what becomes harder, and the limitations accepted.
- **Risks to watch.**

## 10. Alternatives considered

Each alternative, with the concrete reason it was rejected.

## 11. Open questions and future work

## 12. Code map

| What | Where |
|---|---|
| Implementation | `packages/.../module.py` |
| Tests | `packages/.../tests/...` |
| Wiki | `docs/wiki/...` |

## History

- YYYY-MM-DD: created.
