# ADR-0002: Result model, limits and verdicts

- **Status:** accepted
- **Date:** 2026-10-20

## Context

Tests record many kinds of outcome: single values against limits, boolean conditions,
and whole tables produced by inner loops (per channel, per point). Reports, UIs and
resumed runs must all agree on the verdicts.

## Decision

- **Verdicts:**
  - The verdicts are `PASS`, `WARN`, `FAIL`, `ERROR`, `SKIPPED` and `ABORTED`.
  - WARN is a verdict in its own right, not a flag on PASS.
  - Aggregation precedence is ABORTED > ERROR > FAIL > WARN > PASS > SKIPPED. A parent
    is therefore SKIPPED only when all of its children were skipped.
- **Limits:**
  - `Limits` consists of a passing `Range` and an optional, wider warning `Range`.
  - Ranges may be one-sided. Bounds are inclusive by default.
  - `IndexedLimits` selects limits per index, with an optional default. Index keys are
    compared as text.
- **Results:**
  - The result types are `Measurement`, `Check` and `Table`, joined in a union
    discriminated by `kind`.
  - **The verdict is always computed from the data and limits.** Callers cannot supply
    one, and a `verdict` key in serialised input is dropped and recomputed.
- **Errors:**
  - mastif errors don't subclass `ValueError`, so Pydantic doesn't wrap them.
    `UnitError` and `LimitsError` reach callers as themselves.

## Consequences

- A result can never carry a verdict that contradicts its data.
- Tables keep inner-loop data together, and each cell gets its own verdict.
- Results carry no run context such as position or slot. The engine attaches that once
  per event.

## Alternatives considered

- **WARN as a flag on PASS**: rejected. It hides marginal results in aggregation, and
  operators want them to stand out.
- **Caller-supplied verdicts**: rejected because they invite inconsistency, as in
  log-scraped verdicts.
