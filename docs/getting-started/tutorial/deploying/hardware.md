# Connecting real hardware

Everything so far has run in memory. In this chapter we swap the simulator for a real instrument, and the
pleasing part is how little of our code has to change. The less pleasing part is that real hardware brings
a set of problems no simulator warned us about, and those are what this chapter is really about.

!!! success "Works today"
    The station and transports are implemented. The `acme.psu-x` driver is fictional, so you'll need a driver for
    the instrument you own. [Your first driver](../hardware-integration/first-driver.md) shows how to write one.

## What changes

Here's the profile again, this time for a real bench:

```yaml title="stations/bench-01.yaml"
station: bench-01
resources:
  bench_supply:
    driver: acme.psu-x
    config:
      transport: {kind: tcp, host: 192.0.2.10, port: 5025, timeout: 2.0}
    expect: {serial: A123}
roles:
  supply: bench_supply
```

Here's what changed in the test: nothing. It still asks for `supply`, and it still gets something that behaves like a
`PowerSupply`.

Three things have changed in the profile. Let's see what each of them does.

**`driver: acme.psu-x`** names a driver from an SDK. Rather than listing classes by hand, your application asks the
registry to find whatever's installed:

```python title="excerpt: find every installed driver"
from mastif.resources.registry import Registry

registry = Registry.discover()
print(registry.ids())
```

Your SDK advertises its drivers through a Python entry point, so there's nothing to configure, and mastif doesn't need to
know your package's name. We'll set that up in [Packaging an organisation SDK](../hardware-integration/packaging.md).

**`transport`** says how to reach this one. The driver asked for a connection that speaks SCPI, and it doesn't care how
it's carried. If a different bench reaches the same instrument over serial, only this line differs:

```yaml title="the same instrument on another bench"
transport: {kind: serial, port: COM3, baudrate: 115200}
```

The recipe on [SCPI over TCP, serial or VISA](../../../learn/recipes/scpi.md) has more detail.

**`expect`** says what this instrument must report about itself. Why bother, when the address is right there?
Because the address tells you where you're connecting, not what's there. An instrument gets swapped, a cable moves to a
different port, or two identical supplies get transposed. All of these connect perfectly well, and they all give you results
from the wrong device. When the station opens, it asks the instrument who it is and compares the answer:

```text title="Real output"
IdentityMismatch: bench_supply: serial is 'SIM-001', expected 'OTHER'
```

Think about what that protects. If the instrument's serial doesn't match, the run stops before your test touches it. The
serial also goes into the run record, so results can be traced to a specific piece of calibrated equipment.

## Before you connect anything: think about what's new

Moving from simulation to hardware isn't just a configuration change. Here's what you've been protected from up to now.

| In simulation | On a real bench |
|---|---|
| A configured number comes back | The instrument performs a real measurement, with noise |
| Everything happens instantly | Every command takes time, and settling takes longer |
| Identity is fixed | Identity is read from the device, and it can be wrong |
| Failures happen when you ask for them | Failures happen without warning |
| Nothing can be damaged | You're energising something real |

## Settling: the bug a simulator will never show you

Here's part of our test from earlier, looked at again with real physics in mind:

```python title="the task's hooks — preview"
def setup(self, ctx):
    self.supply.set_voltage(self.config.voltage)
    self.supply.set_current_limit(500 * mA)
    self.supply.output(True)

def run(self, ctx):
    ctx.measure("idle_current", self.supply.measure_current(), ...)
```

On our simulator, that's correct. On a real bench, it's wrong, and in a nasty way. When you turn the output on, a real board
draws an inrush current, boots its firmware, and only then settles to its idle draw. Read immediately, and you'll measure the
inrush or the boot, not idle. The board isn't idle yet, and our requirement was about *idle*.

So how long should you wait? The instinct is `time.sleep(5)`. That works today, and it's a trap: it makes every test five
seconds slower, whether the board needed it or not, and next year's firmware might boot in six.

The better question is: **how would you know the board is idle?** If it can tell you, ask it. That's a piece of product
knowledge, and it belongs on the DUT:

```python title="the same hooks, with a DUT — preview"
class IdleCurrent(Task[IdleCurrentConfig]):
    id = "idle_current"

    supply: PowerSupply = requires("supply")
    board: WidgetBoard = requires("dut")

    def setup(self, ctx):
        self.supply.set_voltage(self.config.voltage)
        self.supply.set_current_limit(500 * mA)
        self.supply.output(True)
        self.board.wait_until_idle(timeout=10.0)

    def run(self, ctx):
        ctx.measure("idle_current", self.supply.measure_current(), ...)
```

Now the test waits for exactly as long as the board needs, and if the board never reaches idle, you get a clear
`TransportTimeout` rather than a confusing current reading. A fixed delay is sometimes the only option, when the device gives
you no signal at all. When that's the case, make it a configuration value, and write down why it has that value.

`WidgetBoard` is a DUT type, which you'd write as part of your SDK. See [Modelling a DUT](../hardware-integration/duts.md).

## Protection isn't a requirement

Look at those two limits again:

```python title="excerpt"
self.supply.set_current_limit(500 * mA)    # Protects the hardware
Limits.at_most(self.config.max_current)    # Judges the board: 250 mA
```

They're both current limits, and they're doing completely different jobs. The first tells the instrument to stop
pushing current past 500 mA, so that a shorted board doesn't burn. The second decides whether the board meets its specification.
Neither should be derived from the other. There's a subtle trap too, if you set the protection limit too low: a supply in current
limit reads back exactly the limit, a beautifully stable number, which might even pass. If you have a tight limit, a good test
also checks that the supply wasn't limiting.

## Bringing up a new bench

When a bench is new, resist running the full test first. Work up in stages, because each stage rules out a different family of
problems, and a failure at any one of them is much easier to read in isolation.

**1. Build it.** No hardware is touched, so this finds profile and driver problems.

```python title="excerpt"
station = Station.build(StationProfile.load("stations/bench-01.yaml"), Registry.discover())
print(station.role_problems({"supply": PowerSupply}))
```

**2. Open it, and do nothing else.** This proves connectivity, identity and health.

```python title="excerpt"
with station:
    print(station.identities())
```

**3. Read something harmless.** A voltage reading with the output off proves that commands and parsing work, and it can't hurt
anything.

**4. Only then, apply power**, with a conservative current limit, and with someone watching the bench the first time.

!!! danger "mastif is not your safety system"
    The station makes a determined attempt to leave hardware in a safe state, and it reports what it couldn't do. But if the
    connection is gone, no software can turn that output off. Anything that could hurt a person or damage expensive equipment
    needs a hardware interlock, independent of this software.

## Recap

- Moving to hardware **changes the profile, not the test**: a driver, a transport and an expected identity.
- `expect` catches the wrong device connected at the right address, before anything happens to it.
- **Settling is your problem**: wait for a real signal from the DUT wherever you can, not an arbitrary delay.
- Bring up a new bench **in stages**, so that each failure means one thing.

We've mentioned opening and closing several times now. The next chapter opens up that machinery, and it's the part of mastif we're
most careful about.

**Next:** [Opening, checking, and closing a station](lifecycle.md)
