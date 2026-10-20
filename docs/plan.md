# mastif-oss: Step 1, the execution engine and instrument/DUT primitives

## Context
mastif is being rebuilt as a generic ATE product. The full product has a domain-neutral **core**, a **generic API** (Python plus an optional service), and org-written SDKs and UIs on top. Development happens in a **clean new repo** at `D:\Documents\Coding projects\DanU\mastif-oss`:
- no code or material from earlier employer-owned projects is copied
- only general design ideas from the past sessions are reused
- the old `mastif/` stays untouched

The full roadmap is too big to tackle at once. This plan covers only the first two pillars:
1. **Instrument and DUT handling primitives**
2. **The test execution engine**

It also covers the minimum bootstrap and kernel they depend on. Out of scope for now: the service/REST API, artifacts, layered config with selectors, exporters, UI and packaging templates.

**Decisions already made:**
- **Author API:** sync. Tasks and drivers use plain blocking methods; the engine is async inside.
- **Contracts:** plain `typing.Protocol`. Drivers are classes marked with `@driver(...)`.
- **DUT:** a resource with named channels.
- **Multi-DUT:** designed for but not built (`slot` ids run through every model).
- **Engine base:** chosen by a spike, own engine vs pytest-based.
- **Python:** 3.12+.
- **License:** undecided, so the repo is "All rights reserved" for now.
- **Dependencies:** permissive licences only.

---

## Step 0: Bootstrap the repo
- `git init` with the personal email, then set up a uv workspace with `packages/mastif` and `packages/mastif-testing`.
- Tooling: ruff (line length 100), ty, pytest, import-linter.
- `AGENTS.md` and `CLAUDE.md` must cover:
  - clean-room rules (no employer identifiers, nothing copied from old repos)
  - layering rules
  - NumPy docstrings
  - Pydantic v2 with `extra="forbid"`
  - fakes over mocks
- `docs/adr/` with the ADR template; mkdocs-material skeleton.
- Root `NOTICE`: "Copyright (c) 2026 <user>. All rights reserved."

## Step 1: Minimal kernel (`mastif/kernel/`)
Only what the engine and resources need.
- `units.py`:
  - a small `Quantity(value, unit)` with an SI table and conversion
  - constants such as `V, mV, A, mA, Hz, kHz, MHz, GHz, s, ms, dB, dBm, W` so authors can write `12 * V`
  - log units (dB/dBm) are not converted to linear units
  - type aliases `Volts`, `Amps`, `Hertz` (all `Quantity`) as documentation hints
  - an ADR records why this is home-grown and not pint (size and startup cost); pint can be swapped in later behind the same API
- `limits.py`:
  - `Range(low, high, inclusive=True)`
  - `Limits(passing: Range, warning: Range | None)`
  - `IndexedLimits(by_index, default)`
  - a pure `evaluate(value, limits) -> Verdict`
- `verdict.py`:
  - the `Verdict` enum: PASS, WARN, FAIL, ERROR, SKIPPED, ABORTED
  - `aggregate()` with precedence ERROR > FAIL > WARN > PASS
  - SKIPPED is ignored unless every child was skipped; ABORTED dominates
- `results.py`:
  - result types `Measurement`, `Check` and `Table` (with per-cell and per-row verdicts)
  - a Measurement's verdict is always computed from its value and limits, never passed in
- `errors.py`: the `MastifError` hierarchy (see resources and engine below).
- `ids.py`: `RunId`, `SlotId` (default `"0"`), `Position`.

---

## Part A: Instrument and DUT primitives (`mastif/resources/`, `mastif/station/`)

### A1. Contracts: zero ceremony
```python
class PowerSupply(Protocol):  # org code, no mastif import required
    def set_voltage(self, v: Volts) -> None: ...
    def read_current(self) -> Amps: ...
```
- A contract is any `Protocol`.
- `@contract(safe_state="disable_output")` is optional metadata that names the method used to reach a safe state.
- `mastif.resources.std` holds opt-in built-in contracts:
  - `PowerSupply`, `SignalSource`, `Switch` (`route(a, b)`), `Relay`, `DigitalIO`, `Axis`
  - `Shell` (`execute(cmd) -> ShellResult`)
  - `MessageChannel` (`send`, `request(msg, match, timeout)`, `subscribe(handler)`)
- The built-in contracts are kept deliberately small. Orgs are expected to write their own.

### A2. Drivers
```python
@driver("acme.psu-x", provides=[PowerSupply])
class PsuX:
    class Config(DriverConfig):  # pydantic, extra=forbid
        transport: TcpConfig
        channel: int = 1

    def __init__(self, cfg: Config, io: Scpi): ...
    # optional lifecycle hooks, detected structurally:
    def open(self) -> None: ...
    def identify(self) -> Identity: ...
    def health(self) -> Health: ...
    def safe_state(self) -> None: ...
    def close(self) -> None: ...
```
- `@driver` only attaches a `DriverSpec` to the class (`__mastif_driver__`). Importing a driver module has **no global side effects**.
- When decorated, `@driver` checks that the class structurally satisfies every contract in `provides` (method names and arity) and raises `ContractMismatch` if not. ty provides the static check.
- **Dependency injection:** the runtime builds transports and helpers from `Config.transport` and injects them according to the `__init__` annotations (`io: Scpi`, `raw: LineIO`, `dgram: DatagramChannel`).
  - In sim or tests, a fake transport is injected instead.
  - A driver that wants no transport simply omits the parameter.
- **Composite resources:** a driver may expose `children() -> dict[str, object]`, for example a positioner controller and its axes.
  - The parent owns the shared transport; the children borrow it.
  - Roles can bind to `parent.child`.

### A3. DUTs: resources with channels
```python
@dut("demo.widget-board", state=WidgetState)
class WidgetBoard:
    console: Shell = channel()
    ctrl: MessageChannel = channel()

    def identify(self) -> DutIdentity: ...  # serial, part_number, revision, extra
    def boot(self) -> None: ...  # org-defined product methods
```
- A DUT is a resource with the same lifecycle and identity check as an instrument.
- `channel()` declares a named, typed channel. The station profile maps each channel to a transport-backed channel implementation, either real or sim.
- Channels open in declaration order and close in reverse. If any open fails, the ones already opened are rolled back.
- `state`: a typed Pydantic model. The engine captures it into the run snapshot.
- Identity can come from `identify()`, from the run request (an operator-scanned serial), or both. A mismatch fails before any test runs.

### A4. Transports (`resources/transports/`)
- Configs form a discriminated union: `TcpConfig`, `UdpConfig`, `SerialConfig` (pyserial extra) and `VisaConfig` (pyvisa extra).
- Layers:
  - `StreamTransport`: raw bytes.
  - `LineIO`: terminator, `write`, `query`, timeouts.
  - `Scpi(LineIO)`: `query_float`, `*IDN?` → `Identity`, error-queue check.
  - `DatagramChannel`: an asyncio endpoint on one background thread, a sync facade, handler fan-out, `request(match, timeout, retries)` using futures, and a matcher that correlates each reply with its request.
- Every transport logs its I/O trace through an injected logger. There are no module-level loggers.

### A5. Errors
`ResourceError` → `TransportError`, `TimeoutError`, `ProtocolError`, `IdentityMismatch`, `ContractMismatch`, `ResourceFault`.
- Drivers raise these errors. They never return sentinel values.
- Any exception that is not a `ResourceError` is still turned into a task ERROR. Exceptions are never swallowed.

### A6. Registry and discovery (`resources/registry.py`)
- The entry-point group `mastif.drivers` points to org modules.
- `Registry.discover()` imports those modules and collects the classes that carry `__mastif_driver__`/`__mastif_dut__`.
- Discovery happens only when explicitly called, separately from activation.
- Tests can build a `Registry` directly from a list of classes.

### A7. Station profile and resource manager (`station/`)
```yaml
station: bench-01
resources:
  bench_psu: {driver: acme.psu-x, config: {transport: {kind: tcp, host: 10.0.0.5, port: 5025}},
              expect: {serial: "A123"}, shared: false}
  dut:       {dut: demo.widget-board,
              channels: {console: {kind: serial, port: COM3, baud: 115200},
                         ctrl:    {kind: udp, host: 192.168.1.50, port: 9000}}}
roles: {psu_main: bench_psu, dut: dut}
sim:   {bench_psu: {driver: demo.psu-sim}, dut: {dut: demo.widget-sim}}
```
- The profile is a Pydantic model. It contains facts only; control flow stays in Python.
- `Station.build(profile, registry, sim=False) -> Station` acts as the composition root. It validates driver ids and configs and checks that each role's resource provides the contract its tasks require.
- `ResourceManager` handles the lifecycle:
  - opens resources in profile order, then runs identify, the `expect` check and health
  - rolls back on failure and closes in reverse order
  - `safe_state_all()` on abort, error or run end
  - session scope is per run by default (a per-resource `scope: run|task` setting is planned)
- `shared` and `slot` fields exist in the model now. The parallel-slot locking that uses them is deferred.

### A8. Testing kit (`packages/mastif-testing`)
- `FakeLineIO` and `FakeScpi`: scripted request→response pairs, with assertions on what was sent.
- `FakeDatagramPeer`: a fake UDP peer on loopback.
- `assert_satisfies(cls, Contract)`.
- `lifecycle_conformance(driver_cls, cfg, fake_io)`: a reusable pytest helper that org SDKs run against their own drivers.

---

## Part B: Test execution engine (`mastif/engine/`, author surface in `mastif/api/`)

### B1. Author API (engine-independent and frozen before the spike)
```python
class RxGain(TaskConfig):
    target: Quantity = 20 * dB


class MeasureGain(Task[RxGain]):
    id = "measure_gain"
    needs = (Calibration,)  # ContextValue types
    produces = (GainResult,)
    psu: PowerSupply = requires("psu_main")
    board: WidgetBoard = requires("dut")

    def should_run(self, ctx) -> Skip | None: ...
    def setup(self, ctx): ...
    def run(self, ctx):
        with ctx.step("sweep"):
            g = ...
            ctx.measure("gain", g, Limits(Range(18 * dB, 22 * dB)))
            ctx.require(...) / ctx.check(...) / ctx.table(...)
        ctx.outputs.put(GainResult(...))

    def on_fail(self, ctx, outcome): ...
    def teardown(self, ctx): ...  # always runs
```
- **Hook order:** should_run → setup → run → (on_fail if the task fails or errors) → teardown.
- **Outcomes:**
  - a plain `assert` produces FAIL
  - `ctx.require` raises `StopTask` (FAIL)
  - any other exception produces ERROR
- The `ctx` API:
  - `ctx.prompt(msg, choices|schema, timeout)` blocks until an operator answers
  - `ctx.checkpoint()` is a cooperative abort/pause point inside long tasks
  - `ctx.position` holds the current loop values
  - `ctx.dut_state` holds the DUT's state

### B2. Plan model and loops (`engine/plan.py`, `engine/loops.py`)
```yaml
name: demo-board-acceptance
loops:
  profile:  {type: demo.firmware_profile, values: [std, lowpower]}   # org loop (enter = reflash/restart)
  channel:  {type: values, values: [1, 2, 3]}                         # built-in, no actions
order: [profile, channel, task]
sequence:
  - task: power_on
    when: {channel: first}
  - task: measure_gain
  - task: shutdown
    when: {channel: last}
policies: {on_fail: continue, on_error: stop_loop:profile, retries: 0}
```
- The core ships only the `values` loop type, which has no enter/exit actions. Orgs register loop types (`@loop("demo.firmware_profile")`) that implement:
  - `values(request, station)`
  - `enter(value, ctx)`
  - `exit(value, ctx)`
  - `can_change_inline(prev, next)`
- **Expansion is a pure function:** `expand(plan, request) -> ExecutionPlan`, an ordered list of `Item(position, task_id, slot)`.
- **Transitions are a pure function:** `transitions(prev_pos, next_pos)` exits innermost-first, then enters, and only for loops whose value changed.
- Both functions get golden tests (task-first vs loop-first ordering, and `when` rules).

### B3. Shared task runner (`engine/runner.py`): the same code serves both spike variants
- `run_item(item, station, context, sink) -> ItemOutcome`:
  - resolves `requires` from the station roles
  - validates `needs` against the context store
  - runs the hooks in order, records results and computes the verdict
  - emits events
- Tasks run on a single worker thread. The engine's async side owns events, prompts and abort handling.
- `ContextStore` holds typed `ContextValue` (Pydantic) entries keyed by (type, scope position). It serialises to JSON.

### B4. Events (`mastif/events/`)
- Events form a Pydantic discriminated union. Each event carries `seq`, `ts`, `run_id`, `slot`, `position`.
- Event types:
  - run: `RunStarted`, `PreflightFinished`, `RunFinished`
  - loops: `LoopEntered`, `LoopExited`
  - tasks and steps: `TaskStarted`, `TaskFinished`, `StepStarted`, `StepFinished`
  - results: `ResultRecorded` (measurement, check or table)
  - operator: `PromptRequested`, `PromptAnswered`
  - resources: `ResourceOpened`, `ResourceFault`
  - other: `Log`
- `EventSink` is a protocol with an NDJSON file sink and an in-memory sink. `mastif schema events` exports the JSON Schema.

### B5. Spike: own engine (A) vs pytest-based (B) (`spikes/engine_choice/`)
- Both variants consume the same `ExecutionPlan` and `run_item`. Only the driving loop differs:
  - **A:** a plain scheduler loop with an explicit state machine.
  - **B:** a pytest plugin whose collector maps `Item`s to `pytest.Function` nodes, with transitions applied in `pytest_runtest_setup`. It runs as a subprocess.
- **Test scenario:** the demo plan above, plus a prompt, a deliberately failing task and a forced crash mid-run that is then resumed.
- **Scoring criteria:**
  - resume correctness
  - event fidelity
  - transitions correct in both loop orders
  - standalone task runs
  - ability to embed in a future service
  - quality of tracebacks and debugging
  - dependence on pytest internals
  - line count
- The outcome is recorded in an ADR, and the losing variant is deleted.

### B6. Engine proper (the chosen variant)
- **Run state machine:** Created → Preflight → Running ⇄ Paused → Aborting → SafeState → Finished(verdict).
  - Loop exits and `safe_state_all()` are explicit states, not best-effort `finally` blocks.
- **Preflight** runs before any hardware moves. It checks that:
  - the plan is valid
  - every role is bound and its resource provides the required contract
  - every `needs` has a producer earlier in the expansion or in the supplied context
  - task configs validate
  - org loop types exist
- **Policies:** `on_fail`/`on_error` can be `continue`, `stop_loop:<name>` or `stop_run`, with optional `retries`.
- **Abort and pause:** requested through the control channel and honoured at item boundaries and at `ctx.checkpoint()`.
- **Run store** (`engine/store.py`), one run folder per run containing:
  - `events.ndjson` (append-only, flushed after every event)
  - `snapshot.json`, written atomically (temp file + rename) after every item: completed items, context store, DUT state
  - `manifest.json`: frozen plan, request, station-profile hash and package versions
  - `report.json`, built from the events by a pure reducer
- **Resume:** reload the manifest, re-expand the plan, skip completed items, enter every loop at the resume position, then continue.
- **Standalone task:** `mastif task <id> --station ... [--context-from <run> | --context-file f.json]`. A task with unmet `needs` is SKIPPED with a reason.
- **Minimal CLI** (`mastif/cli/`): `mastif validate | run | resume | task | schema`. Prompts are answered on stdin. The control channel is designed so a service can drive it later.

---

## Demo (proves both parts; `examples/`)
- `demo_sdk`, a fictional org:
  - a `demo.psu-sim` driver implementing std `PowerSupply`
  - a `demo.widget-sim` DUT with `console: Shell` and `ctrl: MessageChannel`; the latter runs over a local UDP fake peer, which exercises `DatagramChannel`
  - the `demo.firmware_profile` loop type
  - sim and "real" (loopback) station profiles
- `demo_tests`: 3–4 Tasks plus `plan.yaml`, registered through the `mastif.test_packages` entry point.

## Execution order
0 Bootstrap → 1 Kernel → A1–A8 Resources (each with tests) → B1–B4 → B5 Spike + ADR → B6 Engine → Demo.

## Verification
- `uv run pytest`, `ruff check` and `ty check` all pass. import-linter enforces: `kernel` ← `resources` ← `station` ← `engine` ← `api`/`cli`, with nothing importing `examples`.
- **Unit and golden tests:**
  - unit conversions
  - `evaluate` and `aggregate`
  - `@driver` contract mismatch detection
  - profile validation errors
  - `ResourceManager` rollback when the second resource fails to open
  - `DatagramChannel` request/response matching against `FakeDatagramPeer`
  - `expand`/`transitions` golden tests
- **End-to-end:**
  1. `mastif validate examples/demo_tests/plan.yaml --station examples/demo_sdk/station.yaml --sim`.
  2. `mastif run ... --sim` produces a run folder whose verdict matches the expected one; the deliberately failing task gives FAIL with `on_fail` executed.
  3. Kill the process mid-run, run `mastif resume <id>`, and check the final `report.json` equals that of an uninterrupted run (golden test).
  4. `mastif task measure_gain --context-from <id>` runs standalone; without context it is SKIPPED.
  5. Abort during a prompt: the loop exits and `safe_state` events appear, and the verdict is ABORTED.
- **Clean-room check:** grep for former-employer identifiers (the term list is kept outside this repo) returns nothing.
