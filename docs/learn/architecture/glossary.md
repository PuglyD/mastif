# Glossary

Every term of art used in these docs, in alphabetical order. Each entry says what it means in mastif, and where it lives. Planned framework features are labelled as such. General integration concepts explain the systems applications can build around mastif; they aren't additional framework APIs.

**ADR (Architecture Decision Record)**
: A document recording one decision: the problem, where it fits, the abstractions, data
  flow, errors, and the alternatives rejected. There is one per module. See the
  [ADR index](../../adr/index.md).

**Aggregate**
: Combine child verdicts into a parent verdict: the worst wins (ABORTED > ERROR > FAIL >
  WARN > PASS > SKIPPED). `mastif.kernel.verdict.aggregate`. ADR-0005.

**AGPL (GNU Affero General Public License)**
: mastif's licence, version 3 or later. A copyleft licence: whoever receives mastif, or
  uses a modified version over a network, must be offered the source. Internal use
  carries no obligations. ADR-0031, [Licensing](../../wiki/licensing.md).

**ATE (automated test equipment)**
: Hardware plus software that tests products automatically: instruments, fixtures, and
  test sequencing.

**Audit log** *(integration concept)*
: A history of actions and their context: who, when, what and why. An application can preserve corrections as new entries rather than overwriting earlier decisions. mastif doesn't supply an audit service. See [dispositions](../system-design/dispositions.md).

**Bench / station**
: One physical test setup: instruments, fixture and DUT. It is described by a
  **station profile**. The words are used interchangeably.

**Bootstrap**
: The single start-up call (`mastif.infra.bootstrap`): load settings, configure logging,
  record the version. Returns a `Runtime`. ADR-0029.

**Build info**
: Git information embedded into a wheel at build time (`_build_info.py`), so installed
  software knows its commit. ADR-0028.

**Calling convention**
: How a C function receives its arguments: `cdecl` (the default) or `stdcall` (the
  `WINAPI` convention of many Windows vendor DLLs). Set per library in `NativeConfig`.
  ADR-0035.

**Channel**
: A named way into a DUT, declared on the DUT class as `console: Shell = channel()`.
  It is mapped in the profile to a channel driver. ADR-0011, ADR-0023.

**Children**
: Sub-resources a composite driver reports once open, e.g. the axes of a positioner
  controller. They are reachable by role as `resource.child`.

**CLA (Contributor Licence Agreement)**
: A contract in which a contributor grants the project owner the right to relicense
  their contribution. Needed before mastif could accept outside contributions without
  losing the ability to sell commercial licences. ADR-0031.

**Composition root**
: The single place where all parts are wired together. In mastif that is
  `Station.build`. ADR-0023.

**Conformance**
: Checking that a driver meets mastif's obligations: `mastif_testing.check_lifecycle`
  and `assert_satisfies`. ADR-0025.

**Contract**
: A capability a test needs, written as a plain `typing.Protocol`, e.g. `PowerSupply`.
  Tests depend on contracts, never on drivers. ADR-0008.

**Design preview**
: A concrete proposed workflow or API written for review. Mock terminal output shows
  intended behaviour; it is not evidence that the command exists. See
  [Learn mastif](../../getting-started/intro/route.md).

**Direct mode**
: The default way to run: the test process builds and owns the `Station`, opens the
  instruments, measures and closes them. No background process. ADR-0030.

**Disposition** *(integration concept)*
: A decision about the subject of test evidence, such as rework or retest, recorded separately from the verdict. Its workflow belongs to the application. See [dispositions](../system-design/dispositions.md).

**Driver**
: A class marked `@driver("org.name", provides=[...])` holding the knowledge of one
  device: which commands to send, and how to read the replies. ADR-0011.

**DriverSpec**
: The record `@driver`/`@dut` attaches to a class: id, provided contracts, config model,
  injected parameters, channels and state model. ADR-0011.

**Dual licensing**
: Offering the same code under two licences: the AGPL for everyone, and a commercial
  licence, sold by the author, without the AGPL's obligations. Requires the author to
  hold all copyright. ADR-0031.

**DUT (device under test)**
: The product being tested. In mastif, a **DUT type** is a class marked `@dut`, usually
  with channels and a state model.

**Dynaconf**
: The configuration library behind mastif's `Settings`: multi-format files, merging,
  environment-variable overrides. ADR-0026.

**Entry point**
: A named hook a Python package declares in `pyproject.toml`. mastif finds org drivers
  through the `mastif.drivers` group. ADR-0012.

**ERROR (verdict)**
: The test could not complete: an exception, or lost communication. It says nothing
  about the unit. Contrast with FAIL.

**Evaluate**
: The pure function that turns a value and limits into PASS, WARN or FAIL.
  `mastif.kernel.limits.evaluate`. ADR-0004.

**Exec channel**
: An SSH channel that runs one command and reports its output, error output and exit
  status separately. `SshSession.run` and `mastif.ssh-shell` use one per command.
  ADR-0033.

**Execution context (planned)**
: The `ctx` argument the engine passes to a task's hooks. It records results (`ctx.measure`,
  `ctx.check`), exposes the loop position, and handles prompts and checkpoints. See
  [Writing a reusable test](../../getting-started/tutorial/writing-tests/reusable-tests.md).

**Expect**
: Identity fields a profile requires a resource to report, e.g. `{serial: A123}`. They
  are checked before use. ADR-0010, ADR-0022.

**FAIL (verdict)**
: The unit did not meet a limit or check.

**Fake**
: A behavioural stand-in for hardware I/O: `FakeLineIO`, `FakeStream`,
  `FakeDatagramPeer`. Preferred over mocks. ADR-0024.

**GitInfo / VersionInfo**
: Which commit and package version produced a run; `source` says whether it was
  embedded, captured live, or unavailable. ADR-0028.

**Health**
: Whether a resource is fit for use right now (`Health(ok, detail, readings)`). An
  unhealthy resource is refused when the station opens. ADR-0010.

**Host key / known hosts**
: An SSH server proves its identity with a host key, checked against a known-hosts file.
  mastif refuses unknown hosts by default (`known_hosts: strict`) and always refuses a
  changed key. ADR-0033.

**Idempotent operation**
: An operation whose repetition has the same intended final effect, unlike a trigger
  or increment. Device timing and side effects still matter when deciding whether a
  retry is valid. See [recovery](../system-design/recovery.md).

**Identity**
: What a resource reports about itself: vendor, model, serial, revision, extra.
  ADR-0010.

**Infra**
: The layer above the kernel for application plumbing: settings, logging, version
  information. ADR-0001, ADR-0026–0029.

**Injection (of I/O)**
: The station builds the I/O object a driver asks for in its `__init__` annotation, from
  the profile's `transport:` block. ADR-0018.

**Kernel**
: The bottom layer: units, limits, verdicts, results, ids and errors. It is pure, with
  no I/O. The name comes from domain-driven design's "shared kernel".

**Layer**
: One of `kernel`, `resources`, `station`, `engine`, `api` and `cli`. Imports only point
  down. ADR-0001.

**Lease (control lease)**
: Exclusive control of a set of roles, held by one client of the station runtime. A test
  run leases the roles it requires; GUIs may observe without one. A no-op in direct mode.
  ADR-0030 (planned).

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

**Monitor**
: Opt-in background polling of a resource's declared side-effect-free readings, configured
  by a `monitor:` block in the station profile. Runtime mode only; pauses while a test
  holds the resource by default. ADR-0030 (planned).

**Native library**
: A vendor's compiled library (Windows DLL, Linux shared object) driving an instrument.
  Reached through `NativeLibrary` (`kind: native`), never committed to a repository.
  ADR-0035.

**Outbox** *(system-design concept)*
: A durable queue of records awaiting delivery, written atomically with the local evidence. A sender retries until the receiver acknowledges delivery; duplicate delivery must be handled explicitly. See [the concept system design](../system-design/station-and-server.md#the-outbox-pattern). Not a currently implemented mastif API.

**Plan (planned)**
: A description of selected tests, their inputs, ordering, and execution dimensions.
  A **run** is one attempt to execute that procedure. The format is a design preview.
  See [plans](../../getting-started/tutorial/writing-tests/plans.md).

**Platform** *(general concept)*
: Shared capabilities offered like a product to the applications built on them. The term doesn't imply a particular deployment topology or a set of services shipped by mastif. See [design concepts](../system-design/concepts.md#what-a-platform-is).

**Position**
: The current value of every loop in a plan, outermost first. Used for provenance,
  transitions and resume. ADR-0007.

**Profile (station profile)**
: The YAML facts of one bench: resources, roles and sim overrides. ADR-0021.

**Prototype (of a C function)**
: Its return type and argument types, declared with `NativeLibrary.function` before the
  function can be called. Prevents ctypes from truncating 64-bit pointers. ADR-0035.

**Proxy**
: A client-side stand-in for a resource in the station runtime. It implements the same
  contract as the driver and forwards each call to the runtime process. ADR-0030
  (planned).

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

**ResourceProvider**
: The interface the engine uses to reach hardware: `role`, `require`, `open`,
  `safe_state`, `close` and `lease`. `Station` provides it in direct mode; a
  `RemoteStation` client will in runtime mode. ADR-0030.

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

**Sequence number**
: A counter attached to every value written into a resource's state. A test accepts
  only values whose sequence number is at least that of its own command
  (read-after-write consistency). ADR-0030.

**Settings**
: The one Dynaconf object holding an application's configuration, built once at
  start-up and passed explicitly (dependency injection). `section()` gives typed views.
  ADR-0026.

**Sim / simulation mode**
: Building a station with `sim=True`, which swaps in the profile's `sim:` entries.

**Slot**
: One DUT position on a multi-DUT fixture. It is carried in ids and profiles today, and
  will be used later. ADR-0007.

**SSH**
: Secure Shell: an encrypted, authenticated connection to a host, used for Linux DUTs.
  `kind: ssh` transport, `SshSession`, `mastif.ssh-shell`; needs `mastif[ssh]`
  (paramiko). ADR-0033, ADR-0034.

**State model**
: A Pydantic model declared with `@driver(..., state=...)` or `@dut(..., state=...)`.
  Local state creation exists today (ADR-0011). Automatically stamped fields, runtime
  publication, and freshness coordination remain planned (ADR-0030).

**Station runtime**
: The planned long-lived process that owns a station and serves several clients (the
  test executor, a control GUI) through proxies. Built after the engine. ADR-0030.

**Task** *(designed)*
: One test: a class with `should_run`, `setup`, `run`, `on_fail` and `teardown` hooks. See [Writing a reusable test](../../getting-started/tutorial/writing-tests/reusable-tests.md).

**Telnet**
: A text protocol over TCP (port 23) with in-band option negotiation, common on lab
  boxes such as switch matrices. `kind: telnet` transport; negotiation is stripped.
  ADR-0032.

**Thread confinement**
: Running every call to a resource on one dedicated thread, because many vendor libraries
  aren't thread-safe. The default for `NativeLibrary`; also how the planned station
  runtime serialises calls per resource. ADR-0030, ADR-0035.

**TRACE / SUCCESS**
: Extra log levels: TRACE (5) for raw protocol traffic, SUCCESS (25) for positive
  milestones. ADR-0027.

**Transport**
: How bytes or messages reach a device: TCP, serial, VISA or UDP. ADR-0013–0017.

**Verdict**
: PASS, WARN, FAIL, ERROR, SKIPPED or ABORTED. ADR-0005.

**WARN (verdict)**
: Nothing failed, but something fell in a marginal (warning) range.

**Next:** [What exists today and what we are designing](../status.md)
