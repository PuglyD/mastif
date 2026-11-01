# Testing kit

Drivers and DUT code have to be tested on every commit, and without hardware. The obvious tool for that is a mock, and it's the wrong one here. A mock answers whatever you told it to, and it never times out, so your tests pass while your driver is broken.

`mastif-testing` provides something better: **behavioural fakes**, which act like real silent, slow or chatty devices, and **conformance checks**, which vet any driver against what mastif expects of it. It's a separate package, so that your SDK can install it in its own test environment without shipping it to stations.

!!! success "Works today"
    Everything on this page runs against the current code. **Package:** `mastif-testing`, imported as `mastif_testing`. **API:** [reference](../../reference/testing/index.md). For how to use them, see [Testing drivers with fake I/O](../../getting-started/tutorial/hardware-integration/fake-io.md).

## Fakes

Each fake stands in for one layer of [the transport stack](transports.md), and it follows that layer's real rules.

| Fake | Stands in for | How it behaves |
|---|---|---|
| `FakeLineIO(replies)` | `LineIO` | A scripted reply per command, where lists repeat their last entry. `written` records what was sent. If nothing's queued, it raises `TransportTimeout`. |
| `FakeStream()` | `StreamTransport` | Uses the real framing code. `feed(bytes)` makes data readable, and `sent` holds what was written. |
| `FakeSshSession(commands)` | `SshSession` | Scripted results per command: a string, a `ShellResult`, or an exception. |
| `FakeNativeLibrary(functions)` | `NativeLibrary` | Python callables or status codes for vendor functions, with the same rules as the real library. `set_out` fills output parameters. |
| `FakeDatagramPeer(responder)` | A UDP device | A real localhost socket, where `push()` sends unsolicited messages. |

```python
from mastif.resources.transports import Scpi
from mastif_testing import FakeLineIO

io = FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4", "MEAS:CURR?": ["0.10", "0.18"]})
scpi = Scpi(io)
print(scpi.identify().serial)           # A123
print(scpi.query_float("MEAS:CURR?"))   # 0.1
print(scpi.query_float("MEAS:CURR?"))   # 0.18
print(io.written)
```

The default behaviour is the important part. A command that hasn't been scripted raises `TransportTimeout`, exactly like a silent instrument, so your error handling gets exercised without you having to arrange it.

## Conformance

Two helpers check what's the same for every driver, so that you don't need to write these yourself.

```python title="excerpt: PsuX is your driver"
from mastif_testing import assert_satisfies, check_lifecycle


def test_psu_x_is_a_power_supply():
    assert_satisfies(PsuX, PowerSupply)


def test_psu_x_conforms():
    fake = FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4"})
    report = check_lifecycle(
        PsuX, {"transport": {"kind": "tcp", "host": "h", "port": 1}}, io=Scpi(fake)
    )
    assert report.identity.serial == "A123"
    assert fake.written[-1] == "OUTP OFF"   # Safe state switched the output off
```

`check_lifecycle` builds the driver through the **real** construction path, with your fakes injected. It then runs `open`, `identify`, `health`, safe state and `close`, skipping hooks you haven't defined, and it fails naming the exact step. See [Checking contract and lifecycle conformance](../../getting-started/tutorial/hardware-integration/conformance.md), [ADR-0024](../../adr/0024-testing-fakes.md) and [ADR-0025](../../adr/0025-conformance-kit.md).

## Recap

- **Behavioural fakes** act like real devices, and that includes failing like them.
- **Conformance checks** verify what's common to every driver, through the real construction path.

That covers everything that's been built. The last few pages are for reference: lessons from the field, every error, and every term.

**Next:** [Field notes](field-notes.md)
