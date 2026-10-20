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
