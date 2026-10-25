"""Built-in channel drivers, so a DUT can be reached without writing any driver code.

Why this exists:
    A DUT's console and its UDP control port are common enough that every org would
    otherwise write the same adapters. mastif ships them as ordinary drivers, always
    present in the `Registry`:

    - ``mastif.udp``: `MessageChannel` over UDP (`UdpMessageChannel`).
    - ``mastif.line-shell``: `Shell` over a serial, TCP, Telnet or SSH console (`LineShell`).
    - ``mastif.ssh-shell``: `Shell` over SSH command execution, with real exit codes
      (`SshShell`).

Where it fits:
    A station profile maps a DUT's declared channels to these drivers::

        dut:
          driver: demo.widget-board
          channels:
            console: {driver: mastif.line-shell,
                      config: {transport: {kind: serial, port: COM3, baudrate: 115200},
                               prompt: "# "}}
            ctrl:    {driver: mastif.udp,
                      config: {transport: {kind: udp, host: 192.168.1.50, port: 9000}}}
"""

from mastif.resources.channels.shell import LineShell
from mastif.resources.channels.ssh import SshShell
from mastif.resources.channels.udp import UdpMessageChannel

BUILTIN_DRIVERS: tuple[type, ...] = (LineShell, SshShell, UdpMessageChannel)
"""Driver classes every `Registry` includes by default."""

__all__ = ["BUILTIN_DRIVERS", "LineShell", "SshShell", "UdpMessageChannel"]
