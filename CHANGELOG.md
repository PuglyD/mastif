# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/) (see `CONTRIBUTING.md`).

## [Unreleased]

### Added

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
