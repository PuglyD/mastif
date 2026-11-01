# Failed checks and execution errors

The supply returned 300 mA. The supply returned nothing.

These two events look similar. Both mean the test didn't pass, and in a lot of test software both end up as the same red line in the same report. But they
tell you very different things, and they call for opposite actions. Getting this distinction right is one of the most important things a test framework
can do, so it gets its own chapter.

!!! example "Part implemented, part preview"
    Typed exceptions, verdicts and aggregation work today, and so does everything in the [exception
    section](#a-map-of-what-can-go-wrong). How the engine converts them into task outcomes is a design preview.

## Two different facts

**300 mA against a 250 mA limit is a FAIL.** The instrument answered, the reading is valid, and the board is drawing too much. You've learned something
definite about the unit. The right response is to investigate the unit, and you might scrap or rework it.

**No reply is an ERROR.** You've learned nothing about the unit at all. It might be perfect. The right response is to fix the bench, and test the unit again.

Now think about the cost of confusing them, in each direction.

If an instrument problem gets reported as FAIL, you may scrap good hardware. A flaky cable on one bench turns into a yield problem that someone spends weeks
chasing through the product's design.

If a failure gets reported as an ERROR or, worse, gets lost, bad hardware may ship. The classic route to this is a well-meaning piece of code:

```python title="please don't do this"
try:
    current = supply.measure_current()
except Exception:
    current = 0 * mA      # So the test keeps going
```

A broken cable now reads 0 mA, which is under the limit. **It passes.** Every board tested on that bench, with the cable out, passes. This is about the worst outcome a
test system can have, and it comes from trying to be helpful. So here's the first rule:

> **Never convert an exception into a value.** Let it propagate.

## Who decides

The way mastif draws the line is simple, and it's very easy to remember.

**A verdict is about the unit. An exception is about the test.**

Everything flows from that. No exception in mastif ever means "the unit is bad". That's always a verdict.

```python title="preview"
def run(self, ctx):
    # The instrument might not answer. That raises TransportTimeout, and we don't catch
    # it. The task becomes an ERROR, which is the truth.
    current = self.supply.measure_current()

    # We have a valid reading. This might record a FAIL, which is also the truth.
    ctx.measure("idle_current", current, Limits.at_most(self.config.max_current))
```

Here's how the engine classifies what a task does:

| What happens in the task | Task outcome | What it means |
|---|---|---|
| All results pass | **PASS** | The unit met this requirement |
| A result fails, including via `assert` or `ctx.require` | **FAIL** | The unit didn't meet it |
| `TransportTimeout`, `ProtocolError`, `ResourceFault` | **ERROR** | The bench or the instrument had a problem |
| `UnitError`, `KeyError`, or any other bug | **ERROR** | The test itself has a problem |
| `should_run` returned `Skip` | **SKIPPED** | The task chose not to run |
| Stopped by an operator or a policy | **ABORTED** | The work was interrupted |

There's one situation to think through carefully: a task that records a FAIL and then hits an exception. Its outcome is ERROR, as `aggregate` says ERROR outranks FAIL, but the
FAIL measurement is still there in the record. Nothing is thrown away. It's correct to say the test as a whole is broken, and it's also useful to know what it saw before that.

## A map of what can go wrong

Every exception mastif raises descends from `MastifError`, which means an application can catch them all at the top, while each one tells you where to look.

```python
from mastif.kernel.errors import MastifError
from mastif.resources.errors import ProtocolError, TransportError, TransportTimeout

print(issubclass(TransportTimeout, TransportError))  # True
print(issubclass(ProtocolError, MastifError))        # True
```

The useful way to read these is by *when* they occur, as this tells you what to go and fix.

| When | Examples | Go and fix |
|---|---|---|
| **Importing your code** | `ContractMismatch`, `DriverDefinitionError` | The driver's code |
| **Building the station** | `StationError` | The profile, or the installed SDK |
| **Preflight** | `RoleError` | The profile's role mapping |
| **Opening** | `TransportError`, `IdentityMismatch`, `ResourceFault` | The bench |
| **Running** | `TransportTimeout`, `ProtocolError` | The instrument, the cabling or the driver |
| **Any time** | `UnitError`, `LimitsError` | The test or the specification |

Notice how far to the left most of these appear. A big part of mastif's design is pushing errors to the earliest possible moment, when they're cheapest and when nothing is
energised. The complete list is in the [error map](../../../learn/architecture/errors.md).

Let's look at the real messages from a driver failing in three different ways. We've used a scripted fake instrument to produce them:

```python
from mastif.resources.errors import ProtocolError, TransportTimeout
from mastif.resources.transports import Scpi
from mastif_testing import FakeLineIO

def read_current(reply):
    io = Scpi(FakeLineIO({"MEAS:CURR?": reply} if reply else {}))
    io.open()
    return io.query_quantity("MEAS:CURR?", "A")

print(read_current("0.180"))  # 0.18 A

for bad in ["banana", "9.9E37", None]:
    try:
        read_current(bad)
    except (ProtocolError, TransportTimeout) as error:
        print(f"{type(error).__name__}: {error}")
```

```text title="Real output"
ProtocolError: MEAS:CURR? returned 'banana', expected a number
ProtocolError: MEAS:CURR? returned overflow/invalid marker '9.9E37'
TransportTimeout: fake: no reply queued
```

Take a look at the second one. Remember the [script from the start of these docs](../../intro/problem.md), which parsed `9.9E37` happily and reported a very large current? Many instruments use that value
to mean "overrange", which means the instrument didn't get a valid reading. The `Scpi` helper recognises this, so it becomes a `ProtocolError`, an ERROR, instead of a FAIL against a
number that was never measured.

Each message also starts with what it's about: the command, the resource, or the field. That's a convention we keep throughout, because the first thing you want from an error message is
where to look.

## Who should catch what

In short, almost nobody. Here's how that breaks down.

**Task authors: almost never.** If you can't do something meaningful about an exception, let it go. Catch it only if your procedure genuinely expects that failure and has a real response to it.

```python title="preview: a legitimate catch"
def run(self, ctx):
    # This revision may legitimately have no fan. Absence is a fact we want to record.
    try:
        speed = self.board.read_fan_speed()
    except FeatureNotPresent:
        ctx.check("fan_present", False, detail="this revision has no fan")
        return
    ctx.measure("fan_speed", speed, ...)
```

Be careful about the width of your `except`. A bare `except Exception` also catches your own bugs, and converts a typo into a "failed test".

**Driver authors: translate.** A driver catches library exceptions, and re-raises them as `TransportError`, `TransportTimeout` or `ProtocolError`, adding context and chaining the cause. That way nothing
above the driver needs to know whether you're using pyserial or a vendor DLL. Only retry queries that are safe to repeat.

**The station: never stops cleanup.** It translates build problems into a `StationError` that names the resource, it rolls back a failed open, and it keeps going through safe state regardless.

**The engine: at the top.** It catches everything, classifies it, records it, and makes sure that the station gets to its safe state.

## Keep the first cause

When things go wrong, they tend to go wrong in a cascade. An instrument's connection drops, the measurement raises a timeout, `teardown` tries to turn the output off and gets a timeout of its own, and then
the station's close fails too.

The report needs to show that sequence, with the first failure in the place of honour. It's easy to end up with a final message saying "failed to close bench_supply", which is true, and tells you
nothing about the real cause. Cleanup failures are recorded as *additional* facts, and they can't replace the original.

This is the same reason you should chain exceptions when translating:

```python title="in a driver"
try:
    reply = self.lib.read_register(address)
except VendorError as error:
    raise ProtocolError(f"{self.name}: register {address:#x}: {error}") from error
```

`from error` keeps the original traceback attached, so anyone diagnosing the problem can still see the vendor's own message.

## Retrying

There's a temptation to wrap flaky operations in a retry loop. We'll deal with this properly in [Failure propagation and recovery](../../../learn/system-design/recovery.md), but here's the short version. A retry of a read is
usually harmless. A retry of a command, after a timeout, may repeat something that already happened: the first attempt might have worked, and only the reply was lost. Think about what happens if that
command is "advance the positioner by 10 degrees".

The plan's `retries` policy exists, and it defaults to zero for this reason. When you do retry a task, the record keeps every attempt, so a passing retry doesn't erase the failure before it. A unit that
passes on the third try is telling you something too.

## Recap

- **A verdict is about the unit, and an exception is about the test.** FAIL means investigate the unit. ERROR means fix the bench and retest.
- **Never turn an exception into a value.** A silent zero is how broken benches pass bad boards.
- Errors **surface as early as possible**, and each one tells you where to look.
- **Almost nobody should catch.** Drivers translate, tasks let exceptions go, and the engine classifies at the top.
- **The first cause is kept.** Cleanup failures add to the story, and they can't replace it.

That covers how a test reports its outcomes. Now let's look at what it leaves behind.

**Next:** [Understanding the results](../first-results/results.md)
