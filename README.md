# mastif

A domain-neutral framework for automated test equipment (ATE).

- **Core**: the test execution engine, the instrument and DUT primitives, results and events.
- **API**: a stable Python API, plus an optional network service built on it (planned).

Organisations write their own SDK on top of it (contracts, drivers, DUT types, loop types) and attach their own UI.

Status: early development. See `docs/plan.md` and `docs/adr/`.

```
uv sync
uv run pytest
```
