# Identity, health, and safe state

A connected device can answer every command perfectly, and still be the wrong device. It can be the right device, and be in no condition to use. And when you've finished with it, it'll stay exactly how you left it, energised or not, unless someone does something about it.

These are three distinct questions: *Who are you? Are you fit to use? How do I leave you safely?* They're answered by three optional methods on your driver, and in this chapter we'll look at how to write them well.

!!! success "Works today"
    Everything on this page runs against the current code, with no hardware.

## Who are you?

Connecting to an address tells you where you've connected, not what's there. Instruments get swapped, cables get moved, and two identical units get transposed. Everything keeps working, the numbers look reasonable, and your results are now traceable to the wrong piece of calibrated equipment.

So a driver can report who it's talking to:

```python
from mastif.resources.identity import Identity

identity = Identity(
    vendor="ACME",
    model="PSU-X",
    serial="A123",
    revision="1.4",
    extra={"calibration_due": "2027-03-01"},
)
print(identity.mismatches({"serial": "A123"}))  # {}
print(identity.mismatches({"serial": "B999"}))
```

All of the fields are optional, because devices differ in what they can tell you. `extra` holds anything else that identifies it, and the profile's `expect:` can check those fields too, with the same syntax:

```yaml title="in a profile"
expect: {serial: A123, calibration_due: "2027-03-01"}
```

For a SCPI instrument, `Scpi.identify()` parses the standard `*IDN?` reply, so your whole implementation is one line:

```python title="excerpt"
def identify(self) -> Identity:
    return self.io.identify()
```

When a station opens this resource, it calls `identify()` and compares the answer. A mismatch stops everything before your test can touch that device:

```text title="Real output"
IdentityMismatch: bench_supply: serial is 'SIM-001', expected 'OTHER'
```

What if a profile has `expect:` but your driver has no `identify()`? That's a mismatch as well, and it's a deliberate one. If somebody asked for a check, then silently skipping it would be the worst possible response.

### Why it's checked after `open()`

Look again at the order in which the station does things: I/O first, then `open()`, then `identify()`. Many devices need some set-up before you can ask them anything, so `open()` has to come first.

This has a practical consequence for you as a driver author: **at the time `open()` runs, you don't yet know that this is the right device.** So keep it conservative. Reset the interface if you must, and select a channel, but don't apply stimulus. If `open()` turns an output on, and the serial then turns out to be wrong, you've just energised
something you never meant to.

## Are you fit to use?

Being the right device doesn't mean it's in a state to give you good data. It may be overheating, it might have a fault latched, or a self-test might have failed. That's what `health()` is for:

```python
from mastif.resources.identity import Health

print(Health.good().ok)  # True

poor = Health(ok=False, detail="over-temperature", readings={"temperature_c": 82.0})
print(poor.ok, poor.detail)  # False over-temperature
```

A station that sees `ok=False` raises `ResourceFault` and refuses to continue, rolling back anything it has already opened. Here's a typical implementation:

```python title="excerpt"
def health(self) -> Health:
    errors = self.io.errors()
    temperature = self.io.query_float("SYST:TEMP?")
    return Health(
        ok=not errors and temperature < 70,
        detail="; ".join(errors),
        readings={"temperature_c": temperature},
    )
```

`readings` are diagnostic values that are kept alongside the result of the check, whether or not it passes. They're the kind of thing that you'd like to have on hand when investigating a strange run later on.

Now, here are some subtleties to think about.

**Checks can have side effects.** Reading a SCPI error queue *empties* it. That's fine if `health()` is the only one that reads it. But if something polls `health()` in the background, it could steal the error that a test was about to check. Say what your checks do, in the docstring.

**A health check is a moment in time.** It says the device was fine when you asked. It's not a promise about the next hour. mastif calls this at opening. It's not continuous monitoring, which is a [separate, opt-in feature](../../../learn/system-design/events-state.md) of the runtime.

**Don't fake it.** Returning `Health.good()` unconditionally is reasonable for a simple simulator. In a real driver, it's better to leave the method out entirely, so that nobody's misled into thinking there was a check. If you can't check anything, then don't claim to have.

## How do I leave you safely?

Think about what "closed" means for a power supply. The socket has gone away, and the output is still on. Closing a connection does nothing to the device, which simply carries on with its last instruction. So putting hardware into a safe condition has to be its own step, and it's a different one from releasing the connection.

There are two ways to define what "safe" means for your device.

**Through the contract.** If you provide `PowerSupply`, this is already done, since the contract declares `output(False)`. You don't have to write anything. That's what happened in [the lifecycle chapter](../deploying/lifecycle.md#watch-it-happen), where a driver with no `safe_state` method still had its output turned off.

**With your own method**, when the device needs something more specific. If you define one, it replaces the contract's action:

```python title="excerpt"
def safe_state(self) -> None:
    self.output(False)
    self.io.write("RELAY:OPEN:ALL")
    self.io.write("VOLT 0")
```

Here's how to write a good one.

**Make it safe to call at any time.** It can run when the device was never fully set up, when it's in a bad state, or a second time. It must not assume anything.

**Keep it simple and fast.** It runs when things have already gone wrong. A long procedure that can itself fail in many ways isn't what you want at that moment.

**Think about what safe means here.** For a supply it's usually off. But for a chamber, "off" might not be safe at all. A chamber at −40 °C with its door open will collect condensation on your product, so it might need to ramp to ambient first. Only you can know this, which is exactly why it's in your driver and not in the framework.

**Think about a partial failure.** If the first command raises, the others don't run. If they're truly independent, try each one and report at the end, in the same way that the station does:

```python title="excerpt"
def safe_state(self) -> None:
    errors = []
    for command in ("OUTP OFF", "RELAY:OPEN:ALL"):
        try:
            self.io.write(command)
        except TransportError as error:
            errors.append(error)
    if errors:
        raise errors[0]
```

## And `close()`

`close()` is for what your *driver* acquired, such as a session handle from a vendor library. You don't need to close the injected I/O, as the station opened it, and the station closes it. By the time your `close()` runs, the I/O is still usable, so you can send a final command if needed.

Don't put safety-related actions in here. `safe_state` and `close` are separate calls, and the safety action belongs in the first one.

## A complete example

Here's a simulator with all of these hooks, and a station watching what it does:

```python
from mastif.kernel.units import Amps, Volts, mA
from mastif.resources.driver import DriverConfig, driver
from mastif.resources.identity import Health, Identity
from mastif.resources.registry import Registry
from mastif.resources.std import PowerSupply
from mastif.station import Station, StationProfile


@driver("demo.hooks", provides=[PowerSupply])
class Hooks:
    class Config(DriverConfig):
        healthy: bool = True

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def open(self) -> None:
        print("open")

    def identify(self) -> Identity:
        print("identify")
        return Identity(serial="H1")

    def health(self) -> Health:
        print("health")
        return Health(ok=self.cfg.healthy, detail="" if self.cfg.healthy else "fan stalled")

    def safe_state(self) -> None:
        print("safe_state")

    def close(self) -> None:
        print("close")

    def set_voltage(self, voltage: Volts) -> None: ...
    def set_current_limit(self, current: Amps) -> None: ...
    def output(self, enabled: bool) -> None: ...
    def measure_voltage(self) -> Volts: ...
    def measure_current(self) -> Amps: return 0 * mA


def build(healthy: bool) -> Station:
    profile = StationProfile.from_yaml(f"""
station: demo
resources:
  psu:
    driver: demo.hooks
    config: {{healthy: {str(healthy).lower()}}}
""")
    return Station.build(profile, Registry([Hooks]))


with build(healthy=True):
    print("-- test runs here --")
```

```text title="Real output"
open
identify
health
-- test runs here --
safe_state
close
```

Change `healthy` to `False`, and you'll see `open`, `identify`, `health`, and then `close`, with a `ResourceFault` reading `psu: unhealthy: fan stalled`. Your test doesn't run at all. Note that `safe_state` doesn't run either, since the resource never finished opening; `close` is what cleans up after a failed open. That's worth bearing in mind
for your `open()`, and it's one more reason to keep stimulus out of it.

## Recap

- **`identify()`** answers "who are you?". The station compares it with `expect:`, and it refuses a mismatch.
- **`health()`** answers "are you fit to use right now?". It's a moment in time, and it can have side effects.
- **`safe_state()`**, or the contract's action, handles the hardware. **`close()`** handles what the driver acquired.
- **`open()` runs before identity is checked**, so it should never apply stimulus.

All of this has been about instruments. What about the thing you're actually testing?

**Next:** [Modelling a DUT](duts.md)
