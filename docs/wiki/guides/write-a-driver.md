# Guide: write a driver

You'll write an instrument driver for a fictional SCPI bench supply, the "ACME PSU-X",
register it, and use it from a station. Concepts: [Resources](../resources.md). Design:
ADR-0008, ADR-0011, ADR-0012, ADR-0016.

## 1. Pick or define the contract

Use the built-in one if it fits:

```python
from mastif.resources.std import PowerSupply
```

Or define your own. It's a plain Protocol, and doesn't need a mastif import:

```python
from typing import Protocol
from mastif.kernel.units import Volts, Amps


class ProtectedSupply(PowerSupply, Protocol):
    def set_ovp(self, voltage: Volts) -> None: ...
```

Keep contracts small. A test should need everything a contract declares.

## 2. Write the driver

```python
# acme_sdk/drivers/psu_x.py
from mastif.kernel.units import Amps, Volts
from mastif.resources.driver import DriverConfig, driver
from mastif.resources.identity import Health, Identity
from mastif.resources.std import PowerSupply
from mastif.resources.transports import Scpi, TcpConfig, VisaConfig


@driver("acme.psu-x", provides=[PowerSupply])
class PsuX:
    """ACME PSU-X single-channel bench supply."""

    class Config(DriverConfig):
        transport: TcpConfig | VisaConfig  # works over LAN or USB-TMC
        channel: int = 1

    def __init__(self, cfg: Config, io: Scpi) -> None:
        self.cfg = cfg
        self.io = io

    # optional lifecycle hooks: called by the station, in a fixed order
    def open(self) -> None:
        self.io.reset()  # known state at every run start

    def identify(self) -> Identity:
        return self.io.identify()  # *IDN? → Identity

    def health(self) -> Health:
        errs = self.io.errors()
        return Health(ok=not errs, detail="; ".join(errs))

    # the contract
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
```

**Rules the decorator enforces when the module is imported:**

- The id looks like `org.name`, in lowercase.
- `Config` subclasses `DriverConfig`. A `transport` field is required if you ask for
  injected I/O.
- Every `__init__` parameter is the config, an I/O type (`StreamTransport`, `LineIO`,
  `Scpi`, `DatagramChannel`), a `logging.Logger`, or has a default.
- Every contract in `provides` is implemented, with compatible parameters.

**Rules by convention:**

- Take and return `Quantity` values for anything physical.
- Raise errors (`ProtocolError`, `ResourceFault`); never return `0.0` or `None` to mean
  "failed".
- No safe-state hook is needed here: `PowerSupply` already declares "output off".
  Add `safe_state()` only if your device needs something different.
- Don't open sockets yourself. Don't put test logic in drivers.

## 3. Advertise it

```toml
# acme_sdk/pyproject.toml
[project.entry-points."mastif.drivers"]
acme = "acme_sdk.drivers"        # a module; every @driver class in it is found
```

## 4. Use it on a bench

```yaml
resources:
  bench_psu:
    driver: acme.psu-x
    config: {transport: {kind: tcp, host: 10.0.0.5, port: 5025}, channel: 1}
    expect: {serial: A123}
roles: {psu_main: bench_psu}
```

## 5. Test it without hardware

See [Test your driver](test-your-driver.md). In short:

```python
def test_psu_x_conforms():
    fake = FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4", "SYST:ERR?": '0,"No error"'})
    report = check_lifecycle(
        PsuX, {"transport": {"kind": "tcp", "host": "h", "port": 1}}, io=Scpi(fake)
    )
    assert report.identity.serial == "A123"
```

## Binary or non-SCPI devices

- Ask for `io: LineIO` for plain text protocols.
- Ask for `io: StreamTransport` for binary frames, and use `read_exactly` /
  `read_until`.
- Ask for `io: DatagramChannel` for UDP.

The station builds whichever you ask for from the profile's `transport:` block.
