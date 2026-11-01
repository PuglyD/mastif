# DUT channels and child resources

Some resources contain smaller things that tests want to reach directly: a DUT's console, or one axis of a positioner. They look alike from the outside, and you'd address both of them with a dotted name. But there are two different mechanisms behind them, and they differ in an important way: **when you can know they exist.**

!!! success "Works today"
    Everything on this page runs against the current code. The profile fragments are illustrative and use documentation addresses.

## Channels: declared ahead of time

We declared these on the DUT in the [last chapter](duts.md). A **channel** is a way into a DUT, with its capability fixed in the DUT's code, while each bench decides how it's physically connected.

```python title="on the DUT type"
console: Shell = channel()
ctrl: MessageChannel = channel(optional=True)
```

```yaml title="on the bench, in the profile"
resources:
  dut:
    driver: demo.widget-board
    channels:
      console:
        driver: mastif.line-shell
        config:
          transport: {kind: serial, port: COM3, baudrate: 115200}
          prompt: "# "
          exit_code_command: "echo $?"
      ctrl:
        driver: mastif.udp
        config:
          transport: {kind: udp, host: 192.0.2.50, port: 9000}
roles:
  console: dut.console
```

Each channel is itself a resource, with its own driver and its own connection. So here, the board has two connections, and each one could be replaced separately.

Now here's the payoff. A different bench reaches the same board over SSH instead of a serial cable. Its profile has one different entry, and neither the DUT type nor any test changes:

```yaml title="another bench"
      console:
        driver: mastif.ssh-shell
        config:
          transport: {kind: ssh, host: 192.0.2.60, username: root, key_file: ~/.ssh/id_ed25519}
```

## The built-in channels

mastif includes three channel drivers that are always available, since a DUT's console and control port are common enough that it would be a shame if everyone had to write them again.

| Driver | Provides | Over | Good for |
|---|---|---|---|
| `mastif.line-shell` | `Shell` | Serial, TCP, Telnet, SSH shell | Prompt-based consoles |
| `mastif.ssh-shell` | `Shell` | SSH exec | Hosts with real exit codes |
| `mastif.udp` | `MessageChannel` | UDP | Datagram control ports |

There's more on the differences between those two shells in the [SSH and consoles recipe](../../../learn/recipes/shell.md). If none of them fits, say you've got a framed binary protocol over TCP, write a channel driver in the same way as any other driver:

```python title="excerpt"
@driver("demo.framed-tcp", provides=[MessageChannel])
class FramedTcp:
    class Config(DriverConfig):
        transport: TcpConfig

    def __init__(self, cfg: Config, io: StreamTransport) -> None:
        self.io = io

    ...
```

Then map it in a profile: `ctrl: {driver: demo.framed-tcp, config: {...}}`. The DUT type asked for a `MessageChannel`, so it doesn't care.

## What gets checked, and when

Because channels are declared on the class and configured in a profile, the station can check all of this at build time, with no hardware:

- Is each required channel mapped?
- Is any channel mapped that the DUT doesn't declare? (A typo in a channel name is caught here.)
- Does each channel's driver provide the contract that the DUT asked for?

At open time, the order is **channels first, and then the DUT's own `open()`**. So by the time your `open()` runs, `self.console` is ready to use, and you can talk to the board immediately. On the way out, it's the reverse.

## Child resources: discovered at run time

Now for the other mechanism. Picture a motion controller with two axes. You might want tests to ask for `positioner.azimuth`, as if that were its own device. But unlike a console, it isn't declared in advance, because how many axes a controller has may depend on what you find when you connect to it.

For this, a driver implements `children()`, which the station calls during opening:

```python title="excerpt"
@driver("acme.positioner-2", provides=[])
class Positioner:
    def __init__(self, cfg: Config, io: Scpi) -> None:
        self.io = io

    def children(self) -> dict[str, object]:
        count = int(self.io.query("AXIS:COUNT?"))
        names = ["azimuth", "elevation", "roll"][:count]
        return {name: Axis(self.io, index) for index, name in enumerate(names, start=1)}


class Axis:
    def __init__(self, io: Scpi, index: int) -> None:
        self.io = io
        self.index = index

    def move_to(self, position) -> None:
        self.io.write(f"AXIS{self.index}:MOVE {position.magnitude('deg')}")
```

```yaml title="in the profile"
roles:
  az: positioner.azimuth
```

## How they differ

Here's the comparison, and you should pay particular attention to the second and fourth rows.

| | Channel | Child resource |
|---|---|---|
| **Declared** | On the DUT's class | Reported by `children()` |
| **Known** | At build time | Only after opening |
| **Connection** | Each has its own | Usually shares its parent's |
| **Independent?** | Yes, generally | Often not |
| **Configured** | In the profile | By the parent driver |

**Known only after opening.** This has a real effect on preflight. A role like `positioner.azimuth` can't be fully checked until the controller's been connected. So `role_problems` will say that a child can't be verified yet, rather than failing a bench that's actually fine.

**Not independent.** Those two `Axis` objects look like separate things, but they share one connection, and quite possibly one motion controller with one command queue. Issuing commands to both from two threads could interleave them badly. Having two different role names doesn't make them two independent instruments, and anything that schedules
work, or grants [leases](../../../learn/system-design/resource-lifetimes.md), must account for the physical reality rather than the names.

## Who owns what

Here's the rule, and it's the same at every level: **whoever created something closes it.**

- The station creates resources and channels, and it opens and closes them.
- A driver creates its children, so they don't get their own lifecycle. They live and die with their parent.
- A test creates nothing, and closes nothing.

So a test should never close a channel that it's finished with, and a child shouldn't close the shared connection it was given. If a test could do that, then the next test would inherit a dead console, and you'd spend a day working out why.

## Recap

- **Channels** are declared on the DUT, mapped per bench in the profile, and checked at build time. Changing how a bench reaches a DUT needs no code changes.
- **Child resources** are reported at run time by `children()`, so preflight can't fully check them, and they usually share a parent's connection.
- **Role names don't imply independence.** What matters is what's physically shared.
- **Whoever creates something closes it**, and tests don't close anything.

Our drivers and DUTs are now all connected. How do we know they work, without a bench?

**Next:** [Testing drivers with fake I/O](fake-io.md)
