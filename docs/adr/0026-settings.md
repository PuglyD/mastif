# ADR-0026: Settings: one Dynaconf object, built once, passed explicitly

| | |
|---|---|
| **Status** | accepted |
| **Date** | 2026-10-25 |
| **Module(s)** | `mastif.infra.config` |
| **Layer** | infra |
| **Related** | ADR-0001 (the infra layer); ADR-0002 (`ConfigError`); ADR-0011/0023 (settings injected into drivers via the station); ADR-0027 (logging config can come from settings); ADR-0029 (bootstrap builds the settings) |

## 1. Summary

An application's configuration is loaded into **one Dynaconf object** (`Settings`) at
start-up, from:

- a config directory
- optional extra files
- code defaults
- environment variables

That object is then **passed explicitly** (dependency injection) to whatever needs it:
the station, drivers that ask for it, and later the engine. There is no global settings
object anywhere in mastif. For settings a component depends on, `section(settings, key,
Model)` returns a validated, typed Pydantic model. The one idea to remember: *build it
once, at the top; pass it down; read typed sections where structure matters.*

## 2. The problem, from first principles

- **There's a lot of configuration, and it comes from several places.** Station names,
  default timeouts, paths to limit files, operator options and org-specific knobs live
  in files. Some values must be overridden per machine (an environment variable on one
  station), or per stage (development vs production).
- **Loading and merging is a solved problem.** Dynaconf reads toml, yaml, json and ini,
  merges nested sections, applies environment-variable overrides and supports
  per-stage sections. Re-implementing that would be wasted effort.
- **Global configuration objects cause real damage:**
  - Code that reads `from app import settings` can't be tested with different
    settings without monkey-patching.
  - Two tests that change the global interfere with each other.
  - Nobody can tell which code depends on which settings.

  The old project had the same tension. This design keeps Dynaconf's power and drops
  the global.
- **Untyped access hides typos.** `settings.station.retires` simply reads as missing.
  For settings that matter, structure should be declared and validated up front.
- **Broken files must fail at start-up.** Dynaconf loads lazily, so a malformed file
  would otherwise surface on first access, possibly mid-run.

## 3. Where it sits in the system

```mermaid
flowchart LR
    files["config dir (*.toml, *.yaml, ...) + extra files"] --> cs[create_settings]
    defaults[code defaults] --> cs
    env["environment: PREFIX_SECTION__KEY"] --> cs
    cs --> S[(Settings)]
    S -->|passed explicitly| st["Station.build(settings=)"]
    st -->|injected| drv["drivers with __init__(..., settings: Settings)"]
    S -->|section(key, Model)| typed[validated models]
    S --> logs[resolve_logging_config]
    S -->|as_dict| manifest[run manifest - planned]
```

- **Layer:** infra. It does file and environment I/O, so it can't live in the kernel,
  but drivers (resources layer) must be able to receive it.
- **Upstream:** `bootstrap`, `Station.build`, driver construction, logging resolution,
  and the planned engine.
- **Downstream:** Dynaconf and Pydantic.

## 4. Decision

1. **`Settings` is Dynaconf's `Dynaconf` class itself.** It is exposed under a mastif
   name for annotations, so users keep all of Dynaconf: dotted access, `get(key,
   default)`, validators, environments.
2. **`create_settings(...)`** builds it. Sources, from lowest to highest precedence:

   | Precedence | Source |
   |---|---|
   | 1 (lowest) | `defaults`, a mapping, passed to Dynaconf as upper-case keyword arguments |
   | 2 | every `*.toml/*.yaml/*.yml/*.json/*.ini` in `config_dir`, in sorted filename order (`config_files`) |
   | 3 | `files`, explicit extra files, in the order given |
   | 4 (highest) | `.env` (when `load_dotenv`), then environment variables `<envvar_prefix>_KEY`, with `__` for nesting |

   `merge_enabled=True`, so nested sections merge across sources rather than being
   replaced.
3. **Explicit, sorted file order.** Number file names (`00-base.toml`, `10-site.yaml`)
   to control precedence. No implicit discovery beyond the top level of the directory.
4. **`environments=False` by default.** With it on, Dynaconf ignores every key outside
   `[default]`/`[<env>]` sections, which silently drops flat files. Turning it on is a
   deliberate choice.
5. **Fail at start-up.** `create_settings` forces Dynaconf to load immediately. Missing
   paths and parse errors raise `ConfigError`.
6. **Typed sections.** `section(settings, key, model)` reads a dotted key, converts
   Dynaconf boxes to plain data, validates it into a Pydantic model, and reports every
   invalid field.
7. **Export.** `as_dict(settings)` gives a plain dict with lower-case top-level keys,
   excluding Dynaconf's own option keys, for run manifests.
8. **Default env prefix `MASTIF`.** Orgs should choose their own, e.g. `ACME`.
9. **No global, ever.** mastif never creates or reads a module-level settings object.
   The station keeps the one it was given as `station.settings`.

## 5. Abstractions

| Name | Purpose | Invariants and behaviour |
|---|---|---|
| `Settings` | The settings type (`dynaconf.Dynaconf`) | Annotate injectable parameters with it. |
| `create_settings(config_dir=None, *, files=(), defaults=None, envvar_prefix="MASTIF", environments=False, env=None, load_dotenv=False)` | Build the settings | Precedence as in point 2. Raises `ConfigError`. Two calls give two independent objects. |
| `config_files(config_dir)` | The files a directory contributes, in load order | Top level only. Supported suffixes only. Sorted by name. |
| `section(settings, key, model)` | Typed, validated view of one section | Raises `ConfigError` when missing or invalid. Returns a new model each call. |
| `as_dict(settings)` | Plain-dict export | JSON-friendly. Excludes Dynaconf internals. |
| `CONFIG_SUFFIXES`, `DEFAULT_ENVVAR_PREFIX` | Constants | — |

## 6. Data flow

```mermaid
sequenceDiagram
    participant App as Application entry point
    participant C as create_settings
    participant D as Dynaconf
    participant St as Station.build
    participant Drv as Driver
    App->>C: create_settings("config/", defaults=..., envvar_prefix="ACME")
    C->>C: config_files → [00-base.toml, 10-site.yaml]
    C->>D: Dynaconf(settings_files=[...], DEFAULTS..., merge_enabled=True)
    C->>D: as_dict() (force load; errors → ConfigError)
    C-->>App: settings
    App->>St: Station.build(profile, registry, settings=settings)
    St->>Drv: __init__(cfg, io, settings=settings)
    Drv->>Drv: section(settings, "acme.psu", PsuDefaults)
```

**Failure paths:**

- A malformed file raises `ConfigError("cannot load settings: TOMLDecodeError: ...")`.
- A missing or invalid section raises `ConfigError("setting 'station' is invalid:
  name: Field required")`.

## 7. Errors

| Exception | Raised when | Meaning | Who catches it, and what they do |
|---|---|---|---|
| `ConfigError` | the config directory or an explicit file is missing; a file can't be parsed; `section` finds a missing or invalid section | the configuration is wrong | The application entry point shows it and exits. Fix the file. |
| `ResourceError` → `StationError` | a driver asks for settings, but the station was built without them | the application forgot to pass settings | Pass `settings=` to `Station.build`. |

## 8. Guarantees and invariants

- Precedence is fixed and documented (point 2).
- `create_settings` either returns fully loaded settings or raises.
- No module-level settings object exists. Independent settings objects never interfere.
- `section` never returns partially valid data.

## 9. Consequences

- **Positive:**
  - Dynaconf's full power with none of the global-state problems.
  - Testable: build a settings object per test with `defaults=`.
  - Dependencies on settings are visible in signatures.
- **Negative:**
  - Settings must be threaded through constructors, so there is a bit more plumbing
    than with a global.
  - mastif is coupled to Dynaconf's API (accepted: it's the decision).
  - Environment variables are read at creation, so later changes need a new settings
    object.
- **Risks:** code reaching for `settings` deep inside utilities. Pass the specific
  value, or a typed section, instead of the whole object, where practical.

## 10. Alternatives considered

- **A module-level global settings object:** rejected (section 2). Tests interfere,
  and dependencies are hidden.
- **A thin mastif wrapper class around Dynaconf:** rejected by decision. It hides useful
  Dynaconf features for little insulation.
- **Pydantic-settings instead of Dynaconf:** rejected. Dynaconf was chosen for its
  multi-format, layered and environment-aware loading. Typed access is still available
  through `section`.
- **Copying the old project's helper:** rejected under the from-scratch rule. Its ideas
  were kept and its pitfalls fixed: `environments=True` by default dropped flat keys,
  and logging was configured as a side effect of loading settings.

## 11. Open questions and future work

- Settings validation via Dynaconf validators declared by org SDKs.
- Reloading settings during a long-running service.
- A settings section for the engine (timeouts, policies) once it exists.

## 12. Code map

| What | Where |
|---|---|
| Implementation | `packages/mastif/src/mastif/infra/config.py` |
| Tests | `packages/mastif/tests/infra/test_config.py`, plus doctests |
| Injection | `packages/mastif/src/mastif/resources/driver.py` (`settings_param`), `packages/mastif/src/mastif/station/station.py` |
| Wiki | `docs/wiki/infra.md`, `docs/wiki/guides/bootstrap-an-application.md` |

## History

- 2026-10-25: created.
