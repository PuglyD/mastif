# ADR-0001: Home-grown units instead of pint

- **Status:** accepted
- **Date:** 2026-10-20

## Context

Measurements, limits and driver contracts need units (`12 * V`, `250 * mA`, `10 * dBm`).
pint is the standard Python units library. It is large, has noticeable import and startup
cost, and its quantities don't serialise into Pydantic/JSON without adapters. Test
equipment also relies on logarithmic units (dB, dBm), whose conventions pint handles in
ways that surprise test engineers.

## Decision

`mastif.kernel.units` provides a small `Quantity(value, unit)` Pydantic model:

- It uses a built-in table of SI-prefixed units.
- Any other symbol is accepted as its own dimension, so no registration is needed.
- dB-family arithmetic follows RF convention (`dBm + dB -> dBm`, `dBm - dBm -> dB`).
  dB-family units never convert to linear units.
- Unit constants (`V`, `mA`, `GHz`, ...) build quantities by multiplication.

## Consequences

- No extra dependency. Quantities round-trip through JSON as `{"value", "unit"}`.
- There are no compound units (`V/m`, `W/Hz`). An org can still use these as opaque
  symbols that only convert to themselves.
- The aliases `Volts`, `Amps`, ... document intent but don't check dimensions
  statically.

## Alternatives considered

- **pint**: rejected for dependency weight, startup cost and serialisation friction. The
  `Quantity` API is small enough to back with pint later if needed.
- **Bare floats with unit-suffixed names** (`voltage_v`): rejected because unit mistakes
  become silent wrong verdicts.
