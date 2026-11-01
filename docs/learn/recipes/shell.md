# Talk to a DUT over SSH or a console

**You have:** a DUT that you reach by typing commands, over a serial console, Telnet or SSH.

**You want:** your DUT type to run commands, without caring which connection a given bench uses.

!!! success "Works today"
    Everything on this page runs against the current code. Addresses are documentation placeholders.

Declare what you need, by capability, on the DUT type:

```python title="excerpt"
@dut("demo.widget-board")
class WidgetBoard:
    console: Shell = channel()

    def firmware_version(self) -> str:
        return self.console.execute("cat /etc/version").output
```

Then each bench chooses one of two built-in drivers.

## Choosing between them

| | `mastif.ssh-shell` | `mastif.line-shell` |
|---|---|---|
| **Works over** | SSH only | Serial, TCP, Telnet, an SSH shell |
| **How it works** | A fresh channel per command | One interactive session, reading to a prompt |
| **Exit codes** | Real | Only if you configure a way to ask |
| **stderr** | Kept separate | Mixed in with the output |
| **`cd` carries over?** | No: each command is a new shell | Yes: it's a single session |
| **Choose it when** | The device runs a real SSH server | You've only got a console |

If the device has a real SSH server, prefer `mastif.ssh-shell`, as it's far more reliable. The prompt-based one is what you use when a console is all there is.

## SSH

```yaml title="under resources.dut.channels"
console:
  driver: mastif.ssh-shell
  config:
    transport:
      kind: ssh
      host: 192.0.2.20
      username: demo
      key_file: ~/.ssh/id_ed25519
      known_hosts: strict
```

This needs `mastif[ssh]`. Host keys are always checked. `strict`, the default, refuses unknown hosts, while `accept_new` trusts a new host and remembers it. A *changed* key is always refused, as that's what a man-in-the-middle attack looks like, and it's also what a reinstalled device looks like, so you'll need to look into which it is.

Remember that each command runs in a fresh shell:

```python title="excerpt"
self.console.execute("cd /opt/widget")
self.console.execute("./status")               # Runs in the home directory
self.console.execute("cd /opt/widget && ./status")   # This is what you meant
```

## A serial console

```yaml title="under resources.dut.channels"
console:
  driver: mastif.line-shell
  config:
    transport: {kind: serial, port: COM3, baudrate: 115200}
    prompt: "# "
    exit_code_command: "echo $?"
```

Here's what it does on each `execute`: it sends the command, reads up to the `prompt`, removes the echoed command, and returns what's left.

**Get the prompt exactly right**, including any trailing space. If it's wrong, every command times out.

**`exit_code_command` matters.** Without it, `exit_code` is `None`, and getting a prompt back tells you only that a command finished, not that it succeeded. If your device has a POSIX-style shell, then `echo $?` gives you real exit codes.

The same driver works over a terminal server, or Telnet:

```yaml title="alternatives"
transport: {kind: tcp, host: 192.0.2.30, port: 4001}
transport: {kind: telnet, host: 192.0.2.31, login_prompt: "login: ", username: admin, password: "...", ready_prompt: "> "}
```

Telnet option negotiation gets handled for you, and passwords are `SecretStr`, so they don't appear in logs.

## Validate replies in your DUT type

A shell returns text. Turning it into something reliable is your DUT type's job:

```python
from mastif.resources.errors import ProtocolError
from mastif.resources.std import ShellResult


def parse_version(result: ShellResult) -> str:
    if result.exit_code not in (0, None):
        raise ProtocolError(f"{result.command!r} exited {result.exit_code}: {result.output!r}")
    version = result.output.strip()
    if not version:
        raise ProtocolError(f"{result.command!r} returned nothing")
    return version


print(parse_version(ShellResult(command="version", output="2.1\n", exit_code=0)))  # 2.1
```

## Test it without a board

`FakeStream` lets you test prompt handling, including messages that arrive in pieces:

```python
from mastif.resources.channels.shell import LineShell
from mastif_testing import FakeStream

stream = FakeStream()
stream.open()
config = LineShell.Config.model_validate({"transport": {"kind": "serial", "port": "COM3"}, "prompt": "# "})
shell = LineShell(config, stream)

stream.feed(b"version\r\n2.1\r\n# ")
print(shell.execute("version").output)  # 2.1
```

`FakeSshSession` does the same for the SSH case, with scripted commands and exit codes.

## See also

- [DUT channels and child resources](../../getting-started/tutorial/hardware-integration/channels.md).
- [ADR-0020](../../adr/0020-builtin-line-shell.md) and [ADR-0034](../../adr/0034-builtin-ssh-shell.md).

**Next:** [Implement a UDP request/reply protocol](udp.md)
