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

- Added an editable tlDiagram architecture map with source-linked Python elements,
  evidenced relationships, responsibility-based drill-downs, and explicitly planned work.
  Every implemented layer expands to modules, classes, functions, members, and types,
  with connectors generated from the source AST and hand-written wording kept in `.tld/curated.yaml`.
- Exposed private classes, functions, methods, and attributes in module reference pages.
- Enabled undocumented public members in the API reference, made unit constants
  individually discoverable, and documented public globals and aliases across both
  packages. Added reference coverage for health readings and the built-in driver tuple.
- Split API reference modules into dedicated pages under collapsible layer categories;
  added nested Transport and Channel navigation, with overview pages and ADR links.
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
