# Working on mastif

How to make a change that will be accepted. The binding rules are in `AGENTS.md`
(engineering and documentation) and `CONTRIBUTING.md` (git flow, commits, versioning).

## The definition of done

A change is done when **all** of the following are true:

1. **Code** sits in the right layer (ADR-0001) and raises typed errors (ADR-0002).
2. **Docstrings** on every function are Google style, with a runnable `Example:` and a
   sentence on where the code fits.
3. **Tests** use fakes, not mocks. Every test has a docstring saying what it pins down
   and why that matters.
4. **An ADR** exists for every new module, with all sections of the
   [template](../adr/0000-template.md) filled in. Changed modules get their ADR updated,
   plus a *History* line.
5. **The wiki** is updated: the layer page, the flows, the [glossary](glossary.md) for
   new terms, the [error map](errors.md) for new exceptions, and a guide for new
   extension points.
6. **Every check passes:**

   ```bash
   uv run pytest                     # unit tests + doctests
   uv run ruff check . && uv run ruff format --check .
   uv run ty check
   uv run lint-imports
   uv run mkdocs build --strict
   ```

## Adding a new module: a checklist

```mermaid
flowchart LR
    a[Write ADR draft: problem, place, abstractions, flow, errors] --> b[Implement with docstrings + doctests]
    b --> c[Unit tests with fakes]
    c --> d[Finalise ADR: code map, consequences]
    d --> e[Wiki: layer page, glossary, errors, guide]
    e --> f[mkdocs nav + ADR index]
    f --> g[All checks green → Conventional Commit on feature branch]
```

Writing the ADR draft **before** the code is encouraged. It's the cheapest place to
find a design problem.

## Conventions worth memorising

- **Models:** Pydantic v2, `ConfigDict(extra="forbid", frozen=True)`.
- **No import-time side effects.** Never register things globally.
- **Pure decision functions,** with I/O at the edges and injected.
- **Errors:** subclass the layer's base error. Messages start with the subject. Chain
  causes with `raise ... from exc`.
- **Physical values are `Quantity`.** Timeouts are float seconds.
- **Names:** org ids are `org.name`, in lowercase.
- **Examples** use the fictional orgs `demo` and `acme` and simulated devices. Never
  real company or product names.

## Branches and commits

```bash
git switch develop
git switch -c feature/<topic>
# ... work, with Conventional Commits:  feat(station): ..., docs(adr): ..., test(kernel): ...
git switch develop && git merge --no-ff feature/<topic>
```

Versions follow SemVer. While the version is `0.y.z`, breaking changes bump the minor
version. See `CONTRIBUTING.md`.

## Doctests

Every `>>>` example in a docstring is run by `uv run pytest`. If you change behaviour
and forget an example, CI tells you. For examples that need real hardware, use a prose
code block (indented, without `>>>`) instead.

## Diagrams

Diagrams are Mermaid, written in ```` ```mermaid ```` fences. The docs render them with
their own viewer (`docs/javascripts/diagrams.js`) instead of Material's built-in one,
because Material draws them into a closed shadow root that can't be zoomed. Every
diagram gets:

- **+ / − / ↺ / ⛶** buttons: zoom in, zoom out, fit, fullscreen
- **drag** to pan, **Ctrl+scroll** to zoom (plain scroll in fullscreen), **double-click**
  for fullscreen, **Esc** to close it
- keyboard, once the diagram has focus: `+` `-` `0` `f` and the arrow keys
- light and dark themes following the palette toggle

Two Mermaid pitfalls have broken diagrams here before:

- **No `;` in sequence-diagram messages.** Mermaid treats `;` as the end of a
  statement, so `A->>B: open(); close()` is a syntax error. Write `open(), then close()`.
- **Quote edge labels that contain parentheses or brackets:** `A -->|"section(key)"| B`.

A diagram that fails to parse shows the error and its source in place of the drawing,
so check the pages you touched with `uv run mkdocs serve`.
