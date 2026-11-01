# Modelling a DUT

So far, we've written drivers for instruments, which are things you measure with. Now let's look at the device under test, the product you're measuring. It has a console, maybe a control port, and a set of behaviours that are entirely specific to your organisation.

You'll probably write fewer DUT types than drivers, but they'll carry more of your organisation's knowledge than anything else in your SDK.

!!! success "Works today"
    DUT declarations, channels and state models are implemented. Examples use fakes, with no hardware. Recording a DUT's state into run snapshots is part of the engine, so that part is a design preview.

## Why give a product its own class?

Let's look at how product knowledge usually spreads through a test suite:

```python title="the approach we are avoiding"
def run(self, ctx):
    self.console.execute("echo 1 > /sys/class/widget/idle")
    time.sleep(2)
    version = self.console.execute("cat /etc/version").output.strip().split("-")[0]
    ...
```

There's a command string, a magic path, a delay, and a piece of parsing. Now multiply that by forty tests. When the next firmware moves that file, you'll be doing a search-and-replace across your whole test suite, and hoping that everyone wrote it the same way.

This knowledge should live in one place, behind names that describe intent:

```python title="preview"
def setup(self, ctx):
    self.board.enter_idle()

def run(self, ctx):
    ctx.check("firmware", self.board.firmware_version() == "2.1", detail=...)
```

That's what a **DUT type** is: the one class that knows how your product behaves. When the firmware changes, you've got exactly one file to update.

## Declaring a DUT

A DUT type looks a lot like a driver, with the `@dut` decorator instead of `@driver`, and with one big difference. An instrument usually has one connection. A DUT often has several ways in, known as **channels**.

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
    """The widget board, reached over its console and a UDP control port."""

    console: Shell = channel()
    ctrl: MessageChannel = channel(optional=True)
    state: WidgetState

    def open(self) -> None:
        self.state.firmware = self.console.execute("version").output
        self.state.booted = True

    def identify(self) -> Identity:
        serial = self.console.execute("cat /etc/serial").output
        return Identity(serial=serial, revision=self.state.firmware)

    def enter_idle(self) -> None:
        result = self.console.execute("widgetctl idle on")
        if result.exit_code not in (0, None):
            raise ProtocolError(f"could not enter idle: {result.output!r}")

    def temperature(self) -> float:
        reply = self.ctrl.request(b"TEMP?", match=lambda m: m.startswith(b"TEMP "))
        try:
            return float(reply.split()[1])
        except (IndexError, ValueError):
            raise ProtocolError(f"bad TEMP reply {reply!r}") from None
```

Let's work through it.

### Channels are declared by capability

```python title="excerpt"
console: Shell = channel()
ctrl: MessageChannel = channel(optional=True)
```

This says that the board needs something that behaves like a `Shell`, and it might also have a `MessageChannel`. Note what it doesn't say: nothing here mentions serial, SSH or a port number. Exactly the same idea from tests applies to DUTs, because the DUT declares what it needs and the bench provides it. You'll map these in the
[next chapter](channels.md).

`optional=True` means that a bench may leave this one out, in which case `self.ctrl` will be `None`. Should a method require it, it should check that and raise a clear error, rather than letting an `AttributeError` surface.

### Product methods say what, not how

`enter_idle` and `temperature` are the vocabulary that your tasks will use, and they're where parsing and validation belong. Notice how strictly they behave. `temperature` doesn't return `None` or `0.0` for a reply it can't read. It raises `ProtocolError`, and it includes the offending reply. It's the same rule as for drivers: never invent a value.

Should a product method return a quantity? For anything physical that crosses into a test, yes, it's a good habit: `return value * Unit("degC")`. We've kept a plain `float` above just to keep the example focused.

### State

```python title="excerpt"
class WidgetState(BaseModel):
    booted: bool = False
    firmware: str | None = None

@dut("demo.widget-board", state=WidgetState)
```

`state=` asks mastif to create an instance of your model, and to attach it as `self.state`. It's where you keep what you've learned about this unit during this session: has it booted, which firmware is it on, what mode is it in.

Why a dedicated model and not just attributes? Because the station can read this as plain data, and that opens up several things:

- `station.resource("dut").state_snapshot()` returns it as a dictionary today.
- In the engine, it goes into the run's snapshot, so a resumed run knows what state the DUT was in.
- In the station runtime, it's what a control GUI displays, without having to interrogate the hardware.

Put simply, state is **what's worth knowing about this device from the outside**. Instruments can declare a state model as well, and the [station runtime](../../../learn/system-design/events-state.md) relies on it. A driver for a supply, for instance, can declare its setpoints, whether the output's enabled, and its last reading.

The model is only a container, though. Declaring one doesn't add locks, timestamps, or publication to other processes. Your methods are in charge of keeping it accurate.

## Observation, not judgement

Here's a boundary you should hold firmly, as it's the most common place for test logic to leak into an SDK.

```python title="wrong: the DUT type decides what's acceptable"
def check_firmware(self) -> None:
    if self.firmware_version() != "2.1":
        raise ProtocolError("wrong firmware")
```

```python title="right: the DUT type reports, and the task judges — preview"
# In the DUT type
def firmware_version(self) -> str:
    return self.console.execute("version").output

# In the task
def run(self, ctx):
    actual = self.board.firmware_version()
    ctx.check("firmware", actual == self.config.expected_firmware, detail=f"found {actual}")
```

In the first version, a firmware difference is an *exception*, so it comes out as an ERROR, and that says the test broke, when in fact you've found out something real about the product. It also fixes the expected version in the SDK, so a test that's deliberately checking an older unit can't use this method. The DUT should tell you what's true, and the task
should decide whether that's good.

## Testing a DUT type without a board

Since its channels are passed in, you can give a DUT type a scripted console. Here's the class above being tested:

```python title="continuing the example above"
from mastif.resources.driver import build_resource, spec_of
from mastif.resources.std import ShellResult


class FakeConsole:
    def __init__(self, replies):
        self.replies = replies

    def execute(self, command: str, timeout: float | None = None) -> ShellResult:
        return ShellResult(command=command, output=self.replies[command], exit_code=0)


built = build_resource(spec_of(WidgetBoard), {}, name="dut")
board = built.instance
board.console = FakeConsole({"version": "2.1", "cat /etc/serial": "SN-42", "widgetctl idle on": ""})

board.open()
print(board.identify().serial)   # SN-42
print(board.state.firmware)      # 2.1
board.enter_idle()
```

This is enough to test your parsing, your command sequences, and how you handle bad replies. Keep the fake's replies faithful to what the real device produces. Copy them from a real session when you can.

## Recap

- A **DUT type** is the single place that knows how your product behaves, so that tests can speak in terms of intent.
- It declares **channels by capability**, and each bench decides how they connect.
- Its **state model** holds what's worth knowing from the outside, for snapshots and for UIs.
- It **reports what's true**, and tasks **judge** whether that's good.

We've declared channels, but we haven't connected them to anything. Let's do that.

**Next:** [DUT channels and child resources](channels.md)
