# Checking contract and lifecycle conformance

Your driver will be used by a station that follows some strict rules: it calls hooks in a certain order, expects `identify` to return an `Identity`, and depends on safe state working when things have gone wrong. There's no need for each driver author to write a test for each of those rules. They're the same for every driver, so mastif provides
them, and you can get them in a couple of lines.

!!! success "Works today"
    Everything on this page runs against the current code, with no hardware.

## Two questions

The `mastif_testing` package answers two questions about any driver. Is it the right shape? And does it get through the lifecycle?

```python
from mastif.kernel.units import Amps, Volts
from mastif.resources.driver import DriverConfig, driver
from mastif.resources.identity import Identity
from mastif.resources.std import PowerSupply
from mastif.resources.transports import Scpi, TcpConfig
from mastif_testing import FakeLineIO, assert_satisfies, check_lifecycle


@driver("demo.conforming", provides=[PowerSupply])
class Conforming:
    class Config(DriverConfig):
        transport: TcpConfig

    def __init__(self, cfg: Config, io: Scpi) -> None:
        self.io = io

    def identify(self) -> Identity:
        return self.io.identify()

    def set_voltage(self, voltage: Volts) -> None:
        self.io.write(f"VOLT {voltage.magnitude('V'):.4f}")

    def set_current_limit(self, current: Amps) -> None:
        self.io.write(f"CURR {current.magnitude('A'):.4f}")

    def output(self, enabled: bool) -> None:
        self.io.write("OUTP ON" if enabled else "OUTP OFF")

    def measure_voltage(self) -> Volts:
        return self.io.query_quantity("MEAS:VOLT?", "V")

    def measure_current(self) -> Amps:
        return self.io.query_quantity("MEAS:CURR?", "A")


# Is it the right shape?
assert_satisfies(Conforming, PowerSupply)

# Does it get through the lifecycle?
fake = FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4"})
report = check_lifecycle(
    Conforming,
    {"transport": {"kind": "tcp", "host": "192.0.2.10", "port": 5025}},
    io=Scpi(fake),
)

print(report.steps)            # ['build', 'identify', 'safe_state']
print(report.identity.serial)  # A123
print(report.safe_state_ran)   # True
print(fake.written)            # ['*IDN?', 'OUTP OFF']
```

### Is it the right shape?

`assert_satisfies` compares a class with a contract, including each method's parameters, and raises an `AssertionError` naming anything that's wrong. `@driver` already does this for each contract in its `provides` list when it's imported. So why would you want this as well? It's for when a class gets checked against a contract it doesn't declare. For
instance, in a test that makes sure your driver also satisfies a new, narrower contract:

```python title="excerpt"
assert_satisfies(Conforming, CurrentReader)
```

### Does it get through the lifecycle?

`check_lifecycle` takes the driver class, a `config` mapping (the same thing that would appear in a profile), and a fake for each I/O parameter, by the parameter's name. Then it runs the driver through the same sequence a station uses: build, `open`, `identify`, `health`, safe state, `close`. It skips any hooks that you didn't define (this driver has no `open`, `health` or `close`, so they don't appear in `steps`), and it raises an `AssertionError`
naming the step if anything fails.

So a single test gives you a lot of checks. Your `Config` accepts a realistic profile. Your constructor annotations can be satisfied. Your hooks don't raise. `identify` returns an `Identity`, and `health` returns something healthy. A safe-state action exists and runs. And `close` works.

## The report is where it gets interesting

`check_lifecycle` returns a report, so you can make assertions that are specific to your device.

| Field | What it tells you |
|---|---|
| `steps` | The lifecycle steps that were run, in order |
| `identity` | What `identify()` returned, if you've defined it |
| `health` | What `health()` returned, if you've defined it |
| `safe_state_ran` | Whether a safe-state action ran |
| `instance` | The driver object, for further poking |

Pay particular attention to `safe_state_ran`. It tells you that an action *ran*, not that it was the right one. So the most valuable line in a conformance test is usually the one that follows, where you look at what the action actually did:

```python title="continuing the example above"
assert "OUTP OFF" in fake.written
```

It's a one-line check that the thing which protects your hardware really sends the command you think it does.

## Put it in your test suite

Here's a pattern we'd suggest for every driver in your SDK. It's short, so there's little excuse for skipping it:

```python title="tests/test_psu_x.py"
import pytest

from demo_sdk.drivers import PsuX
from mastif.resources.std import PowerSupply
from mastif.resources.transports import Scpi
from mastif_testing import FakeLineIO, assert_satisfies, check_lifecycle

CONFIG = {"transport": {"kind": "tcp", "host": "192.0.2.10", "port": 5025}}


def test_is_a_power_supply():
    assert_satisfies(PsuX, PowerSupply)


def test_lifecycle():
    fake = FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4", "SYST:ERR?": '0,"No error"'})
    report = check_lifecycle(PsuX, CONFIG, io=Scpi(fake))
    assert report.identity.serial == "A123"
    assert "OUTP OFF" in fake.written
```

As it runs in milliseconds and needs no hardware, it can go in your CI, and then a change that breaks a driver's lifecycle is caught at review.

## What conformance doesn't prove

It's the same story that we've told about each testing tool, and it's still true here. Let's be specific.

| Conformance establishes | It doesn't establish |
|---|---|
| The methods exist and can be called correctly | That they do the right thing |
| The hooks run in the station's order | That the commands are correct for this instrument |
| A safe-state action exists and runs | That the hardware actually became safe |
| It doesn't raise against this script | How it behaves against anything else |

So don't think of this as a replacement for the [behaviour tests](fake-io.md) that we covered in the last chapter. A driver can pass here, and still swap volts and amps. Conformance checks that your driver fits the framework, and behaviour tests check that it does its job. You'll want both, and then time on a real bench too, where someone observes independently that the output
really did go off. (A meter across the output is a wonderful thing.)

## Recap

- **`assert_satisfies`** checks a class's shape against a contract.
- **`check_lifecycle`** runs a driver through the station's sequence, and returns a report.
- Always **assert what safe state actually sent**, not merely that it ran.
- It's quick to add, so **add it for every driver**, and keep your behaviour tests as well.

Your drivers are now written and tested. The last step is to get them to the stations.

**Next:** [Packaging and discovering an organisation SDK](packaging.md)
