# ADR-0022: Resource manager: the safety-critical lifecycle, done once

| | |
|---|---|
| **Status** | accepted |
| **Date** | 2026-10-21 |
| **Module(s)** | `mastif.station.manager` |
| **Layer** | station |
| **Related** | [ADR-0010](0010-identity-and-health.md) supplies verification reports; [ADR-0011](0011-drivers-and-duts.md) defines hooks and `make_safe`; [ADR-0023](0023-station-composition-root.md) composes and owns the manager; [ADR-0002](0002-error-model.md) defines the error hierarchy |

**Reading path:** start with [Resources](../wiki/resources.md) for the concepts, then
[Life of a station](../wiki/life-of-a-station.md) for the end-to-end flow. This record
specifies the current lifecycle algorithm and its limits; engine integration is planned.

## 1. Summary

The `ResourceManager` opens a station's resources in profile order, verifies them,
and coordinates requested safe-state and close actions in reverse order.

Opening one resource means:

1. its I/O
2. its DUT channels
3. `open()`
4. `identify()`, checked against `expect:`
5. `health()`
6. `children()`

If opening fails, the manager attempts to close partially opened and previously
opened resources before propagating the error. Safe-state and close operations
continue past ordinary exceptions to attempt the remaining actions. Lifecycle
events report progress; successful physical cleanup cannot be guaranteed when a
device or connection fails.

## 2. The problem, from first principles

- **Bring-up is where real-world failures cluster:** a supply switched off, the wrong
  unit in the fixture, a console with no prompt. The third of five resources failing
  must not leave the first two energised and connected.
- **Order matters for safety and correctness:**
  - A DUT's channels must be open before the DUT's `open()` uses them.
  - Identity should be checked before test operations. In the current implementation,
    injected I/O and the driver's `open()` hook run before identity verification;
    opening hooks may already have sent commands.
  - Shutdown must reverse bring-up, so dependents are released before what they depend
    on.
- **Abort must reach everything.** If an operator hits stop and one supply doesn't
  respond to "output off", the remaining instruments must still be made safe.
- **Nobody should re-implement this.** If each driver or test managed its own
  lifecycle, the ordering and rollback rules would differ, and safety would depend on
  the least careful author.
- **Observability.** The engine and UIs need to show bring-up progress, and record
  which resource failed and why.

## 3. Where it sits in the system

```mermaid
flowchart LR
    st[Station.open / safe_state / close] --> rm[ResourceManager]
    rm --> h[ResourceHandle per resource]
    h --> io[injected I/O open/close]
    h --> ch[channel handles]
    h --> hooks[driver hooks via call_hook]
    rm -->|make_safe| sf[driver safe_state or contract actions]
    rm -->|ResourceEvent| lis[listener → engine events - planned]
```

Arrows show calls and event delivery. The [station composition root](0023-station-composition-root.md)
owns the manager; [driver hooks](0011-drivers-and-duts.md) provide device-specific actions;
[identity and health](0010-identity-and-health.md) provide the verification reports.

## 4. Decision

1. **`ResourceHandle`** holds everything about one resource at run time:
   - `built` (instance, config, I/O)
   - `entry` (profile)
   - `channels` (child handles)
   - `children`, `identity`, `health`, `is_open`
   - a private `_driver_opened` flag

   `state_snapshot()` returns the DUT state as JSON-ready data, for run snapshots.
2. **The open sequence per resource** (`_open_one`), in this order:
   1. open every injected I/O object
   2. open each channel handle, recursively, with the same rules
   3. `call_hook(open)`, after which the driver is marked opened only if the call returns
   4. `identify()` if present. If the merged expectations (profile `expect:` plus the
      caller's `expect=`) are non-empty, they must match. Expectations without
      `identify()` raise `IdentityMismatch`.
   5. `health()` if present. `ok=False` raises `ResourceFault`.
   6. `children()` if present, stored for role resolution
   7. mark open and emit `opened`

   On any exception (`BaseException`, so `KeyboardInterrupt` is included), the manager
   emits `open_failed`, attempts to close this resource's partial state, and re-raises.
3. **`open_all(expect=None)`** opens the handles in order. If one fails, every
   previously opened handle has cleanup attempted in reverse and the error is re-raised. The
   `expect` argument carries **operator-supplied identities**, such as a scanned DUT
   serial.
4. **Closing one resource** (`_close_one`):
   - the driver's `close()`, but only if the opening-hook call returned successfully
   - then channels in reverse
   - then I/O in reverse

   It collects errors and continues. It always clears `is_open` and `children`.
5. **`close_all()`** closes every opened handle in reverse. Afterwards, if any errors
   occurred, it raises a single `ResourceError` chained to the first.
6. **`safe_state_all()`** calls `make_safe` on every opened handle in reverse. It
   collects ordinary `Exception` failures in `{name: exception}` and emits
   `safe_state` / `safe_state_failed`. Resources with no safe-state action emit
   `safe_state` with detail `"no safe-state action"`.
7. **Events.** A `ResourceEvent(resource, phase, detail)` is emitted for: `opening`,
   `opened`, `open_failed`, `safe_state`, `safe_state_failed`, `closed`,
   `close_failed`. Every event is also logged. A listener that raises is logged and
   ignored for ordinary exceptions, so those listener failures do not interrupt shutdown.

## 5. Abstractions

| Name | Purpose | Invariants and behaviour |
|---|---|---|
| `ResourceHandle` | Run-time record of one resource | `instance` and `spec` shortcuts. `state_snapshot()` gives a dict or `None`. |
| `ResourceManager(handles, listener=None, logger=None)` | Lifecycle executor | Opens in the order given. |
| `open_all(expect=None)` | Bring-up with rollback | Failed bring-up triggers cleanup attempts; cleanup failures do not establish a physical closed state. |
| `safe_state_all()` | Attempt configured safe-state actions | Collects ordinary exceptions and returns failures; process interruption and non-returning hooks remain limitations. |
| `close_all()` | Tear down | Attempts everything, then raises if anything failed. |
| `opened` | Currently open handles | In opening order. |
| `ResourceEvent`, `Phase`, `Listener` | Observability | `Phase` is a closed set of string literals. |

## 6. Data flow

```mermaid
sequenceDiagram
    participant M as ResourceManager
    participant A as psu
    participant B as dut (+console)
    participant C as pos
    M->>A: io.open, open, identify✓, health✓
    M->>B: io.open, console(open...), open, identify✓
    M->>C: io.open, open ✗ ResourceFault
    M->>C: close partial (io.close)
    M->>B: close, console.close, io.close
    M->>A: close, io.close
    M--xM: re-raise ResourceFault
```

**Normal end of a run** (planned engine): `safe_state_all()`, then `close_all()`.

## 7. Errors

| Exception | Raised when | Meaning | Who catches it, and what they do |
|---|---|---|---|
| `IdentityMismatch` | expected identity differs, or can't be verified | configured identity requirements are not satisfied | The caller stops bring-up and reports the mismatch. Engine handling is planned. |
| `ResourceFault` | `health()` reports not ok | the device is unfit | Fix or replace it. |
| `ResourceError` | `close_all` had errors | some resource didn't close cleanly | Log it. The station may need a manual check. |
| anything from hooks or I/O | opening failed | see that error | Rollback has already happened. The error is unchanged. |

`safe_state_all` deliberately returns failures instead of raising.

## 8. Guarantees and invariants

- On failed bring-up, cleanup is attempted for partial and previously opened resources.
  Close errors during rollback do not replace the original opening error. Clearing
  internal open flags is not evidence that a device physically disconnected.
- `safe_state_all` continues to remaining resources when an action raises an ordinary
  `Exception`. It does not guarantee recovery from process termination, a blocking
  hook, or every `BaseException`.
- `close_all` continues past ordinary close exceptions and reports collected failure.
- A driver's `close()` is called only after its opening-hook call returns successfully.
  If `open()` raises part-way through device setup, the manager closes channels and
  injected I/O but does not call that driver's `close()` hook.
- Safe-state actions and closing are separate requests. Opening rollback performs
  close operations; it does not itself invoke `safe_state_all()`.
- Ordering: open follows profile order; safe state and close follow its reverse.

## 9. Consequences

- **Positive:**
  - Safety and ordering are centralised and tested once.
  - Drivers implement only steps.
  - Progress is observable.
- **Negative:**
  - The order is sequential. Slow instruments open one after another.
  - Hooks have no per-step timeouts beyond what transports enforce.
- **Risks:** a driver `open()` that blocks forever without I/O. Drivers should use
  transport timeouts.

## 10. Alternatives considered

- **Context managers per driver (`with psu:`):** rejected. They spread lifecycle and
  rollback logic across tests, and nested `with` blocks can't express "make all safe
  even if one fails".
- **Raising from safe state:** rejected. The first failure would stop the rest.
- **Parallel open:** deferred. It complicates ordering and rollback; revisit for large
  stations.

## 11. Open questions and future work

- Per-resource scope (open per run or per task) and reconnect policies.
- Timeouts per lifecycle step.
- Locks for `shared` resources on multi-DUT stations.

## 12. Code map

| What | Where |
|---|---|
| Implementation / API | [`mastif.station.manager`](../reference/station/manager.md) |
| Tests | `packages/mastif/tests/station/test_station.py` (ordering, rollback, identity, health, safe state, events) |
| Wiki | [Station](../wiki/station.md), [Life of a station](../wiki/life-of-a-station.md), [Resources](../wiki/resources.md) |

## History

- 2026-10-21: created.
- 2026-10-29: connected the concept, API, and related-decision pages; clarified actual
  rollback, opening-hook, and safe-state limits against the current implementation.
  No lifecycle behaviour changed.
