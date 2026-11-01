# What the system must do

A test works on one bench, then a replacement instrument arrives. Another test runs for hours, then loses its connection during cleanup. A report says FAIL, but nobody can tell which limits were used. These look like unrelated problems until you ask the same question of each: which part of the system was responsible for keeping that fact or making that decision?

Requirements give us a way to answer before choosing components. This chapter describes the generic behaviours mastif is built around. A useful requirement explains what must remain true when the hardware, application or deployment changes; it doesn't start by choosing a database or a server layout.

!!! example "Framework design requirements"
    The resource, station and result foundations are implemented. The engine, run store and persistent runtime are planned. The [status table](#where-mastif-stands) separates those parts; requirements here are design targets, not claims that the whole system exists.

## Purpose and boundaries

mastif provides a domain-neutral foundation to **define, execute, observe and record** hardware tests. Your test specifies what to ask of a device and how to evaluate its answer. The framework gives that code a consistent vocabulary and lifecycle, while an organisation supplies its product knowledge through packages and configuration.

| Framework responsibility | Application or organisation responsibility |
|---|---|
| Values, units, limits and computed verdicts | Product requirements and acceptance limits |
| Capability contracts and driver integration | Device-specific commands and DUT behaviour |
| Station composition and resource lifecycle | Physical wiring, station profiles and interlocks |
| Planned task execution, events and run records | Test procedures, interfaces and downstream workflows |

These boundaries follow [ADR-0001](../../adr/0001-layered-architecture.md): dependencies point towards the reusable foundation, and product-specific code plugs in through explicit extension points. Deployment, software distribution, identity services and long-term organisational recordkeeping are integration choices around that foundation.

## Principles that survive a deployment change

### Tests name capabilities

A test that measures current should ask for a current-reading capability, rather than construct a particular vendor's driver. The profile selects the device; the driver translates its protocol. A simulator can then satisfy the same contract without making the test special-case simulation.

This is a boundary for both code and meaning. Matching method signatures doesn't prove that two instruments have the same accuracy or timing. The [contract](../../getting-started/tutorial/hardware-integration/contracts.md) must explain the behaviour a caller can rely on, and the integration must be checked against it.

### Ownership is explicit

An open connection, permission to control an instrument and responsibility for cleanup are different things. Each needs an owner. Otherwise, one screen can close a connection while a test is using it, or a failed task can leave an output energised because every layer expected another layer to turn it off.

In direct mode, the application owns the station's lifetime. The planned persistent runtime gives that lifetime to a dedicated process and grants clients control through leases. [ADR-0030](../../adr/0030-execution-topology.md) defines this distinction. A lease concerns access to resources; it does not define an organisation's operator roles or login policy.

### Evidence preserves its meaning

A recorded value needs its unit, the limits used to evaluate it and enough context to identify its source. A failed check and a failed attempt to take a reading are different outcomes: **FAIL** says the requirement wasn't met; **ERROR** says execution couldn't complete. [ADR-0002](../../adr/0002-error-model.md) explains why a timeout must never become a plausible-looking reading.

The run-level design extends that principle to provenance: resolved parameters, plan position, equipment identity and software versions. A later [human decision](dispositions.md) can refer to evidence, but must not silently turn a failed measurement into a pass.

### Failure remains visible

Asking an output to turn off is not proof that it did. A cable may have fallen out, the device may be unresponsive, or a vendor call may never return. The framework must attempt the cleanup it owns, preserve the original failure, and report cleanup failures too.

The same honesty applies to recovery. A saved software checkpoint cannot restore a physical experiment by itself. Resuming requires checking identity and re-establishing conditions; if that cannot be justified, starting a new run may be the correct outcome. See [cancellation](cancellation.md) and [recovery](recovery.md) for the limits of these mechanisms.

## From principles to behaviour

### Define work before executing it

The planned engine separates a **plan** (what should run) from a **run** (one attempt to execute it). Expansion resolves task parameters, loop positions and resource requirements before hardware is touched. That lets an author inspect the intended work and catches configuration mistakes early.

Validation happens in stages. Building a station can check that a role exists and supplies a contract. Opening can check the connected instrument's identity and health. Neither stage proves that the fixture is wired correctly or that a particular physical experiment is ready. Those checks belong in the relevant driver or test procedure.

### Coordinate execution and cleanup

Task hooks, loop entry and exit, and station open and close have different lifetimes. The engine must pair each setup action with cleanup at the right scope, including when setup only partly succeeds. Pause and abort requests need defined checkpoints, and blocking operations need meaningful deadlines.

Parallel execution also needs a resource model, not just more threads. Two tasks cannot independently control aliases of the same instrument without coordinating access. The chapters on [resource lifetimes](resource-lifetimes.md) and [concurrency](concurrency.md) explain where that coordination belongs.

### Record enough to explain a run

The existing kernel gives measurements, checks and tables a serialisable representation with computed verdicts. The planned engine adds ordered events and a run record that connects those results to the work that produced them.

The [run-folder design](../../getting-started/tutorial/first-results/progress.md#what-gets-saved) makes inputs, events, checkpoints and the final report inspectable. A record must distinguish a completed run from an interrupted one. It must also say what was actually used, rather than refer only to configuration files that might later change. Sensitive configuration must be redacted from that record.

Durability needs its own contract: when a recording call returns, what has reached persistent storage? What could still be lost if the process or machine stops now? Those questions remain important regardless of the eventual storage implementation, and the [progress chapter](../../getting-started/tutorial/first-results/progress.md#surviving-a-crash) keeps the unresolved acknowledgement policy visible.

### Let clients observe without owning execution

A UI needs current progress, but a displayed snapshot is only what the UI last heard. It must not become a second run state machine. Commands request changes; events report what the execution owner actually did. A lost connection means the client's knowledge is stale, not that the hardware stopped.

This leads to typed events, sequence information and explicit freshness, covered in [events and state](events-state.md). It also keeps diagnostic logs separate from structured evidence: improving a log message should not break a result consumer.

## Qualities and their costs

| Quality | What we ask of the design | The limit to keep visible |
|---|---|---|
| **Testability** | Exercise decisions with pure functions and integrations with fake I/O | A fake doesn't establish real device timing or physical safety |
| **Reproducibility** | Preserve the resolved inputs and provenance of a run | Reproducing software inputs doesn't guarantee identical physical conditions |
| **Reliability** | Preserve causes, attempt cleanup and identify incomplete work | Software can't guarantee recovery from every device or process failure |
| **Responsiveness** | Keep blocking device work away from client interaction | A timeout cannot forcibly cancel arbitrary Python or native code |
| **Maintainability** | Change drivers and applications without forking the core | Contract semantics and compatibility still need deliberate ownership |

## Where mastif stands

| Requirement | State | Where |
|---|---|---|
| Capability contracts, drivers and transport diversity | **Implemented** | [Resources](../architecture/resources.md), [Transports](../architecture/transports.md) |
| Validated station profiles, identity checks and lifecycle cleanup | **Implemented** | [Station](../architecture/station.md) |
| Structured result values and computed verdicts | **Implemented** | [Kernel](../architecture/kernel.md) |
| Fake I/O and lifecycle conformance checks | **Implemented** | [Testing kit](../architecture/testing-kit.md) |
| Tasks, plans, loops and run control | Design preview | [Plans](../../getting-started/tutorial/writing-tests/plans.md), [Run lifecycle](run-lifecycle.md) |
| Run records, checkpoints and resume | Design preview | [Progress and saved results](../../getting-started/tutorial/first-results/progress.md), [Recovery](recovery.md) |
| Persistent hardware ownership and control leases | Designed, not implemented | [Execution modes](execution-modes.md), [Resource lifetimes](resource-lifetimes.md) |

??? question "Still open in this design"
    - **Durability acknowledgement.** Exactly when an event-recording call returns, and where batching is acceptable.
    - **Plan composition.** How reusable procedures combine without hiding their resource requirements or cleanup scopes.
    - **Resume eligibility.** How tasks and loop types express when repeating work or restoring conditions is valid.

## Recap

- Generic requirements come from capability boundaries, ownership, evidence and failure handling.
- The framework supplies common mechanisms; applications supply product knowledge and operating policies.
- Resource management and result models work today. Execution, run recording and shared runtime access remain planned.
- A useful guarantee names both the owner and the point where that guarantee stops.

With those framework requirements in view, we can look at the wider system: how execution and evidence relate to shared services without making them the same responsibility.

**Next:** [The concept system design](station-and-server.md)
