"""Tests for `mastif.resources.transports.ssh` and the ``mastif.ssh-shell`` channel.

Two kinds of test, because SSH has two kinds of risk:

- **Logic, against a fake paramiko client** (no network): host-key policies,
  credential handling, error translation, output/stderr/exit-code collection,
  timeouts, and which I/O types the factory builds from an SSH config. The fake has
  paramiko's method names, so `SshSession` runs its real code against it.
- **Protocol, against a real SSH server** run in-process with paramiko's server mode on
  localhost: a real handshake, host-key checking against a real known-hosts file,
  password authentication, exec channels with separate stderr and real exit codes, and
  an interactive shell driven by ``mastif.line-shell``. These are skipped if paramiko
  (the ``ssh`` extra) is not installed.
"""

import socket
import sys
import threading
import time
from pathlib import Path
from typing import cast

import pytest

from mastif.resources import DriverDefinitionError, TransportError, TransportTimeout
from mastif.resources.channels import LineShell, SshShell
from mastif.resources.registry import Registry
from mastif.resources.std import ShellResult
from mastif.resources.transports import (
    DatagramChannel,
    LineIO,
    Scpi,
    SshConfig,
    SshSession,
    SshStreamTransport,
    StreamLineIO,
    StreamTransport,
    TcpConfig,
    build_io,
)
from mastif_testing import FakeSshSession

# --------------------------------------------------------------------------- fakes


class FakeKey:
    """A host key with paramiko's ``get_name``."""

    def get_name(self) -> str:
        """Return the key type."""
        return "ssh-ed25519"


class FakeHostKeys(dict):
    """paramiko's ``HostKeys``, reduced to ``add``."""

    def add(self, hostname: str, keytype: str, key: object) -> None:
        """Remember a key."""
        self[hostname] = (keytype, key)


class FakeExecChannel:
    """An exec channel replaying canned output, error output and exit status."""

    def __init__(self, script: dict[str, tuple[bytes, bytes, int] | None]) -> None:
        """Create the channel with a command script; ``None`` means "never finishes"."""
        self.script = script
        self.out = b""
        self.err = b""
        self.status: int | None = None
        self.closed = False

    def exec_command(self, command: str) -> None:
        """Start the scripted command."""
        reply = self.script.get(command, (b"", b"not found\n", 127))
        if reply is not None:
            self.out, self.err, self.status = reply

    def recv_ready(self) -> bool:
        """Whether output is waiting."""
        return bool(self.out)

    def recv(self, n: int) -> bytes:
        """Hand out output in small chunks, like a network would."""
        chunk, self.out = self.out[:3], self.out[3:]
        return chunk

    def recv_stderr_ready(self) -> bool:
        """Whether error output is waiting."""
        return bool(self.err)

    def recv_stderr(self, n: int) -> bytes:
        """Hand out error output."""
        chunk, self.err = self.err, b""
        return chunk

    def exit_status_ready(self) -> bool:
        """Whether the command has finished."""
        return self.status is not None

    def recv_exit_status(self) -> int:
        """Return the exit status."""
        assert self.status is not None
        return self.status

    def close(self) -> None:
        """Record the close."""
        self.closed = True


class FakeShellChannel:
    """An interactive shell channel: bytes fed in are read back out."""

    def __init__(self) -> None:
        """Start empty."""
        self.incoming: list[bytes] = []
        self.sent = b""
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        """Accept a timeout (the fake never blocks)."""

    def sendall(self, data: bytes) -> None:
        """Record sent bytes."""
        self.sent += data

    def recv(self, n: int) -> bytes:
        """Return the next fed chunk; raise a timeout if none, ``b""`` once closed."""
        if self.incoming:
            return self.incoming.pop(0)
        if self.closed:
            return b""
        raise TimeoutError

    def close(self) -> None:
        """Record the close."""
        self.closed = True


class FakeTransport:
    """paramiko's ``Transport``, reduced to what `SshSession.run` uses."""

    def __init__(self, client: "FakeSshClient") -> None:
        """Belong to a client."""
        self.client = client
        self.active = True

    def is_active(self) -> bool:
        """Whether the connection is alive."""
        return self.active

    def open_session(self, timeout: float | None = None) -> FakeExecChannel:
        """Open an exec channel."""
        chan = FakeExecChannel(self.client.script)
        self.client.channels.append(chan)
        return chan


class FakeSshClient:
    """A stand-in for ``paramiko.SSHClient`` with real host-key policy behaviour.

    Attributes:
        known: Host names whose key is "in known_hosts".
        connect_error: Raised from ``connect`` if set (after the host-key check).
        connect_kwargs: The keyword arguments ``connect`` received.
    """

    def __init__(self, script=None, known=(), connect_error: Exception | None = None):
        """Configure the fake server behind the client."""
        self.script = dict(script or {})
        self.known = set(known)
        self.connect_error = connect_error
        self.host_keys = FakeHostKeys()
        self.loaded: list[str] = []
        self.saved: list[str] = []
        self.policy = None
        self.connect_kwargs: dict = {}
        self.channels: list[FakeExecChannel] = []
        self.shell = FakeShellChannel()
        self.transport = FakeTransport(self)
        self.closed = False

    def load_system_host_keys(self) -> None:
        """Pretend to load ``~/.ssh/known_hosts``."""

    def load_host_keys(self, path: str) -> None:
        """Record which known-hosts file was loaded."""
        self.loaded.append(path)

    def set_missing_host_key_policy(self, policy) -> None:
        """Keep the policy mastif installs."""
        self.policy = policy

    def get_host_keys(self) -> FakeHostKeys:
        """Return the client's host keys."""
        return self.host_keys

    def save_host_keys(self, path: str) -> None:
        """Record a save."""
        self.saved.append(path)

    def connect(self, host: str, **kwargs) -> None:
        """Check the host key like paramiko does, then succeed or raise."""
        self.connect_kwargs = kwargs
        if host not in self.known:
            assert self.policy is not None
            self.policy.missing_host_key(self, host, FakeKey())
        if self.connect_error is not None:
            raise self.connect_error

    def get_transport(self) -> FakeTransport:
        """Return the connection."""
        return self.transport

    def invoke_shell(self, **kwargs) -> FakeShellChannel:
        """Return the interactive shell channel."""
        return self.shell

    def close(self) -> None:
        """Record the close."""
        self.closed = True


class BadHostKeyException(Exception):
    """Same name as paramiko's, which is how mastif recognises it."""


class AuthenticationException(Exception):
    """Same name as paramiko's."""


def session_with(client: FakeSshClient, **cfg) -> SshSession:
    """Build an `SshSession` that uses ``client``."""
    config = SshConfig.model_validate({"host": "dut", "username": "root", **cfg})
    return SshSession(config, client_factory=lambda: client)


# --------------------------------------------------------------- logic, with fakes


def test_run_separates_output_stderr_and_exit_code():
    """`run` returns output and error output separately, with the real exit code.

    Tests judge commands by exit status and want clean output; mixing stderr into
    output, or guessing the status, is what makes console-based checks fragile.
    """
    client = FakeSshClient({"ls /nope": (b"partial\n", b"ls: /nope: missing\n", 2)}, known={"dut"})
    ssh = session_with(client)
    ssh.open()

    result = ssh.run("ls /nope")

    assert result == ShellResult(
        command="ls /nope", output="partial\n", exit_code=2, stderr="ls: /nope: missing\n"
    )
    assert client.channels[0].closed


def test_command_that_never_finishes_times_out_and_closes_its_channel():
    """A hung command raises `TransportTimeout` and its channel is closed.

    A test must never stall forever on a DUT command; closing the channel usually ends
    the remote process too.
    """
    client = FakeSshClient({"sleep 100": None}, known={"dut"})
    ssh = session_with(client)
    ssh.open()

    with pytest.raises(TransportTimeout, match="did not finish within 0.05 s"):
        ssh.run("sleep 100", timeout=0.05)
    assert client.channels[0].closed


def test_strict_host_keys_refuse_unknown_hosts_with_a_fix_hint():
    """With ``known_hosts: strict``, an unknown host is refused, explaining what to do.

    Connecting to an unverified host would let anyone on the network impersonate the
    DUT. The message tells the engineer how to trust the host deliberately.
    """
    client = FakeSshClient(known=())
    ssh = session_with(client)

    with pytest.raises(TransportError, match="not in known_hosts.*ssh-keyscan.*accept_new"):
        ssh.open()
    assert not ssh.is_open
    assert client.closed


def test_accept_new_trusts_and_saves_an_unknown_host(tmp_path):
    """With ``accept_new``, a new host is trusted and its key saved for next time.

    This matches OpenSSH's ``accept-new``: convenient for freshly flashed DUTs, while
    later connections are still checked against the saved key.
    """
    known_file = tmp_path / "known_hosts"
    client = FakeSshClient(known=())
    ssh = session_with(client, known_hosts="accept_new", known_hosts_file=str(known_file))

    ssh.open()

    assert "dut" in client.host_keys
    assert client.saved == [str(known_file)]


def test_changed_host_key_is_refused_with_a_warning():
    """A changed host key fails with a message that names the possible attack.

    This is what a man-in-the-middle looks like (or a reinstalled host); either way, a
    human has to decide, so mastif never connects silently.
    """
    client = FakeSshClient(known={"dut"}, connect_error=BadHostKeyException("dut: key mismatch"))

    with pytest.raises(TransportError, match="host key has CHANGED.*man-in-the-middle"):
        session_with(client, known_hosts="accept_new").open()


def test_failed_authentication_names_the_credentials_to_check():
    """Wrong credentials give a `TransportError` pointing at the profile's credentials."""
    client = FakeSshClient(known={"dut"}, connect_error=AuthenticationException("denied"))

    with pytest.raises(TransportError, match="authentication failed.*key_file"):
        session_with(client).open()


@pytest.mark.parametrize(
    ("cfg", "agent_and_default_keys"),
    [({}, True), ({"password": "pw"}, False), ({"key_file": "~/.ssh/id_test"}, False)],
)
def test_agent_and_default_keys_only_without_explicit_credentials(cfg, agent_and_default_keys):
    """The SSH agent and ``~/.ssh/id_*`` are tried only when no credential is configured.

    An explicit password or key in the profile must be what is used, not whatever key
    happens to be loaded in the engineer's agent.

    Args:
        cfg: Credential fields of the config.
        agent_and_default_keys: Whether agent and default keys should be allowed.
    """
    client = FakeSshClient(known={"dut"})
    session_with(client, **cfg).open()

    assert client.connect_kwargs["allow_agent"] is agent_and_default_keys
    assert client.connect_kwargs["look_for_keys"] is agent_and_default_keys


def test_password_never_appears_in_reprs_or_logs(caplog):
    """Passwords are secrets: they don't show in config reprs or I/O traces.

    Configs and logs end up in run records and bug reports.
    """
    caplog.set_level("DEBUG", logger="mastif.io")
    cfg = SshConfig.model_validate({"host": "dut", "username": "root", "password": "hunter2"})
    client = FakeSshClient({"id": (b"uid=0\n", b"", 0)}, known={"dut"})
    ssh = SshSession(cfg, client_factory=lambda: client)
    ssh.open()
    ssh.run("id")

    assert client.connect_kwargs["password"] == "hunter2"
    assert "hunter2" not in repr(cfg)
    assert "hunter2" not in caplog.text


def test_run_requires_an_open_live_connection():
    """Running a command when closed, or after the connection dropped, is a `TransportError`."""
    client = FakeSshClient(known={"dut"})
    ssh = session_with(client)
    with pytest.raises(TransportError, match="not open"):
        ssh.run("true")

    ssh.open()
    client.transport.active = False
    with pytest.raises(TransportError, match="connection lost"):
        ssh.run("true")


def test_missing_paramiko_gives_an_install_hint(monkeypatch):
    """Without the ``ssh`` extra, opening a session says exactly what to install.

    paramiko is optional, so the core stays light; the error must make the fix obvious.
    """
    monkeypatch.setitem(sys.modules, "paramiko", None)  # makes ``import paramiko`` fail

    with pytest.raises(TransportError, match=r"pip install 'mastif\[ssh\]'"):
        SshSession(SshConfig(host="dut", username="root")).open()


def test_stream_over_interactive_shell():
    """`SshStreamTransport` reads and writes the interactive shell like a console.

    That is what lets `LineIO`, `Scpi` and ``mastif.line-shell`` run over SSH.
    """
    client = FakeSshClient(known={"dut"})
    stream = SshStreamTransport(
        SshConfig(host="dut", username="root"), client_factory=lambda: client
    )
    stream.open()
    client.shell.incoming += [b"up 3 ", b"days\r\n$ "]

    stream.write(b"uptime\n")

    assert stream.read_until(b"\r\n") == b"up 3 days"
    assert client.shell.sent == b"uptime\n"
    stream.close()
    assert client.shell.closed and client.closed


def test_stream_reports_a_closed_shell_as_transport_error():
    """When the remote shell exits, reads fail with `TransportError`, not a timeout."""
    client = FakeSshClient(known={"dut"})
    stream = SshStreamTransport(
        SshConfig(host="dut", username="root"), client_factory=lambda: client
    )
    stream.open()
    client.shell.closed = True

    with pytest.raises(TransportError, match="shell closed by peer"):
        stream.read_until(b"\n")


def test_ssh_shell_strips_output_and_passes_the_timeout():
    """``mastif.ssh-shell`` returns stripped output and keeps the exit code and stderr.

    Stripping matches ``mastif.line-shell``, so DUT code sees the same shape whichever
    console the profile chooses.
    """
    session = FakeSshSession(
        {
            "cat /etc/version": "fw 2.1\n",
            "flash": ShellResult(command="", output="", exit_code=1, stderr="busy\n"),
        }
    )
    session.open()
    cfg = SshShell.Config.model_validate(
        {"transport": {"kind": "ssh", "host": "h", "username": "u"}}
    )
    sh = SshShell(cfg, cast(SshSession, session))

    assert sh.execute("cat /etc/version").output == "fw 2.1"
    failed = sh.execute("flash")
    assert (failed.ok, failed.stderr) == (False, "busy")


def test_ssh_shell_is_a_builtin_driver_asking_for_a_session():
    """``mastif.ssh-shell`` is always registered, and the station injects an `SshSession`."""
    spec = Registry().get("mastif.ssh-shell")

    assert spec.io_params == {"session": SshSession}


@pytest.mark.parametrize(
    ("want", "expected"),
    [
        (StreamTransport, SshStreamTransport),
        (LineIO, StreamLineIO),
        (Scpi, Scpi),
        (SshSession, SshSession),
    ],
)
def test_build_io_over_ssh(want, expected):
    """Streams, line I/O, SCPI and command sessions can all be built from an SSH config.

    Args:
        want: The I/O type a driver asks for.
        expected: The class `build_io` must return.
    """
    assert isinstance(build_io(want, SshConfig(host="h", username="u")), expected)


@pytest.mark.parametrize(
    ("want", "config"),
    [
        (SshSession, TcpConfig(host="h", port=22)),
        (DatagramChannel, SshConfig(host="h", username="u")),
    ],
)
def test_build_io_rejects_impossible_ssh_combinations(want, config):
    """Command sessions need SSH, and SSH carries no datagrams.

    Args:
        want: The I/O type requested.
        config: A transport that can't provide it.
    """
    with pytest.raises(DriverDefinitionError, match="cannot provide"):
        build_io(want, config)


# ----------------------------------------------------- protocol, with a real server


class RealSshServer:
    """A real SSH server on localhost, built on paramiko's server mode.

    It accepts password ``tester``/``s3cret``, runs scripted exec commands (with
    separate stderr and exit status), and offers an interactive shell that echoes
    commands, answers ``version`` and prints a ``$ `` prompt.
    """

    def __init__(self, paramiko, commands: dict[str, tuple[bytes, bytes, int] | None]) -> None:
        """Generate a host key and start accepting connections."""
        self.paramiko = paramiko
        self.commands = commands
        self.host_key = paramiko.ECDSAKey.generate()
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.transports: list = []
        self.threads: list[threading.Thread] = []
        self._accept_thread = threading.Thread(target=self._accept, daemon=True)
        self._accept_thread.start()

    def known_hosts_file(self, path: Path) -> Path:
        """Write a known-hosts file trusting this server's key."""
        keys = self.paramiko.HostKeys()
        keys.add(f"[127.0.0.1]:{self.port}", self.host_key.get_name(), self.host_key)
        keys.save(str(path))
        return path

    def _accept(self) -> None:
        """Hand every connection to a paramiko server transport."""
        server = self._interface()
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            transport = self.paramiko.Transport(conn)
            transport.add_server_key(self.host_key)
            self.transports.append(transport)
            try:
                transport.start_server(server=server)
            except (self.paramiko.SSHException, EOFError, OSError):
                continue

    def _interface(self):
        """Build the ``ServerInterface`` that answers auth, exec and shell requests."""
        paramiko = self.paramiko
        outer = self

        class Interface(paramiko.ServerInterface):
            def check_channel_request(self, kind, chanid):
                return paramiko.OPEN_SUCCEEDED

            def get_allowed_auths(self, username):
                return "password"

            def check_auth_password(self, username, password):
                ok = (username, password) == ("tester", "s3cret")
                return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

            def check_channel_exec_request(self, channel, command):
                outer._spawn(outer._exec, channel, command.decode())
                return True

            def check_channel_pty_request(self, *args):
                return True

            def check_channel_shell_request(self, channel):
                outer._spawn(outer._shell, channel)
                return True

        return Interface()

    def _spawn(self, target, *args) -> None:
        """Run a channel handler in its own thread, as paramiko recommends."""
        thread = threading.Thread(target=target, args=args, daemon=True)
        self.threads.append(thread)
        thread.start()

    def _exec(self, channel, command: str) -> None:
        """Play one scripted command; ``None`` scripts never finish."""
        reply = self.commands.get(command, (b"", b"not found\n", 127))
        if reply is None:
            return
        out, err, status = reply
        # paramiko acknowledges the exec request only after this handler was started; a
        # real sshd acknowledges first. Give the acknowledgement time to go out.
        time.sleep(0.05)
        try:
            channel.sendall(out)
            channel.sendall_stderr(err)
            channel.send_exit_status(status)
            channel.close()
        except (OSError, EOFError, self.paramiko.SSHException):
            pass

    def _shell(self, channel) -> None:
        """A tiny interactive shell: echo, answer, prompt."""
        try:
            channel.sendall(b"welcome\r\n$ ")
            line = b""
            while chunk := channel.recv(1024):
                line += chunk
                while b"\n" in line:
                    cmd, line = line.split(b"\n", 1)
                    cmd = cmd.strip()
                    reply = b"2.1\r\n" if cmd == b"version" else b""
                    channel.sendall(cmd + b"\r\n" + reply + b"$ ")
        except (OSError, EOFError, self.paramiko.SSHException):
            pass

    def close(self) -> None:
        """Stop accepting and shut down every connection."""
        self.sock.close()
        for transport in self.transports:
            transport.close()
        self._accept_thread.join(timeout=2)
        for thread in self.threads:
            thread.join(timeout=2)


@pytest.fixture
def ssh_server():
    """Start a `RealSshServer` (skipped without paramiko) and stop it after the test.

    Yields:
        A function taking the exec command script and returning a started server.
    """
    paramiko = pytest.importorskip("paramiko")
    servers: list[RealSshServer] = []

    def start(commands=None) -> RealSshServer:
        server = RealSshServer(paramiko, dict(commands or {}))
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()


def real_config(server: RealSshServer, **kwargs) -> SshConfig:
    """An `SshConfig` for the real server, with the right password by default."""
    fields = {
        "host": "127.0.0.1",
        "port": server.port,
        "username": "tester",
        "password": "s3cret",
        "connect_timeout": 5,
        **kwargs,
    }
    return SshConfig.model_validate(fields)


def test_real_server_exec_round_trip(ssh_server, tmp_path):
    """Against a real SSH server, commands return output, stderr and exit codes.

    This checks the whole stack: TCP, key exchange, host-key check against a real
    known-hosts file, password authentication and exec channels.
    """
    server = ssh_server({"echo hi": (b"hi\n", b"", 0), "check": (b"", b"disk full\n", 3)})
    known = server.known_hosts_file(tmp_path / "known_hosts")
    ssh = SshSession(real_config(server, known_hosts_file=str(known)))
    ssh.open()

    ok = ssh.run("echo hi")
    bad = ssh.run("check")
    ssh.close()

    assert (ok.output, ok.exit_code, ok.stderr) == ("hi\n", 0, "")
    assert (bad.output, bad.exit_code, bad.stderr) == ("", 3, "disk full\n")


def test_real_server_unknown_host_is_refused_by_default(ssh_server):
    """A real server whose key isn't known is refused under the default strict policy."""
    server = ssh_server()

    with pytest.raises(TransportError, match="not in known_hosts"):
        SshSession(real_config(server)).open()


def test_real_server_accept_new_saves_the_key_then_checks_it(ssh_server, tmp_path):
    """``accept_new`` trusts the first connection, saves the key, and reuses it.

    The second connection, now strict, succeeds only because the key was saved.
    """
    server = ssh_server({"true": (b"", b"", 0)})
    known = tmp_path / "known_hosts"

    first = SshSession(real_config(server, known_hosts="accept_new", known_hosts_file=str(known)))
    first.open()
    first.close()
    second = SshSession(real_config(server, known_hosts_file=str(known)))
    second.open()

    assert second.run("true").ok
    second.close()
    assert str(server.port) in known.read_text()


def test_real_server_wrong_password_fails_clearly(ssh_server, tmp_path):
    """A wrong password against a real server raises an authentication `TransportError`."""
    server = ssh_server()
    known = server.known_hosts_file(tmp_path / "known_hosts")

    with pytest.raises(TransportError, match="authentication failed"):
        SshSession(real_config(server, password="wrong", known_hosts_file=str(known))).open()


def test_real_server_hung_command_times_out(ssh_server, tmp_path):
    """A command the server never finishes raises `TransportTimeout` within the timeout."""
    server = ssh_server({"hang": None})
    known = server.known_hosts_file(tmp_path / "known_hosts")
    ssh = SshSession(real_config(server, known_hosts_file=str(known)))
    ssh.open()

    started = time.monotonic()
    with pytest.raises(TransportTimeout):
        ssh.run("hang", timeout=0.3)
    ssh.close()

    assert time.monotonic() - started < 3


def test_real_server_line_shell_over_interactive_ssh(ssh_server, tmp_path):
    """``mastif.line-shell`` drives a real interactive SSH shell: echo and prompt removed.

    This is the path for targets that only offer an interactive CLI over SSH.
    """
    server = ssh_server()
    known = server.known_hosts_file(tmp_path / "known_hosts")
    cfg = LineShell.Config.model_validate(
        {
            "transport": real_config(server, known_hosts_file=str(known)).model_dump(),
            "prompt": "$ ",
        }
    )
    stream = build_io(StreamTransport, cfg.transport)
    assert isinstance(stream, SshStreamTransport)
    stream.open()
    sh = LineShell(cfg, stream)
    sh.open()

    result = sh.execute("version")
    stream.close()

    assert result.output == "2.1"
