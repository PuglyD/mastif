# mastif — rules for contributors and coding agents

mastif is a **domain-neutral** framework for automated test equipment (ATE).
It provides a core (test execution engine, instrument/DUT primitives, results, events)
and a generic API. Organisations build their own SDK (contracts, drivers, DUT types,
loop types) and UI on top of it.

## Building from scratch (non-negotiable)

- mastif is a **from-scratch implementation**. Other projects in the parent directory
  (earlier mastif attempts, legacy test tools, driver collections, design session notes)
  may be read freely as **inspiration and reference**:
  - what problems a real station has
  - which designs worked and which caused pain
  - how an instrument protocol behaves
- What comes back from them is **understanding, not material**. Write every line here
  fresh, designed for a domain-neutral framework:
  - don't paste code, docstrings, data files or test fixtures from those projects
  - don't mechanically port a module
- **No customer or employer identifiers** anywhere: company names, product names, part
  numbers, protocol/ICD terms, site names, people, internal IPs or paths. If a reference
  project uses a product-specific concept, generalise it (e.g. a product's firmware
  configuration becomes an org-defined loop type). Examples use the fictional orgs `demo`
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
- Every test module and test function has a docstring. A test's docstring states the
  behaviour it pins down and why that behaviour matters to users. Parametrised tests
  document their parameters under `Args:`.
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
uv run mkdocs build --strict
```

## Documentation (non-negotiable)

Documentation is part of the change, not a follow-up. A branch that adds or changes code
is not done until its ADRs and wiki pages are done too.

**Audience.** Write every ADR and wiki page for a capable engineer who joined the project
today and knows nothing about it. They should come away understanding *what* exists,
*why* it exists, and *how it connects to the rest of the system*.

**Style.**
- **First principles.** Start from the real-world problem, e.g. "a cable falls out
  mid-run", and derive the design from it. Never start from the code.
- **Systems thinking.** Always place the thing in the wider system: what calls it, what
  it calls, what flows through it, and what breaks if it's wrong.
- Be precise and technical, but explain every term the first time it appears, and link
  to the glossary.

**An ADR for every module.** Every new module, meaning any new `.py` file with public
API, gets its own ADR in `docs/adr/`, written from `docs/adr/0000-template.md` with all
of its sections filled in:
- the problem from first principles, and the forces and constraints in play
- where the module sits in the system, with upstream and downstream relations and a
  diagram
- the decision
- **every abstraction**: purpose, invariants and key behaviour of each public type and
  function
- the **data flow**, as a mermaid diagram plus a step-by-step walk-through
- **every exception**: when it's raised, what it means, who should catch it and what
  they should do
- guarantees and invariants
- consequences, including the negatives
- alternatives considered and why they were rejected
- open questions
- a code map

Cross-cutting decisions get their own ADRs too, e.g. layering or the error model.

**Keep ADRs current.**
- When a module's behaviour changes, update its ADR in the same branch and add a line
  to its *History* section.
- Reversing a decision requires a new ADR that supersedes the old one.

**The wiki (`docs/wiki/`).** Keep the wiki in step with the code:
- each layer's page
- the end-to-end flow pages
- the glossary
- the error map
- the guides

New concepts get a glossary entry. New exceptions go into the error map. New extension
points get a how-to guide.

**Docstrings.** Every docstring has a runnable example and a sentence on where the code
fits in the system (see Code style).

**Check.** `uv run mkdocs build --strict` must pass, with no broken links or missing nav
entries.

## Decisions

Architecture decisions are recorded in `docs/adr/` (template: `docs/adr/0000-template.md`).
Read the ADRs before changing anything they cover; start with ADR-0001 (layering) and
ADR-0002 (error model).
