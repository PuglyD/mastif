"""``mastif.line-shell``: the built-in `Shell` over a serial, TCP, Telnet or SSH console.

Why this exists:
    Embedded DUTs very often expose a text console: you type a command, it prints
    output, then a prompt. Turning that into a clean ``execute(cmd) -> ShellResult``
    means dealing with the echoed command, the trailing prompt, and optionally asking
    for the exit status. This driver does it once, configured entirely from the
    station profile.

How it works:
    ``execute`` sends the command plus the write terminator, then reads until the
    prompt appears. It removes the echoed command line (if ``echo`` is set) and returns
    the rest as output. If ``exit_code_command`` is set (e.g. ``"echo $?"``), that
    command is run next and its output parsed as the exit code. On ``open`` the
    driver sends an empty line and waits for a prompt, so leftover boot messages are
    discarded before the first command.
"""

import re

from pydantic import Field

from mastif.resources.driver import DriverConfig, driver
from mastif.resources.errors import ProtocolError, TransportTimeout
from mastif.resources.std import Shell, ShellResult
from mastif.resources.transports.config import SerialConfig, SshConfig, TcpConfig, TelnetConfig
from mastif.resources.transports.stream import StreamTransport


@driver("mastif.line-shell", provides=[Shell])
class LineShell:
    """A prompt-based command shell over a byte stream.

    Examples:
        >>> from mastif_testing import FakeStream
        >>> stream = FakeStream()
        >>> stream.open()
        >>> cfg = LineShell.Config.model_validate(
        ...     {"transport": {"kind": "serial", "port": "COM3"}, "prompt": "# "})
        >>> sh = LineShell(cfg, stream)
        >>> stream.feed(b"version\\r\\n2.1\\r\\n# ")
        >>> sh.execute("version")
        ShellResult(command='version', output='2.1', exit_code=None, stderr='')
    """

    class Config(DriverConfig):
        """How to talk to the console.

        Attributes:
            transport: Serial port, TCP (e.g. a terminal server), Telnet, or an SSH
                interactive shell carrying the console. For plain command execution
                over SSH, ``mastif.ssh-shell`` is simpler and reports real exit codes.
            prompt: The text the shell prints when ready for the next command.
            echo: Whether the console echoes typed commands back (most do).
            exit_code_command: Command that prints the last exit status, e.g.
                ``"echo $?"``; ``None`` if the shell has no such concept.
            sync_on_open: Send an empty line on open and wait for a prompt.
            settle_time: After that prompt, keep discarding further prompts until the
                console has been quiet this many seconds. A prompt that was already
                waiting (after a login banner, say) plus the one answering the empty
                line would otherwise be mistaken for the first command's output.
            timeout: Default seconds to wait for a command to finish.

        Examples:
            ``{transport: {kind: serial, port: COM3, baudrate: 115200}, prompt: "# "}``
        """

        transport: SerialConfig | TcpConfig | TelnetConfig | SshConfig = Field(discriminator="kind")
        prompt: str = "$ "
        echo: bool = True
        exit_code_command: str | None = None
        sync_on_open: bool = True
        settle_time: float = Field(default=0.2, ge=0)
        timeout: float = Field(default=5.0, gt=0)

    def __init__(self, cfg: Config, io: StreamTransport) -> None:
        """Keep the config and the stream the station injects (and opens).

        Examples:
            The station calls ``LineShell(cfg, io=SerialTransport(cfg.transport))``.
        """
        self.cfg = cfg
        self.io = io

    def open(self) -> None:
        """Synchronise with the console by waiting for a fresh prompt, then for quiet.

        Raises:
            TransportTimeout: If no prompt appears, e.g. wrong baud rate or DUT not booted.

        Examples:
            >>> from mastif_testing import FakeStream
            >>> s = FakeStream(); s.open()
            >>> cfg = LineShell.Config.model_validate(
            ...     {"transport": {"kind": "serial", "port": "COM3"}, "prompt": "# "})
            >>> s.feed(b"login ok\\r\\n# "); s.feed(b"\\r\\n# ")   # a waiting prompt, then ours
            >>> sh = LineShell(cfg, s); sh.open()
            >>> s.feed(b"version\\r\\n2.1\\r\\n# ")
            >>> sh.execute("version").output
            '2.1'
        """
        if self.cfg.sync_on_open:
            self.io.write(self.cfg.transport.write_termination)
            self.io.read_until(self.cfg.prompt, self.cfg.timeout)
            while self.cfg.settle_time > 0:
                try:
                    self.io.read_until(self.cfg.prompt, self.cfg.settle_time)
                except TransportTimeout:
                    break

    def _run(self, command: str, timeout: float) -> str:
        """Send one command and return its output, without the echo and the prompt.

        Examples:
            ``self._run("uname -r", 5.0)`` returns ``"6.1.0"``.
        """
        t = self.cfg.transport
        self.io.write(command + t.write_termination)
        raw = self.io.read_until(self.cfg.prompt, timeout).decode(t.encoding, errors="replace")
        lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if self.cfg.echo and lines and lines[0].strip() == command.strip():
            lines = lines[1:]
        return "\n".join(lines).strip()

    def execute(self, command: str, timeout: float | None = None) -> ShellResult:
        """Run a command and return its output and, if configured, its exit code.

        Args:
            command: The command line to run.
            timeout: Seconds to wait for the prompt; defaults to the configured timeout.

        Returns:
            The result.

        Raises:
            TransportTimeout: If the prompt does not come back in time.
            ProtocolError: If the exit-code command prints something that isn't a number.

        Examples:
            >>> from mastif_testing import FakeStream
            >>> s = FakeStream(); s.open()
            >>> cfg = LineShell.Config.model_validate({"transport": {"kind": "tcp", "host": "h",
            ...     "port": 23}, "prompt": "$ ", "exit_code_command": "echo $?"})
            >>> s.feed(b"false\\n$ "); s.feed(b"echo $?\\n1\\n$ ")
            >>> LineShell(cfg, s).execute("false").exit_code
            1
        """
        wait = self.cfg.timeout if timeout is None else timeout
        output = self._run(command, wait)
        exit_code = None
        if self.cfg.exit_code_command:
            status = self._run(self.cfg.exit_code_command, wait)
            if not re.fullmatch(r"-?\d+", status):
                raise ProtocolError(f"{self.cfg.exit_code_command!r} printed {status!r}")
            exit_code = int(status)
        return ShellResult(command=command, output=output, exit_code=exit_code)
