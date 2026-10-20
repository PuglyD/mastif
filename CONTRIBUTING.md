# Contributing to mastif

This guide covers how code gets into mastif: branches, commit messages, versions and
review. The engineering rules (clean-room, layering, code style, tests) are in
[`AGENTS.md`](AGENTS.md). Read both before your first change.

---

## 1. Development setup

```bash
uv sync                                   # create .venv with all workspace packages
uv run pytest                             # unit tests + docstring examples (doctests)
uv run ruff check . && uv run ruff format --check .
uv run ty check                           # static types
uv run lint-imports                       # layer boundaries
```

All five commands must pass before a branch is merged.

---

## 2. Branching model: git flow

| Branch | Branches from | Merges into | Purpose |
|---|---|---|---|
| `main` | — | — | Released code only. Every commit on `main` is a tagged release. |
| `develop` | `main` | — | Integration branch. Always green; the next release is cut from here. |
| `feature/<topic>` | `develop` | `develop` | One feature or change, e.g. `feature/resource-manager`. |
| `release/<x.y.z>` | `develop` | `main` **and** `develop` | Release stabilisation: version bump, changelog, fixes only. |
| `hotfix/<x.y.z>` | `main` | `main` **and** `develop` | Urgent fix to a released version. |

Rules:

- Never commit directly to `main` or `develop`. Work on a `feature/*` branch.
- Name branches in lowercase kebab-case: `feature/datagram-channel`, `hotfix/0.3.1`.
- Merge `release/*` and `hotfix/*` branches with `--no-ff`, so the merge itself marks the release.
- Keep feature branches short-lived. Rebase onto `develop` when it moves (`git rebase develop`).
  Squash-merge them, or merge them with `--no-ff` if their commits are each meaningful.
- Delete a branch once it is merged.

Typical feature flow:

```bash
git switch develop && git pull
git switch -c feature/resource-manager
# ... commits ...
git switch develop && git merge --no-ff feature/resource-manager
git branch -d feature/resource-manager
```

Typical release flow:

```bash
git switch -c release/0.2.0 develop
# bump versions, update CHANGELOG.md, fix only what blocks the release
git switch main    && git merge --no-ff release/0.2.0 && git tag -a v0.2.0 -m "v0.2.0"
git switch develop && git merge --no-ff release/0.2.0
git branch -d release/0.2.0
```

---

## 3. Commit messages: Conventional Commits

Every commit message follows [Conventional Commits 1.0.0](https://www.conventionalcommits.org/):

```
<type>(<scope>)<!>: <summary>

<body: what and why, wrapped at 72 columns>

<footers: BREAKING CHANGE: ..., Refs: #123>
```

**Types**

| Type | Use for | Version effect |
|---|---|---|
| `feat` | A new capability for users or SDK authors | minor |
| `fix` | A bug fix | patch |
| `perf` | A performance improvement with no behaviour change | patch |
| `refactor` | A code change that is neither a fix nor a feature | none |
| `docs` | Documentation only (including docstrings and ADRs) | none |
| `test` | Adding or fixing tests | none |
| `build` | Packaging, dependencies, `pyproject.toml`, `uv.lock` | none |
| `ci` | CI configuration | none |
| `chore` | Repository housekeeping | none |
| `revert` | Reverting an earlier commit | depends |

**Scopes** follow the package layers: `kernel`, `resources`, `station`, `engine`, `events`,
`api`, `cli`, `service`, `testing`, `examples`, `docs`, `adr`. Leave the scope out for
changes that span the whole repository.

**Breaking changes:** add `!` after the type or scope and a `BREAKING CHANGE:` footer
explaining how to migrate.

**Summary line:** imperative mood ("add", not "added"), lowercase, no full stop, at most 72 characters.

Examples:

```
feat(kernel): add IndexedLimits for per-channel acceptance ranges

fix(kernel): keep low side failing when only warn_high is given

Limits.between left the warning range unbounded below when only
warn_high was supplied, so values far below the passing range were
judged WARN instead of FAIL.

feat(engine)!: rename Task.prepare to Task.setup

BREAKING CHANGE: org task classes must rename `prepare` to `setup`.
```

---

## 4. Versioning: Semantic Versioning

mastif follows [SemVer 2.0.0](https://semver.org/): `MAJOR.MINOR.PATCH`.

- **MAJOR**: incompatible change to the public API. That means anything exported from
  `mastif.api`, `mastif.ext` or `mastif.kernel`, the event schema, the plan/station
  YAML formats, or the network API.
- **MINOR**: backwards-compatible new functionality.
- **PATCH**: backwards-compatible bug fixes.

Rules:

- **While the version is `0.y.z`**, the public API is not yet stable. Breaking changes bump
  MINOR, and everything else bumps PATCH.
- **The packages are versioned in lockstep.** All workspace packages (`mastif`,
  `mastif-testing`, and later `mastif-service`) always share one version number.
- **Version numbers are written in PEP 440 form** in `pyproject.toml`, and as the SemVer
  equivalent in tags and the changelog:

  | SemVer (tags, changelog) | PEP 440 (`pyproject.toml`) |
  |---|---|
  | `1.2.0-rc.1` | `1.2.0rc1` |
  | `1.2.0-beta.2` | `1.2.0b2` |
  | `1.3.0-dev` (unreleased work on `develop`) | `1.3.0.dev0` |

- **Tags are `vX.Y.Z`**, annotated, and only on `main`.
- **The bump level comes from the Conventional Commit types** since the last tag (see the
  table in section 3).
- **The event schema and file formats carry their own `schema_version`.** It is bumped
  whenever their shape changes, so stored runs from older versions can still be read or
  migrated.

---

## 5. Changes that need an ADR

Write an Architecture Decision Record in `docs/adr/`, copied from `0000-template.md`, when a change:

- adds or changes a public extension point (contracts, drivers, loops, events)
- changes a stored or transmitted format (events, snapshots, station or plan YAML)
- adds a runtime dependency
- reverses or amends an existing ADR

Number ADRs sequentially. Never edit an accepted ADR's decision; supersede it with a new one.

---

## 6. Pull request / merge checklist

- [ ] The branch name follows git flow, and the commits follow Conventional Commits.
- [ ] `pytest`, `ruff`, `ty` and `lint-imports` all pass.
- [ ] New public functions have Google-style docstrings with a runnable `Example:` and
      context on where they fit (see `AGENTS.md`).
- [ ] Tests use fakes, not mocks. Pure functions have direct unit tests.
- [ ] There's an ADR if section 5 applies.
- [ ] No employer or customer identifiers; reference projects used for inspiration only, nothing pasted.
- [ ] Any new dependency has a permissive licence.
