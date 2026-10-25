# Field notes

Practical advice from engineers who have built and run test stations for a long time.
These are not rules of the framework; they are the experience behind some of its
decisions. Each note says where it came from, what it recommends, and where mastif
reflects it. Names are left out on purpose.

New notes are welcome from anyone on the project. Keep them concrete: the situation, the
advice, and the reason.

---

## 1. Open, measure, close

*From a senior ATE engineer with more than 20 years of experience.*

**The advice.** A test should open its connection to the instrument, make the
measurement and close the connection again. Sequential and simple. Don't keep a
background process polling instruments: constant polling hogs resources and is overkill
for what a test needs.

**Why it works:**

- **Each test starts clean.** Nothing is left open, nothing is half-configured, and a
  crashed test doesn't leave a port locked.
- **It runs anywhere.** The same test runs on the bench, on a laptop against a
  simulator, and in CI. There is no daemon to install, monitor or upgrade.
- **It's cheap.** No CPU, bus time or instrument time is spent on data nobody asked for.
  Instruments stay free for other tools, like the vendor's front-panel software.
- **It's easy to debug.** One process, one log, one stack trace, read top to bottom.

**Where it doesn't reach.** It doesn't cover a control GUI that must work alongside a
running test, safety readings watched between tests, or instruments that take seconds to
open.

**In mastif.** This is **direct mode**, the default and the first mode built: the test
process builds the station, opens it, measures and closes it
([ADR-0030](../adr/0030-execution-topology.md)). mastif keeps the connection open for a
whole run rather than per measurement (open and identity checks happen once, in
order), and a per-task scope is planned for instruments where that matters. The optional
**station runtime** exists for the cases above, and borrows this note's principle:
it measures when asked, and polls only what a profile explicitly marks for monitoring.

---

## 2. Why continuous polling harms tests

*Collected while designing the station runtime, refining note 1.*

**The advice.** Never let a test use a value that some background loop happened to read.
A test result must come from a measurement the test itself triggered, after it set up
its own conditions.

**Five reasons:**

1. **Staleness and causality.** A value polled 800 ms ago predates the test's stimulus.
   It can pass a test the DUT should fail.
2. **Interference with instrument state and error queues.** A poll is a command. It can
   change the range or function, restart averaging, abort a sweep, or read and clear the
   SCPI error queue just before the test checks it.
3. **Measurement conditions.** Polling changes what is measured: auto-ranging,
   self-heating from repeated reads, extra console traffic changing the DUT's timing.
4. **Bus time.** On a slow or shared bus (GPIB, serial), a 200 ms poll delays the test's
   own command by up to 200 ms, at random.
5. **Traceability.** A result must record which command produced it, when and under
   which settings. A cached poll has no such provenance.

**In mastif.** In the station runtime, commands run on demand and return fresh results.
A test's measurement carries a sequence number at least as high as its own command's
(read-after-write consistency), so a cached value can never be returned as a result.
Monitors are **opt-in** per resource, limited to readings the driver declares
side-effect-free, and pause by default while a test controls the resource. See
[ADR-0030](../adr/0030-execution-topology.md), sections 2.4 and 4.
