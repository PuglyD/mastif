# Testing kit (`mastif-testing`)

**Package:** `mastif-testing`, imported as `mastif_testing`. **ADRs:** 0024 (fakes), 0025
(conformance).

## Why it exists

Drivers and DUT code must be tested on every commit, without hardware. Mocks are the
wrong tool for this: they answer whatever they were told, and never time out, so tests
pass while drivers are broken. This package provides **behavioural fakes**, which act
like real silent, slow or chatty devices, plus **conformance checks**, which vet any
driver against mastif's obligations. It is a separate package, so org SDKs can install
it in their own test environments.

## Fakes

| Fake | Stands in for | Behaviour |
|---|---|---|
| `FakeLineIO(replies)` | `LineIO` | Scripted reply per command (lists repeat their last entry). `written` records what was sent. Nothing queued raises `TransportTimeout`. `feed()` adds unsolicited lines. |
| `FakeStream()` | `StreamTransport` | Uses the real framing code (`BufferedStream`). `feed(bytes)` makes data readable; `sent` holds what was written. |
| `FakeDatagramPeer(responder)` | a UDP device | A real localhost socket. `responder(msg) -> reply or None`. `push()` sends unsolicited messages. `received` records everything. |

```python
from mastif_testing import FakeLineIO
from mastif.resources.transports import Scpi

io = FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4", "MEAS:CURR?": ["0.10", "0.18"]})
scpi = Scpi(io)
scpi.identify().serial  # "A123"
scpi.query_float("MEAS:CURR?")  # 0.10, then 0.18 forever
io.written  # ["*IDN?", "MEAS:CURR?"]
```

## Conformance

```python
from mastif_testing import assert_satisfies, check_lifecycle


def test_psu_x_is_a_power_supply():
    assert_satisfies(PsuX, PowerSupply)  # one line per problem if not


def test_psu_x_conforms():
    fake = FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4"})
    report = check_lifecycle(
        PsuX, {"transport": {"kind": "tcp", "host": "h", "port": 1}}, io=Scpi(fake)
    )
    assert report.identity.serial == "A123"
    assert fake.written[-1] == "OUTP OFF"  # safe state switched the output off
```

`check_lifecycle` builds the driver through the **real** construction path, with your
fakes injected. It then runs `open → identify → health → safe state → close`, and fails
naming the exact step: `"acme.psu-x: step 'identify' failed: ..."`.

## Where to look

| What | Where |
|---|---|
| Code | `packages/mastif-testing/src/mastif_testing/` |
| Guide | [Test your driver](guides/test-your-driver.md) |
| API | [reference](../reference/testing.md) |
