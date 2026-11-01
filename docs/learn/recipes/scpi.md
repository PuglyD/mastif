# Use SCPI over TCP, serial, or VISA

**You have:** an instrument that speaks SCPI, which might be reached differently on different benches.

**You want:** one driver for it, with the connection chosen in the station profile.

!!! success "Works today"
    Everything on this page runs against the current code.

SCPI is a language, and it says nothing about how the text gets to the instrument. So your driver's commands and its connection are separate decisions, and mastif keeps them apart. You ask for a `Scpi` object, and you list which connections you've tested.

## The driver

```python
from mastif.kernel.units import Amps, Volts
from mastif.resources.driver import DriverConfig, driver
from mastif.resources.identity import Identity
from mastif.resources.std import PowerSupply
from mastif.resources.transports import Scpi, SerialConfig, TcpConfig, VisaConfig


@driver("acme.psu-x", provides=[PowerSupply])
class PsuX:
    class Config(DriverConfig):
        transport: TcpConfig | SerialConfig | VisaConfig

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
```

The union type on `transport` is the only thing that says which connections are allowed. Only list the ones you've really tested.

## The connections

In the profile, pick one, under `config.transport`. Here are the options:

=== "TCP"

    ```yaml
    transport: {kind: tcp, host: 192.0.2.10, port: 5025, timeout: 2.0}
    ```

    Port 5025 is the conventional port for raw SCPI over a network. No extra packages are needed.

=== "Serial"

    ```yaml
    transport: {kind: serial, port: COM3, baudrate: 115200, read_termination: "\r\n"}
    ```

    Install `mastif[serial]`. You'll need to get the baud rate and line endings right, and both are in the instrument's manual.

=== "VISA"

    ```yaml
    transport: {kind: visa, resource: "USB0::0x1234::0x5678::A123::INSTR"}
    ```

    Install `mastif[visa]`, plus a VISA backend from your instrument's vendor or `pyvisa-py`. VISA ignores the per-read timeout, using the resource's timeout instead.

## Things to check

**Line endings differ.** Most instruments use `\n`, and some use `\r\n`. When a command works in a terminal, but your driver times out, suspect this first.

**A VISA resource isn't the same as the raw TCP port.** `TCPIP0::192.0.2.10::INSTR` uses a different protocol to port 5025, even though both carry SCPI commands. Don't assume that one working means the other does.

**Errors can be silent.** An instrument that doesn't recognise a command may simply put an error in its queue, and say nothing. While you're bringing up a driver, turn on checking, so that every write looks for errors:

```python title="excerpt: slower, but very useful during bring-up"
io = Scpi(line_io, check_errors=True)
```

Alternatively, call `io.raise_on_errors()` at sensible points. Note that reading the queue empties it.

**Use `*OPC?` rather than `sleep`.** After a long operation, `io.wait()` waits for the instrument to say it's finished.

## Test it first

Test against a fake before you go near a bench. This checks your commands and your parsing:

```python title="continuing the example above"
from mastif.kernel.units import mV
from mastif.resources.driver import build_resource, spec_of
from mastif_testing import FakeLineIO

fake = FakeLineIO({"MEAS:CURR?": "0.180"})
built = build_resource(
    spec_of(PsuX),
    {"transport": {"kind": "tcp", "host": "h", "port": 5025}},
    name="psu",
    io_factory=lambda *_: Scpi(fake),
)
built.instance.set_voltage(5000 * mV)
assert fake.written == ["VOLT 5.0000"]
assert built.instance.measure_current().magnitude("mA") == 180
```

Then on a real device: check identity, take a reading of something you know, and check that it agrees with an independent meter.

## See also

- [Your first driver](../../getting-started/tutorial/hardware-integration/first-driver.md), for how all this fits together.
- [Communicating with a device](../../getting-started/tutorial/hardware-integration/communication.md), for the rest of the I/O stack.
- [ADR-0013](../../adr/0013-transport-configuration.md), [ADR-0015](../../adr/0015-line-io.md) and [ADR-0016](../../adr/0016-scpi.md), for the reasoning.

**Next:** [Talk to a DUT over SSH or a console](shell.md)
