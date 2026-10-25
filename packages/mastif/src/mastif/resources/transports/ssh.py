"""SSH transports: run commands on a remote host, or talk to its interactive shell.

Why this exists:
    Linux-based DUTs (and some instruments and controllers) are reached over SSH. Two
    styles of use are common, and they need different tools:

    - **Command execution.** Run ``uname -r`` and get its output, its error output and
      its real exit code, cleanly separated. SSH's *exec* channel does exactly that,
      with no prompt, echo or terminal codes to strip. `SshSession` provides it.
    - **An interactive shell.** Some targets only offer a menu or a vendor CLI, or a
      driver wants to talk SCPI-like lines over SSH. `SshStreamTransport` opens a shell
      channel and presents it as a `StreamTransport`, so `LineIO`, `Scpi` and the
      ``mastif.line-shell`` channel work over SSH unchanged.

    SSH is implemented with paramiko, an optional extra (``pip install 'mastif[ssh]'``).
    The system ``ssh`` client is not used: containers and minimal images often lack it,
    and its prompts and exit codes are hard to drive reliably. paramiko is imported only
    when a connection opens, so mastif imports fine without it.

Security:
    Host keys are always checked. ``known_hosts: strict`` (the default) refuses unknown
    hosts; ``accept_new`` trusts a host the first time and remembers it. A changed host
    key is refused in both modes, because it is what a man-in-the-middle attack looks
    like. Passwords are `pydantic.SecretStr` and never logged.

Where it fits:
    The station builds these from a ``transport: {kind: ssh, ...}`` block (see
    `mastif.resources.transports.factory`). The built-in ``mastif.ssh-shell`` channel
    (`mastif.resources.channels.ssh.SshShell`) wraps `SshSession` as a `Shell`. Tests
    inject a fake client through ``client_factory``; SDK authors use
    ``mastif_testing.FakeSshSession`` instead.
"""

import logging
import os
import time
from collections.abc import Callable
from typing import Any

from mastif.resources.errors import TransportError, TransportTimeout
from mastif.resources.std import ShellResult
from mastif.resources.transports.config import SshConfig
from mastif.resources.transports.stream import BufferedStream

type ClientFactory = Callable[[], Any]
"""Creates an unconnected paramiko ``SSHClient`` (or a fake with the same methods)."""

_POLL = 0.005  # seconds between checks while a command runs and nothing is ready


def _paramiko_client() -> Any:
    """Create a ``paramiko.SSHClient``, importing paramiko on first use.

    Returns:
        A new, unconnected client.

    Raises:
        TransportError: If paramiko isn't installed, with the install command.

    Example:
        ``client = _paramiko_client()`` (needs the ``ssh`` extra).
    """
    try:
        import paramiko  # optional dependency, imported on use
    except ImportError as exc:
        raise TransportError("ssh transport needs: pip install 'mastif[ssh]'") from exc
    return paramiko.SSHClient()


class _RejectUnknownHost:
    """Host-key policy for ``known_hosts: strict``: unknown hosts are refused.

    paramiko calls ``missing_host_key`` when the server's key isn't in any loaded
    known-hosts file. This class is duck-typed to paramiko's ``MissingHostKeyPolicy``,
    so no paramiko import is needed to define it.

    Example:
        ``client.set_missing_host_key_policy(_RejectUnknownHost(config))``
    """

    def __init__(self, config: SshConfig) -> None:
        """Remember the config, for the error message.

        Example:
            ``_RejectUnknownHost(SshConfig(host="h", username="u"))``
        """
        self.config = config

    def missing_host_key(self, client: Any, hostname: str, key: Any) -> None:
        """Refuse the connection, explaining how to trust the host.

        Raises:
            TransportError: Always.

        Example:
            Called by paramiko during ``connect`` for an unknown host.
        """
        raise TransportError(
            f"ssh://{self.config.host}: host key is not in known_hosts. Add it "
            f"(ssh-keyscan -p {self.config.port} {self.config.host} >> ~/.ssh/known_hosts) "
            "or set known_hosts: accept_new in the station profile"
        )


class _AcceptNewHost:
    """Host-key policy for ``known_hosts: accept_new``: trust a host the first time.

    The key is added to the client's known hosts and, if the config names a
    ``known_hosts_file``, saved there, so the next connection checks it strictly.

    Example:
        ``client.set_missing_host_key_policy(_AcceptNewHost(config, log))``
    """

    def __init__(self, config: SshConfig, log: logging.Logger) -> None:
        """Remember the config and where to log the new key.

        Example:
            ``_AcceptNewHost(config, logging.getLogger("mastif.io"))``
        """
        self.config = config
        self.log = log

    def missing_host_key(self, client: Any, hostname: str, key: Any) -> None:
        """Accept and remember the new host key.

        Example:
            Called by paramiko during ``connect`` for an unknown host.
        """
        client.get_host_keys().add(hostname, key.get_name(), key)
        self.log.warning(
            "ssh://%s: trusting new host key %s (known_hosts: accept_new)",
            hostname,
            key.get_name(),
        )
        if self.config.known_hosts_file:
            client.save_host_keys(os.path.expanduser(self.config.known_hosts_file))


class SshSession:
    """An SSH connection for running commands, with output, error output and exit code.

    Each `run` opens a fresh *exec* channel on the one connection, so commands don't
    share shell state (``cd`` in one command doesn't affect the next), exactly like
    ``ssh host cmd``.

    Example:
        Reading a Linux DUT's kernel version (needs a reachable host)::

            ssh = SshSession(SshConfig(host="192.168.1.60", username="root"))
            ssh.open()
            print(ssh.run("uname -r").output)   # "6.1.0\\n"
            ssh.close()
    """

    def __init__(
        self,
        config: SshConfig,
        logger: logging.Logger | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        """Prepare the session; nothing happens on the network until `open`.

        Args:
            config: Host, credentials, host-key policy and timeouts.
            logger: Where to trace commands.
            client_factory: Creates the SSH client. Defaults to paramiko's
                ``SSHClient``; tests pass a fake.

        Example:
            >>> SshSession(SshConfig(host="192.168.1.60", username="root")).name
            'ssh://root@192.168.1.60:22'
        """
        self.config = config
        self.name = f"ssh://{config.username}@{config.host}:{config.port}"
        self.log = logger or logging.getLogger("mastif.io")
        self._factory = client_factory or _paramiko_client
        self._client: Any = None

    @property
    def is_open(self) -> bool:
        """Whether the session is connected.

        Example:
            >>> SshSession(SshConfig(host="h", username="u")).is_open
            False
        """
        return self._client is not None

    def open(self) -> None:
        """Connect and authenticate; does nothing if already open.

        Raises:
            TransportError: If paramiko is missing, the host is unreachable, its key is
                unknown (strict) or has changed, or authentication fails.

        Example:
            Called by the station before the driver's ``open()``.
        """
        if self._client is not None:
            return
        cfg = self.config
        client = self._factory()
        client.load_system_host_keys()
        if cfg.known_hosts_file and os.path.exists(os.path.expanduser(cfg.known_hosts_file)):
            client.load_host_keys(os.path.expanduser(cfg.known_hosts_file))
        if cfg.known_hosts == "strict":
            client.set_missing_host_key_policy(_RejectUnknownHost(cfg))
        else:
            client.set_missing_host_key_policy(_AcceptNewHost(cfg, self.log))
        explicit = cfg.password is not None or cfg.key_file is not None
        try:
            client.connect(
                cfg.host,
                port=cfg.port,
                username=cfg.username,
                password=cfg.password.get_secret_value() if cfg.password else None,
                key_filename=os.path.expanduser(cfg.key_file) if cfg.key_file else None,
                passphrase=cfg.key_passphrase.get_secret_value() if cfg.key_passphrase else None,
                timeout=cfg.connect_timeout,
                banner_timeout=cfg.connect_timeout,
                auth_timeout=cfg.connect_timeout,
                allow_agent=not explicit,
                look_for_keys=not explicit,
            )
        except TransportError:
            client.close()
            raise
        except Exception as exc:
            client.close()
            raise TransportError(f"{self.name}: {_describe_connect_error(exc)}") from exc
        self._client = client
        self.log.debug("%s: opened", self.name)

    def close(self) -> None:
        """Disconnect; safe to call repeatedly.

        Example:
            Called by the station after the driver's ``close()``.
        """
        if self._client is not None:
            client, self._client = self._client, None
            client.close()
            self.log.debug("%s: closed", self.name)

    def _require_client(self) -> Any:
        """Return the connected client, or raise if the session is closed.

        Raises:
            TransportError: If not open.

        Example:
            Guards `run` and `invoke_shell`.
        """
        if self._client is None:
            raise TransportError(f"{self.name}: not open")
        return self._client

    def run(self, command: str, timeout: float | None = None) -> ShellResult:
        """Run one command and wait for it to finish.

        Output and error output are collected separately and decoded with the config's
        encoding (undecodable bytes are replaced, never fatal). They are returned
        exactly as printed, including trailing newlines.

        Args:
            command: The command line, run by the user's login shell on the host.
            timeout: Seconds to wait for the command to finish; defaults to the
                config's ``timeout``.

        Returns:
            ``ShellResult(command, output, exit_code, stderr)``. ``exit_code`` is the
            command's real exit status; it is ``None`` only if the server never
            reported one (e.g. the command was killed by a signal).

        Raises:
            TransportTimeout: If the command doesn't finish in time. The channel is
                closed, which usually terminates the remote command.
            TransportError: If the session is closed or the connection fails.

        Example:
            ``ssh.run("cat /etc/hostname")`` returns a result with ``output='dut-07\\n'``,
            ``exit_code=0`` and ``stderr=''``.
        """
        client = self._require_client()
        wait = self.config.timeout if timeout is None else timeout
        deadline = time.monotonic() + wait
        self.log.debug("%s $ %s", self.name, command)
        try:
            transport = client.get_transport()
            if transport is None or not transport.is_active():
                raise TransportError(f"{self.name}: connection lost")
            chan = transport.open_session(timeout=wait)
            try:
                chan.exec_command(command)
                out, err = bytearray(), bytearray()
                while True:
                    progressed = False
                    while chan.recv_ready():
                        out += chan.recv(65536)
                        progressed = True
                    while chan.recv_stderr_ready():
                        err += chan.recv_stderr(65536)
                        progressed = True
                    if chan.exit_status_ready() and not chan.recv_ready():
                        if not chan.recv_stderr_ready():
                            break
                        continue
                    if not progressed:
                        if time.monotonic() >= deadline:
                            raise TransportTimeout(
                                f"{self.name}: {command!r} did not finish within {wait} s"
                            )
                        time.sleep(_POLL)
                status = chan.recv_exit_status()
            finally:
                chan.close()
        except TransportError:
            raise
        except Exception as exc:
            raise TransportError(f"{self.name}: {command!r} failed: {exc}") from exc
        enc = self.config.encoding
        result = ShellResult(
            command=command,
            output=out.decode(enc, errors="replace"),
            exit_code=status if status >= 0 else None,
            stderr=err.decode(enc, errors="replace"),
        )
        self.log.debug("%s exit %s, output %r", self.name, result.exit_code, result.output)
        return result

    def invoke_shell(self) -> Any:
        """Open an interactive shell channel on a pseudo-terminal.

        The terminal type is ``dumb`` (to discourage colour codes) and the width is
        large, so long command lines don't wrap in the echo.

        Returns:
            The paramiko channel.

        Raises:
            TransportError: If the session is closed or the server refuses a shell.

        Example:
            Used by `SshStreamTransport`; drivers rarely call it directly.
        """
        client = self._require_client()
        try:
            return client.invoke_shell(term="dumb", width=512, height=24)
        except Exception as exc:
            raise TransportError(f"{self.name}: cannot open a shell: {exc}") from exc


def _describe_connect_error(exc: Exception) -> str:
    """Turn a paramiko connection error into an actionable message.

    paramiko's exception classes are matched by name, so this works without importing
    paramiko (it may not be installed, and tests use fakes).

    Example:
        >>> class BadHostKeyException(Exception): ...
        >>> _describe_connect_error(BadHostKeyException("x"))[:24]
        'host key has CHANGED (x)'
    """
    kind = type(exc).__name__
    if kind == "BadHostKeyException":
        return (
            f"host key has CHANGED ({exc}); this may be a man-in-the-middle attack, or "
            "the host was reinstalled. Verify, then remove the old key from known_hosts"
        )
    if kind == "AuthenticationException":
        return f"authentication failed ({exc}); check username, password or key_file"
    if isinstance(exc, TimeoutError):
        return f"connection timed out ({exc})"
    return f"cannot connect: {exc}"


class SshStreamTransport(BufferedStream):
    """An interactive SSH shell as a `StreamTransport`.

    It owns its own `SshSession`. Bytes written go to the remote shell's terminal, and
    whatever the shell prints (echo, prompts, output) is read back, just like a serial
    console. Ask for ``io: LineIO`` or use ``mastif.line-shell`` on top of it.

    Example:
        A vendor CLI that is only reachable as an SSH shell (needs a host)::

            sh = SshStreamTransport(SshConfig(host="10.0.0.20", username="admin",
                                              password="..."))
            sh.open()
            sh.write("show version\\n")
            print(sh.read_until("> "))
    """

    def __init__(
        self,
        config: SshConfig,
        logger: logging.Logger | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        """Prepare the shell; nothing happens on the network until `open`.

        Args:
            config: Connection settings; its `LineSettings` apply to the stream.
            logger: Where to trace I/O.
            client_factory: Creates the SSH client; tests pass a fake.

        Example:
            >>> SshStreamTransport(SshConfig(host="10.0.0.20", username="admin")).name
            'ssh://admin@10.0.0.20:22'
        """
        self.session = SshSession(config, logger, client_factory)
        super().__init__(self.session.name, config.timeout, logger, config.encoding)
        self.config = config
        self._chan: Any = None

    def _connect(self) -> None:
        """Connect the session and open the shell channel.

        Raises:
            TransportError: If either step fails.

        Example:
            Called by `open`.
        """
        self.session.open()
        try:
            self._chan = self.session.invoke_shell()
        except BaseException:
            self.session.close()
            raise

    def _disconnect(self) -> None:
        """Close the channel and the session.

        Example:
            Called by `close`.
        """
        try:
            if self._chan is not None:
                self._chan.close()
        finally:
            self._chan = None
            self.session.close()

    def _send(self, data: bytes) -> None:
        """Send all bytes to the shell.

        Raises:
            TransportError: If the channel fails.

        Example:
            ``self._send(b"uptime\\n")``
        """
        assert self._chan is not None
        try:
            self._chan.sendall(data)
        except Exception as exc:
            raise TransportError(f"{self.name}: send failed: {exc}") from exc

    def _receive(self, timeout: float) -> bytes:
        """Receive one chunk, or ``b""`` on timeout.

        Raises:
            TransportError: If the shell exited or the connection failed.

        Example:
            Returns console output as it arrives, e.g. ``b"up 3 days\\r\\n$ "``.
        """
        assert self._chan is not None
        self._chan.settimeout(timeout)
        try:
            chunk = self._chan.recv(4096)
        except TimeoutError:
            return b""
        except Exception as exc:
            raise TransportError(f"{self.name}: receive failed: {exc}") from exc
        if not chunk:
            raise TransportError(f"{self.name}: shell closed by peer")
        return chunk
