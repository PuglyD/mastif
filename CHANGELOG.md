# Changelog



All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the

project uses [Semantic Versioning](https://semver.org/) (see `CONTRIBUTING.md`).



## [Unreleased]



### Added



- Native vendor libraries (`kind: native`): `NativeLibrary` with required prototypes,
  thread-confined calls, `StatusCheck` and load-error hints; `FakeNativeLibrary` and
  `set_out` in mastif-testing; guide "Wrap a vendor DLL" (ADR-0035).
- Telnet transport (`kind: telnet`, via `telnetlib` / `telnetlib-313-and-up`) and SSH
  transports (`kind: ssh`, optional `mastif[ssh]` extra with paramiko): `SshSession` for
  command execution with real exit codes and stderr, and an interactive-shell stream.
  New built-in channel `mastif.ssh-shell`; `mastif.line-shell` accepts Telnet and SSH
  and drains already-waiting prompts on open; `ShellResult.stderr`;
  `mastif_testing.FakeSshSession` (ADR-0032 to ADR-0034).
- Licensing: mastif and mastif-testing are licensed AGPL-3.0-or-later, with a
  commercial licence available from the author (`LICENSE`, `NOTICE`, PEP 639 metadata).
  The dependency rule changes from "permissive only" to "AGPL-compatible" (ADR-0031).
- Workspace scaffold (`mastif`, `mastif-testing`), tooling, ADR process and contributor guide.

- `mastif.kernel`, covering:

  - units (`Quantity`, unit constants, dB arithmetic)

  - limits (`Range`, `Limits`, `IndexedLimits`, `evaluate`)

  - verdicts (`Verdict`, `aggregate`)

  - results (`Measurement`, `Check`, `Table`)

  - ids (`new_run_id`, `Position`)

  - the `MastifError` hierarchy

- `mastif.resources`:

  - contracts as plain Protocols, with structured `contract_problems`

  - `Identity` and `Health`

  - built-in std contracts

  - `@driver`/`@dut` with typed config, injected I/O and DUT channels

  - `Registry` with entry-point discovery

  - transports: TCP, serial, VISA, `LineIO`, `Scpi` and UDP `DatagramChannel`

  - built-in `mastif.udp` and `mastif.line-shell` channel drivers

- `mastif.station`: YAML `StationProfile` with sim overlay, `Station` as the composition root with role resolution and preflight checks, and `ResourceManager` covering ordered open, identity and health checks, rollback, safe state and close.

- `mastif-testing`: `FakeLineIO`, `FakeStream`, `FakeDatagramPeer`, `assert_satisfies`, `check_lifecycle`.



### Documentation

- Added a Vesper-compatible, Gruvbox-inspired syntax palette with distinct colours
  for keywords, functions, types, strings, numbers and decorators in dark and light modes.
- Added a workflow that builds the docs strictly and deploys to GitHub Pages only from
  `develop`, including manual deployments; pull requests build without deploying.
- Brought the diagram generator into the lint and type checks. Kept MkDocs snippet
  directives outside Python formatting while retaining checks on runnable examples.
- Reorganised the docs into Getting Started (intro and a tutorial ending in deployment) and
  Learn (concepts, system design, architecture as built, project status, operation, recipes).
- Rebuilt the homepage around a runnable quick start and the org-centric framing, with
  technology badges. Adopted the Vesper palette (dark by default), IBM Plex Sans and JetBrains Mono.
- Moved the Architecture section into Learn under `docs/learn/architecture/`, and gathered the
  overview and execution/runtime chapters into System design under `docs/learn/system-design/`.
  Learn covers fundamentals, system design, architecture as built, status and operations;
  the practical tutorial lives in Getting Started.
- Added generic framework requirements, the high-level concept system design and its
  diagram, architectural styles and patterns, and the distinction between evidence and
  application decisions to System design. Rewrote the architecture pages to match the
  course. Kept the separate platform-stack and station-deployment designs in a local
  archive, outside the publishable documentation history.
- Rewrote the complete Learn course from first principles, with the class-based `Task` design: 58 pages covering the tutorial,
  hardware integration, execution/runtime, station operation, recipes, and background.
  Added three runnable hardware-free examples and clearly labelled proposed author APIs,
  plan formats, CLI transcripts, and runtime behaviour for review.
- Added an editable tlDiagram architecture map with source-linked Python elements,
  evidenced relationships, responsibility-based drill-downs, and explicitly planned work.
  Every implemented layer expands to modules, classes, functions, members, and types,
  with connectors generated from the source AST and hand-written wording kept in `.tld/curated.yaml`.
- Added quick orientation summaries to every layer reference and documented the
  agreed single-page, collapsible Python-hierarchy layout in contributor instructions.
- Exposed private classes, functions, methods, and attributes in module reference pages.
- Enabled undocumented public members in the API reference, made unit constants
  individually discoverable, and documented public globals and aliases across both
  packages. Added reference coverage for health readings and the built-in driver tuple.
- Consolidated API references into one page per layer, with explicit peer links for
  every layer and a collapsible right-hand TOC using Python module, class, and member
  names. Removed editorial grouping headings and retained public/private symbol coverage.
- Standardised API reference source folders: every section now has its own `index.md`,
  with updated navigation and links and unchanged published section URLs.
- Collapsible nested sections in the right-hand table of contents, with accessible
  toggle buttons and automatic expansion for deep links.
- Fixed API example rendering by using recognised Google-style `Examples:` sections
  throughout both packages. Doctest prompts now render as highlighted Python sessions
  rather than nested blockquotes. Local previews also watch the reference source files.
- First documentation redesign slice for issue #1: reader-oriented navigation,
  an engineering walkthrough, a runnable measurement tutorial with Termynal playback,
  highlighted API signatures and symbol labels, and a focused identity/health reference.
- Reworked resource explanations and linked ADR-0022 to concepts and related decisions;
  clarified lifecycle guarantees against the current implementation. Added a shared
  documentation writing guide and contributor-agent instructions.

- Interactive diagrams: every Mermaid diagram can be zoomed, panned and opened
  fullscreen, in light and dark themes. Fixed seven diagrams that failed to render
  (ADR-0008, 0011, 0023, 0026 twice, 0035, and the station wiki page).

- ADR-0030 designs the execution topology: direct mode now (the test process owns the
  station), a shared station runtime later behind the same contracts, with the
  constraints the engine must respect. New wiki page: field notes.

- One comprehensive ADR per module (0003–0025), plus cross-cutting ADRs for layering (0001) and the error model (0002). These replace the earlier three summary ADRs.

- A wiki for new engineers, covering:

  - start here, architecture, and the life of a station

  - a page per layer

  - an error map and a glossary

  - guides for writing drivers, DUT types and station profiles, and for testing drivers

  - working on mastif, and the roadmap

- API reference pages generated from docstrings.

- `AGENTS.md` and `CONTRIBUTING.md` now require an ADR for every module and wiki updates in the same branch, and `mkdocs build --strict` is part of the checks.
- ADR-0026–0029 (infra), updates to ADR-0001, 0002, 0011 and 0023, an Infra wiki page and a bootstrap guide.
