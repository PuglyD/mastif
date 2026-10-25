# Roadmap and status

## Built

| Area | What exists | ADRs |
|---|---|---|
| Repository | uv workspace, ruff, ty, pytest + doctests, import-linter, mkdocs, git flow | 0001 |
| Licensing | AGPL-3.0-or-later plus commercial licence; AGPL-compatible dependency rule | 0031 |
| Runtime design | direct mode now, station runtime later (design only); field notes | 0030 |
| Kernel | units, limits, verdicts, results, ids, errors | 0002–0007 |
| Infra | Dynaconf settings by dependency injection, logging (Rich console, rotating file, tables), version and build info, bootstrap | 0026–0029 |
| Resources | contracts, std contracts, identity/health, `@driver`/`@dut`, registry, transports (TCP, serial, VISA, lines, SCPI, UDP, Telnet, SSH, native vendor libraries), built-in channels | 0008–0020, 0032–0035 |
| Station | profile with roles and sim overlay; composition root; resource manager | 0021–0023 |
| Testing kit | fakes; conformance helpers | 0024–0025 |

## Next: the test execution engine

These steps are planned in detail in [the plan](../plan.md), Part B.

1. **Author API.**
   - `Task` classes with `should_run`, `setup`, `run`, `on_fail` and `teardown` hooks.
   - `requires(role)` for hardware.
   - Typed context values (`needs`/`produces`).
   - `ctx.measure`, `ctx.check`, `ctx.table` and `ctx.prompt`.
2. **Plans and loops.**
   - A `plan.yaml` with org-defined loop types, each with enter and exit actions.
   - Pure plan expansion and loop-transition functions, with golden tests.
3. **Shared task runner and events.**
4. **Spike: own engine vs a pytest-based engine.** The result is recorded as an ADR.
5. **The engine itself.**
   - A run state machine.
   - Preflight checks (using `Station.role_problems`).
   - Policies, abort and pause.
   - A run store with snapshots, resume, and standalone task runs.
   - A minimal CLI.

The engine is built in **direct mode** (the test process owns the station) and must
honour the constraints in [ADR-0030](../adr/0030-execution-topology.md): hardware only
through `require(role, Contract)`, serialisable contract values, a `ResourceProvider`
interface, and per-run control leases.

## After the engine: the station runtime

Designed in [ADR-0030](../adr/0030-execution-topology.md), built once the engine works:

- one long-lived process owns the station; the executor and a control GUI use it at
  once through proxies implementing the same contracts
- commands on demand, opt-in monitors, a state store with sequence numbers
- control leases, and child-process hosting for crash-prone or 32-bit vendor DLLs

## Later

- The `mastif.api` facade, and `mastif-service` (REST + WebSocket).
- Artifacts, layered configuration and exporters.
- A `demo` SDK and test package, plus a project template.
- Multi-DUT slots: enforcing `shared`/`slot`, and per-slot roles.

## Under consideration

- **Spec-driven development.** Write each module's spec (its ADR draft plus acceptance
  tests) before any code.
