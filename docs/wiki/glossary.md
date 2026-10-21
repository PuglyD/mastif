# Glossary

Terms are listed alphabetically. Each entry says what the term means in mastif, and
where it lives.

**ADR (Architecture Decision Record)**
: A document recording one decision: the problem, where it fits, the abstractions, data
  flow, errors, and the alternatives rejected. There is one per module. See the
  [ADR index](../adr/index.md).

**Aggregate**
: Combine child verdicts into a parent verdict: the worst wins (ABORTED > ERROR > FAIL >
  WARN > PASS > SKIPPED). `mastif.kernel.verdict.aggregate`. ADR-0005.

**ATE (automated test equipment)**
: Hardware plus software that tests products automatically: instruments, fixtures, and
  test sequencing.

**Bench / station**
: One physical test setup: instruments, fixture and DUT. It is described by a
  **station profile**. The words are used interchangeably.

**Channel**
: A named way into a DUT, declared on the DUT class as `console: Shell = channel()`.
  It is mapped in the profile to a channel driver. ADR-0011, ADR-0023.

**Children**
: Sub-resources a composite driver reports once open, e.g. the axes of a positioner
  controller. They are reachable by role as `resource.child`.

**Composition root**
: The single place where all parts are wired together. In mastif that is
  `Station.build`. ADR-0023.

**Conformance**
: Checking that a driver meets mastif's obligations: `mastif_testing.check_lifecycle`
  and `assert_satisfies`. ADR-0025.

**Contract**
: A capability a test needs, written as a plain `typing.Protocol`, e.g. `PowerSupply`.
  Tests depend on contracts, never on drivers. ADR-0008.

**DriverSpec**
: The record `@driver`/`@dut` attaches to a class: id, provided contracts, config model,
  injected parameters, channels and state model. ADR-0011.

**Driver**
: A class marked `@driver("org.name", provides=[...])` holding the knowledge of one
  device: which commands to send, and how to read the replies. ADR-0011.

**DUT (device under test)**
: The product being tested. In mastif, a **DUT type** is a class marked `@dut`, usually
  with channels and a state model.

**Entry point**
: A named hook a Python package declares in `pyproject.toml`. mastif finds org drivers
  through the `mastif.drivers` group. ADR-0012.

**ERROR (verdict)**
: The test could not complete: an exception, or lost communication. It says nothing
  about the unit. Contrast with FAIL.

**Evaluate**
: The pure function that turns a value and limits into PASS, WARN or FAIL.
  `mastif.kernel.limits.evaluate`. ADR-0004.

**Expect**
: Identity fields a profile requires a resource to report, e.g. `{serial: A123}`. They
  are checked before use. ADR-0010, ADR-0022.

**Fake**
: A behavioural stand-in for hardware I/O: `FakeLineIO`, `FakeStream`,
  `FakeDatagramPeer`. Preferred over mocks. ADR-0024.

**FAIL (verdict)**
: The unit did not meet a limit or check.

**Health**
: Whether a resource is fit for use right now (`Health(ok, detail, readings)`). An
  unhealthy resource is refused when the station opens. ADR-0010.

**Identity**
: What a resource reports about itself: vendor, model, serial, revision, extra.
  ADR-0010.

**Injection (of I/O)**
: The station builds the I/O object a driver asks for in its `__init__` annotation, from
  the profile's `transport:` block. ADR-0018.

**Kernel**
: The bottom layer: units, limits, verdicts, results, ids and errors. It is pure, with
  no I/O. The name comes from domain-driven design's "shared kernel".

**Layer**
: One of `kernel`, `resources`, `station`, `engine`, `api` and `cli`. Imports only point
  down. ADR-0001.

**Limits**
: A passing range plus an optional wider warning range. `IndexedLimits` vary per index.
  ADR-0004.

**LineIO**
: Text-line I/O (`write_line`, `read_line`, `query`) over a stream or VISA. ADR-0015.

**Loop (planned)**
: A dimension a plan iterates over, e.g. channel, temperature or firmware profile. Orgs
  will define loop types with enter and exit actions.

**Measurement / Check / Table**
: The three result kinds. Each computes its own verdict. ADR-0006.

**Position**
: The current value of every loop in a plan, outermost first. Used for provenance,
  transitions and resume. ADR-0007.

**Profile (station profile)**
: The YAML facts of one bench: resources, roles and sim overrides. ADR-0021.

**Quantity**
: A value with a unit: `12 * V`. ADR-0003.

**Range**
: One interval of acceptable values in one unit. Either end may be open. ADR-0004.

**Registry**
: The map from driver id to `DriverSpec`, built explicitly or from entry points.
  ADR-0012.

**Resource**
: Anything the station manages: an instrument, a DUT, or a DUT channel.

**ResourceManager**
: Runs the lifecycle: ordered open with identity and health checks, rollback, safe
  state, reverse close. ADR-0022.

**Role**
: The name a test uses for a resource (`psu_main`). The profile maps roles to resources,
  so tests stay portable across benches. ADR-0021, ADR-0023.

**Safe state**
: The state that is harmless if left unattended, such as outputs off and relays open. It
  is reached via the driver's `safe_state()` or the contract's declared action.

**SCPI**
: Standard Commands for Programmable Instruments, the text command language of most
  bench instruments. The `Scpi` helper is ADR-0016.

**Sentinel**
: A special return value meaning "failed", such as `0.0`, `None` or `-1`. Forbidden in
  mastif. Errors are raised instead. ADR-0002.

**Sim / simulation mode**
: Building a station with `sim=True`, which swaps in the profile's `sim:` entries.

**Slot**
: One DUT position on a multi-DUT fixture. It is carried in ids and profiles today, and
  will be used later. ADR-0007.

**Transport**
: How bytes or messages reach a device: TCP, serial, VISA or UDP. ADR-0013–0017.

**Verdict**
: PASS, WARN, FAIL, ERROR, SKIPPED or ABORTED. ADR-0005.

**WARN (verdict)**
: Nothing failed, but something fell in a marginal (warning) range.
