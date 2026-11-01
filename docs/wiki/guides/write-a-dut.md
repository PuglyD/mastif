# Guide: write a DUT type

A **DUT type** describes the product you test: how to reach it (channels), what it can
do (product methods), and its live state. Concepts: [Resources](../../learn/architecture/resources.md).
Design: ADR-0011, ADR-0019, ADR-0020, ADR-0023.

## 1. Decide the channels

Ask what ways into the product a test needs. For example:

- a **console** to run commands: the `Shell` contract
- a **control port** for UDP messages: the `MessageChannel` contract

Channels are declared by contract, not by medium. Which physical port each one uses is
the station profile's business.

## 2. Write the class

```python
from pydantic import BaseModel
from mastif.resources.driver import channel, dut
from mastif.resources.errors import ProtocolError
from mastif.resources.identity import Identity
from mastif.resources.std import MessageChannel, Shell


class WidgetState(BaseModel):
    booted: bool = False
    firmware: str | None = None


@dut("demo.widget-board", state=WidgetState)
class WidgetBoard:
    """The Widget board, reached over its console and UDP control port."""

    console: Shell = channel()
    ctrl: MessageChannel = channel(optional=True)  # absent on some benches
    state: WidgetState  # created by mastif; annotate for typing

    def open(self) -> None:
        # channels are already open here: the station opens them first
        version = self.console.execute("version").output
        self.state.booted = True
        self.state.firmware = version

    def identify(self) -> Identity:
        serial = self.console.execute("cat /etc/serial").output
        return Identity(serial=serial, revision=self.state.firmware)

    # product methods your tests call
    def temperature(self) -> float:
        reply = self.ctrl.request(b"TEMP?", match=lambda m: m.startswith(b"TEMP "))
        try:
            return float(reply.split()[1])
        except (IndexError, ValueError):
            raise ProtocolError(f"bad TEMP reply {reply!r}") from None
```

## 3. Map the channels on each bench

```yaml
resources:
  dut:
    driver: demo.widget-board
    expect: {}                         # the scanned serial is passed at run time
    channels:
      console:
        driver: mastif.line-shell
        config:
          transport: {kind: serial, port: COM3, baudrate: 115200}
          prompt: "# "
          exit_code_command: "echo $?"
      ctrl:
        driver: mastif.udp
        config: {transport: {kind: udp, host: 192.168.1.50, port: 9000}}
```

The same DUT on a bench where it is reached over SSH needs only a different profile
entry. `mastif.ssh-shell` runs each command over SSH and reports real exit codes:

```yaml
      console:
        driver: mastif.ssh-shell
        config:
          transport: {kind: ssh, host: 192.168.1.60, username: root,
                      key_file: ~/.ssh/id_ed25519}
```

In unit tests, give the DUT a `FakeSshSession` (or a `FakeStream` for console shells)
through the station's `io_factory`, or call the channel driver directly.

**What the station checks at build time:**

- Every required channel is mapped.
- No unknown channel is mapped.
- Each channel driver provides the declared contract.

**At open time:** the channels open first, then your `open()` runs, then `identify()`
is checked against `expect:` and the operator's scanned serial.

## 4. Custom channels

If a built-in channel doesn't fit, write a channel driver like any driver. An example is
a framed binary protocol over TCP:

```python
@driver("demo.framed-tcp", provides=[MessageChannel])
class FramedTcp:
    class Config(DriverConfig):
        transport: TcpConfig

    def __init__(self, cfg: Config, io: StreamTransport): ...
```

Then map it: `ctrl: {driver: demo.framed-tcp, config: {...}}`.

## Tips

- Keep product *knowledge* in the DUT type: commands, parsing, state. Keep *test logic*
  (limits, sequences) in tasks.
- Raise `ProtocolError` for malformed replies. Never return placeholder values.
- Put things that matter for resuming a run into `state`: booted, firmware, mode. The
  station snapshots it.
