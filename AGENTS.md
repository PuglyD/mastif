# mastif — rules for contributors and coding agents

mastif is a **domain-neutral** framework for automated test equipment (ATE).
It provides a core (test execution engine, instrument/DUT primitives, results, events)
and a generic API. Organisations build their own SDK (contracts, drivers, DUT types,
loop types) and UI on top of it.

## Clean-room rules (non-negotiable)

- Write all code from first principles. **Never copy code, text, data or file layouts** from
  other repositories on this machine (earlier attempts, legacy tools, driver
  collections). Do not open them while
  working here.
- **No customer or employer identifiers** anywhere: company names, product names, part
  numbers, protocol/ICD terms, site names, people. Examples use the fictional orgs `demo`
  and `acme` and simulated devices.
- Dependencies must use permissive licences (MIT, BSD, Apache-2.0, PSF). No GPL/AGPL/LGPL.

## Layering

```
mastif.cli  →  mastif.api  →  mastif.engine  →  mastif.station  →  mastif.resources  →  mastif.kernel
```

- A layer may import only layers to its right. Enforced by import-linter (`uv run lint-imports`).
- The core never imports org code; org code is discovered through entry points.
- `mastif.kernel` is pure: no I/O, no threads, no hardware.
- Nothing domain-specific in core. If a concept only makes sense for one kind of product,
  it belongs in an org SDK as an extension.

## Code style

- Pydantic v2 for data models, `model_config = ConfigDict(extra="forbid", frozen=True)`
  unless mutation is required and justified.
- Google-style docstrings on every function, make sure each function docstring has usage examples as well as more context how this fits into the grand scheme of the project, try to be as user friendly and first principles as possible while still being technical.
- Typed errors from the `MastifError` hierarchy; never return sentinel values (`0.0`, `None`
  meaning "failed").
- Importing a module must have no global side effects (no registration at import time).
- Prefer pure functions for decisions (evaluation, aggregation, plan expansion, transitions);
  keep I/O at the edges.

## Tests

- pytest, Arrange / Act / Assert.
- Use **fakes** (from `mastif-testing` or local), not mocks.
- Every pure function gets direct unit tests; plan expansion and reports get golden tests.
- Docstring examples are written as doctests (`>>>`) and run by `uv run pytest`
  (`--doctest-modules`), so they can never go stale.

## Git workflow

Branching (git flow), commit messages (Conventional Commits) and versioning (SemVer) are
defined in [`CONTRIBUTING.md`](CONTRIBUTING.md). Never commit directly to `main` or `develop`.

## Commands

```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run ty check
uv run lint-imports
```

## Decisions

Architecture decisions are recorded in `docs/adr/` (template: `docs/adr/0000-template.md`).
Read the ADRs before changing anything they cover.
