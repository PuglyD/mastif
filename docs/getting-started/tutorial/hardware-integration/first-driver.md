# Your first driver

So far we've used a power supply without asking where it came from. In this part of the tutorial, we're on the other side of that
contract. You've got a real instrument on your desk, a programming manual, and a job to do: make that instrument available to every test in your
organisation, in such a way that none of those tests ever need to read the manual.

That's what a driver is for. By the end of this chapter you'll have written one and tested it, with no instrument connected.

!!! success "Works today"
    Everything on this page runs against the current code. It uses a scripted fake in place of a real instrument.

## What a driver is responsible for

Before writing any code, let's get the job description straight, as a driver is easy to overload. A driver holds **knowledge about one kind of
device**: which command does what, and how to read its replies.

| A driver knows | A driver doesn't know |
|---|---|
| `MEAS:CURR?` reads the current | That 250 mA is too much |
| The reply is in amperes | Why anyone wants the current |
| `9.9E37` means overrange | Which bench it's on |
| How to ask for its serial number | Which serial number is expected |
| What "safe" means for this device | When to make it safe |
| | How the bytes reach the device |

The right-hand column is what separates a reusable driver from one that works only for the project that it was written for. If a pass limit creeps into a
driver, then that driver can only be used for that product. If an IP address creeps in, it only works on one bench.

## Step 1: Choose the capability

Your driver will provide a contract. Start by asking whether the built-in one fits. Ours is a bench supply, and `mastif.resources.std.PowerSupply`
describes that well, so let's use it. If your instrument does something that no existing contract covers, you'll write your own, as we'll do in the
[next chapter](contracts.md).

## Step 2: Read the manual

Our fictional instrument speaks **SCPI** (*Standard Commands for Programmable Instruments*), the text-based command language that most modern bench
instruments use. You send a line of text, and queries, which end in `?`, get a line back. From the manual:

| Command | Effect |
|---|---|
| `VOLT 5.0` | Set the output voltage, in volts |
| `CURR 0.5` | Set the current limit, in amperes |
| `OUTP ON`, `OUTP OFF` | Switch the output |
| `MEAS:VOLT?` | Measure the voltage; replies in volts |
| `MEAS:CURR?` | Measure the current; replies in amperes |
| `*IDN?` | Identify; replies `vendor,model,serial,revision` |

## Step 3: Write it

Here's the complete driver. Take a read through, and then we'll go over the interesting parts.

```python title="excerpt of docs/examples/learn_driver.py"
--8<-- "examples/learn_driver.py:16:56"
```

### The decorator

`@driver("demo.learn-scpi", provides=[PowerSupply])` gives the driver a globally unique id, which is what a station profile uses to refer to it, and it declares
what it provides. The convention for ids is `org.name` in lowercase.

Crucially, the decorator isn't only a label. It does a full inspection of your class **at import time**, and it refuses to let the module load if anything's wrong:

- The id has to be well formed.
- Every method in the contract has to exist, with compatible parameters.
- Every constructor parameter has to be something mastif can supply.

```text title="Real output, from forgetting four methods"
ContractMismatch: demo.bad2 does not provide PowerSupply: set_current_limit: missing,
output: missing, measure_voltage: missing, measure_current: missing
```

### The config

```python title="excerpt"
class Config(DriverConfig):
    transport: TcpConfig
```

This nested class describes what can appear under `config:` in a station profile. It's a Pydantic model that forbids unknown fields, so a typo in somebody's profile is
caught at build time. The `transport` field has a special meaning: it's where the station gets the connection details. You'll see how to accept more than one kind of
connection in the [SCPI recipe](../../../learn/recipes/scpi.md).

### The constructor

```python title="excerpt"
def __init__(self, cfg: Config, io: Scpi) -> None:
    self.io = io
```

There's something important about what this *doesn't* do. It doesn't open a socket. It doesn't parse an address, and it doesn't construct a `Scpi`. It says, "I need something that speaks SCPI",
and the station passes one in, by reading your type annotations. This technique is known as **dependency injection**, and we're relying on it for two reasons.

First, there's the separation. A driver that opens its own socket has decided how the device is reached, so it can't be used over serial. This one can be used over anything that can carry lines of text.

Second, and this is the big one, your driver can be tested with no hardware at all, as we're about to do.

**A constructor must never do I/O.** This is what makes [build first, open later](../deploying/profiles.md#build-first-open-later) possible: a station can be built, and a profile checked, on a machine
with no instruments. Store what you were given, and leave it at that. If you need to talk to the device at start-up, there's a hook for that.

### Crossing the unit boundary

```python title="excerpt"
def set_voltage(self, voltage: Volts) -> None:
    self.io.write(f"VOLT {voltage.magnitude('V'):.4f}")

def measure_current(self) -> Amps:
    return self.io.query_quantity("MEAS:CURR?", "A")
```

Here's what we said in the [units chapter](../writing-tests/measurements.md): values and units only separate at a boundary that requires a bare number. This is that boundary, and it's the one place in the
whole system where the conversion happens. If somebody calls `set_voltage(5000 * mV)`, the instrument still receives `VOLT 5.0000`. On the way back, `query_quantity` attaches the unit to the reply, so the
caller gets a real quantity.

`query_quantity` does some other useful work too. If the reply isn't a number, it raises `ProtocolError`, and if the reply is `9.9E37`, the overrange marker, it raises as well. So a bad reading can't
reach a test disguised as a measurement.

### What's optional

You might have noticed there's no `close` method and no `safe_state`. Those hooks are optional, and the station calls those that exist, in a fixed order:

| Hook | Called when | Purpose |
|---|---|---|
| `open()` | After the I/O is open | Prepare the device. No stimulus yet |
| `identify()` | After `open` | Report an `Identity`, compared with `expect:` |
| `health()` | After `identify` | Report whether it's fit to use |
| `children()` | After `health` | Report sub-resources |
| `safe_state()` | At shutdown | Put the hardware somewhere harmless |
| `close()` | Before the I/O closes | Release anything the driver itself acquired |

We don't need `safe_state`, because the `PowerSupply` contract already declares "output off". We'll go deeper on these hooks in [Identity, health, and safe state](identity.md).

## Step 4: Test it without the instrument

Now for the part that makes all of the above worthwhile.

```python title="excerpt of docs/examples/learn_driver.py"
--8<-- "examples/learn_driver.py:59:89"
```

Instead of connecting to anything, we pass in a `FakeLineIO`, a scripted stand-in for the instrument's connection. It's told what to reply to each command, and it records everything that was written
to it. Then we assert on both directions:

- **Outgoing:** given 5000 mV, did the driver really send `VOLT 5.0000`?
- **Incoming:** given a reply of `0.180`, did it really return 180 mA?

Run it:

<!-- termynal: {title: "Real transcript · learn_driver.py"} -->
```console
$ uv run python docs/examples/learn_driver.py
command: VOLT 5.0000
reading: 180 mA
conformance: identity checked; safe-state action ran
```

That's a real test of your real driver code, running in milliseconds, in your CI, for an instrument that you might not even have purchased yet. Conversions and parsing are exactly the kinds of bugs that take
half a day to find on a bench, so catching them here is well worth it. We'll cover this much more thoroughly in [Testing drivers with fake I/O](fake-io.md).

## Step 5: Use it from a station

To use your driver from a profile, your package advertises it (see [Packaging an organisation SDK](packaging.md)), and then any bench can refer to it by id:

```yaml title="stations/bench-01.yaml"
station: bench-01
resources:
  bench_supply:
    driver: demo.learn-scpi
    config:
      transport: {kind: tcp, host: 192.0.2.10, port: 5025}
    expect: {serial: A123}
roles:
  supply: bench_supply
```

And that's all there is to it. Every test that asks for a `PowerSupply` in the `supply` role now works with your instrument, and none of them changed.

## A few rules of thumb

- **Raise, don't return a placeholder.** Never return `0.0`, or `None`, to mean "it failed". It's [how broken benches pass bad boards](../writing-tests/failures.md).
- **Take and return quantities.** Use a `Quantity` for anything physical. A plain `float` is fine for a timeout, as that's configuring the I/O rather than describing the device.
- **Never open your own sockets.** Ask for what you need in the constructor.
- **Leave test logic out.** If it's a judgement about what's good, it doesn't belong here.
- **Keep it thin.** A driver translates. Elaborate procedures belong in a task, or in a DUT type.

## Recap

A driver is one class that translates a capability into one device's language. It declares what it provides, asks for its connection rather than opening one, and is checked at import time. And because its I/O is
passed in, you can test all of it without the instrument.

Next, let's look at what to do when the built-in contracts don't describe your instrument.

**Next:** [Defining a capability contract](contracts.md)
