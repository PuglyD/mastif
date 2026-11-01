# Guide: test your driver without hardware

Concepts: [Testing kit](../../learn/architecture/testing-kit.md). Design: ADR-0024, ADR-0025.

## Install

```toml
[dependency-groups]
dev = ["pytest", "mastif-testing"]
```

## 1. Contract conformance

```python
from mastif_testing import assert_satisfies
from mastif.resources.std import PowerSupply


def test_psu_x_satisfies_power_supply():
    """PsuX implements every PowerSupply method with compatible parameters."""
    assert_satisfies(PsuX, PowerSupply)
```

## 2. Lifecycle conformance

```python
from mastif_testing import FakeLineIO, check_lifecycle
from mastif.resources.transports import Scpi

TCP = {"transport": {"kind": "tcp", "host": "h", "port": 1}}


def test_psu_x_lifecycle():
    """PsuX builds, opens, identifies, reports healthy, makes itself safe and closes."""
    fake = FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4", "SYST:ERR?": '0,"No error"'})
    report = check_lifecycle(PsuX, TCP, io=Scpi(fake))
    assert report.identity.serial == "A123"
    assert report.safe_state_ran
```

Pass one fake per I/O parameter, keyed by the parameter's name in `__init__`.

## 3. Behaviour tests with scripted replies

```python
import pytest
from mastif.kernel.units import mV
from mastif.resources.driver import build_resource, spec_of
from mastif.resources.errors import ProtocolError


def _psu(replies):
    """Build PsuX over a FakeLineIO, exactly as the station would."""
    fake = FakeLineIO(replies)
    built = build_resource(spec_of(PsuX), TCP, name="psu", io_factory=lambda *_: Scpi(fake))
    return built.instance, fake


def test_set_voltage_sends_volts_with_four_decimals():
    """Voltages are sent in volts, whatever unit the test used."""
    psu, fake = _psu({})
    psu.set_voltage(12_000 * mV)
    assert fake.written == ["VOLT 12.0000"]


def test_overrange_reading_is_an_error():
    """An overflow marker raises instead of returning a huge 'valid' current."""
    psu, _ = _psu({"MEAS:CURR?": "9.9E37"})
    with pytest.raises(ProtocolError):
        psu.measure_current()
```

## 4. Timing and framing

```python
from mastif_testing import FakeStream


def test_reply_split_across_packets_is_reassembled():
    """A reply arriving in pieces is still read as one frame."""
    s = FakeStream()
    s.open()
    s.feed(b"\x00\x00")
    s.feed(b"\x01\x00")
    assert s.read_exactly(4) == b"\x00\x00\x01\x00"
```

## 5. UDP devices

```python
from mastif_testing import FakeDatagramPeer
from mastif.resources.transports import DatagramChannel, UdpConfig


def test_temperature_ignores_status_broadcasts():
    """A status message arriving first is not taken as the reply."""

    def device(msg):
        peer.push(b"STATUS ok")
        return b"TEMP 41.5" if msg == b"TEMP?" else None

    with FakeDatagramPeer(device) as peer:
        ch = DatagramChannel(UdpConfig(host="127.0.0.1", port=peer.port))
        ch.open()
        assert ch.request(b"TEMP?", match=lambda m: m.startswith(b"TEMP ")) == b"TEMP 41.5"
        ch.close()
```

## Principles

- **Test the station's construction path:** `build_resource` with an `io_factory`, never
  `PsuX.__new__` tricks.
- **Script only the replies the device would really send.** A missing reply times out,
  as it would on the bench.
- **Assert on `fake.written`** to pin down the exact commands.
