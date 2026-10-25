"""``mastif.ssh-shell``: the built-in `Shell` over SSH command execution.

Why this exists:
    Linux DUTs are usually reached over SSH, and tests mostly want "run this command,
    give me its output and exit code". The prompt-based ``mastif.line-shell`` can do it
    over an interactive SSH shell, but then it must strip echo, prompts and terminal
    codes, and ask for the exit code with a second command. SSH has a better tool: an
    *exec* channel per command, which returns output, error output and the real exit
    status, cleanly separated. This driver puts that behind the `Shell` contract, so a
    DUT's ``console: Shell`` channel can be switched between serial, Telnet and SSH in
    the station profile without touching the DUT code.

Where it fits:
    A station profile maps a DUT channel to it::

        channels:
          console: {driver: mastif.ssh-shell,
                    config: {transport: {kind: ssh, host: 192.168.1.60, username: root,
                                         key_file: ~/.ssh/id_ed25519}}}

    The station injects an `SshSession` built from ``transport`` and opens it before
    the channel is attached to the DUT.
"""

from pydantic import Field

from mastif.resources.driver import DriverConfig, driver
from mastif.resources.std import Shell, ShellResult
from mastif.resources.transports.config import SshConfig
from mastif.resources.transports.ssh import SshSession


@driver("mastif.ssh-shell", provides=[Shell])
class SshShell:
    """A `Shell` that runs each command in its own SSH exec channel.

    Output and error output are returned with surrounding whitespace removed, matching
    ``mastif.line-shell``, so DUT code sees the same shape whichever shell the profile
    picks. Each command runs in a fresh shell on the host: ``cd`` or ``export`` in one
    command does not carry over to the next (chain them with ``&&`` instead).

    Example:
        >>> from mastif_testing import FakeSshSession
        >>> session = FakeSshSession({"uname -r": "6.1.0\\n"})
        >>> session.open()
        >>> cfg = SshShell.Config.model_validate(
        ...     {"transport": {"kind": "ssh", "host": "192.168.1.60", "username": "root"}})
        >>> SshShell(cfg, session).execute("uname -r")
        ShellResult(command='uname -r', output='6.1.0', exit_code=0, stderr='')
    """

    class Config(DriverConfig):
        """How to reach the host.

        Attributes:
            transport: The SSH connection (host, user, credentials, host-key policy).
            timeout: Default seconds to wait for a command to finish.

        Example:
            ``{transport: {kind: ssh, host: 192.168.1.60, username: root}, timeout: 30}``
        """

        transport: SshConfig
        timeout: float = Field(default=5.0, gt=0)

    def __init__(self, cfg: Config, session: SshSession) -> None:
        """Keep the config and the session the station injects (and opens).

        Example:
            The station calls ``SshShell(cfg, session=SshSession(cfg.transport))``.
        """
        self.cfg = cfg
        self.session = session

    def execute(self, command: str, timeout: float | None = None) -> ShellResult:
        """Run a command and return its output, error output and exit code.

        A non-zero exit code is reported, not raised: whether it is a failure is the
        test's decision (``result.ok``).

        Args:
            command: The command line, run by the user's login shell on the host.
            timeout: Seconds to wait; defaults to the configured timeout.

        Returns:
            The result, with whitespace stripped from ``output`` and ``stderr``.

        Raises:
            TransportTimeout: If the command doesn't finish in time.
            TransportError: If the connection fails.

        Example:
            >>> from mastif_testing import FakeSshSession
            >>> s = FakeSshSession(); s.open()
            >>> cfg = SshShell.Config.model_validate(
            ...     {"transport": {"kind": "ssh", "host": "h", "username": "u"}})
            >>> r = SshShell(cfg, s).execute("frobnicate")
            >>> r.ok, r.exit_code, r.stderr
            (False, 127, 'sh: frobnicate: command not found')
        """
        wait = self.cfg.timeout if timeout is None else timeout
        raw = self.session.run(command, wait)
        return raw.model_copy(update={"output": raw.output.strip(), "stderr": raw.stderr.strip()})
