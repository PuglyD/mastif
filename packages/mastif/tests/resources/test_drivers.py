"""Unit tests for `mastif.resources.driver`, `registry` and the built-in channel drivers.

The decorators are the main surface org SDK authors touch, so these tests pin down
the definition-time checks (ids, Config, contracts, ``__init__`` parameters,
channels), how `build_resource` injects config, I/O and loggers, safe-state
behaviour, registry lookups and conflicts, and the line-shell's prompt and echo
handling.
"""

import logging
from typing import Protocol

import pytest
from pydantic import BaseModel, ValidationError

from mastif.resources import ContractMismatch, DriverDefinitionError, DriverNotFound, ResourceError
from mastif.resources._examples import ExamplePsu
from mastif.resources.channels import LineShell, UdpMessageChannel
from mastif.resources.driver import (
    DriverConfig,
    NoConfig,
    build_resource,
    call_hook,
    channel,
    driver,
    dut,
    make_safe,
    spec_of,
)
from mastif.resources.errors import ProtocolError, TransportTimeout
from mastif.resources.registry import Registry
from mastif.resources.std import MessageChannel, PowerSupply, Relay, Shell
from mastif.resources.transports import LineIO, Scpi, TcpConfig
from mastif_testing import FakeLineIO, FakeStream

TCP = {"transport": {"kind": "tcp", "host": "10.0.0.5", "port": 5025}}


class Probe(Protocol):
    """A one-method contract for these tests."""

    def read(self) -> float:
        """Read a value."""
        ...


def test_bad_driver_id_is_rejected():
    """Ids must be ``org.name`` so profiles stay unambiguous across organisations."""
    with pytest.raises(DriverDefinitionError, match="must look like"):

        @driver("NoDots")
        class Bad:
            pass


def test_driver_missing_contract_method_fails_at_definition():
    """A driver that doesn't implement its claimed contract fails when its module loads."""
    with pytest.raises(ContractMismatch):

        @driver("acme.broken", provides=[Probe])
        class Broken:
            pass


def test_config_must_subclass_driver_config():
    """A ``Config`` that isn't a DriverConfig would skip profile validation, so it's refused."""
    with pytest.raises(DriverDefinitionError, match="Config"):

        @driver("acme.cfg")
        class Bad:
            class Config:
                pass


def test_unsuppliable_init_parameter_is_rejected():
    """Only config, I/O and loggers can be injected; other required parameters are errors."""
    with pytest.raises(DriverDefinitionError, match="can't be supplied"):

        @driver("acme.needy")
        class Needy:
            def __init__(self, gain: float) -> None:
                self.gain = gain


def test_io_without_transport_field_is_rejected():
    """Asking for injected I/O requires a ``transport`` field to build it from."""
    with pytest.raises(DriverDefinitionError, match="transport"):

        @driver("acme.no-transport")
        class NoTransport:
            def __init__(self, io: LineIO) -> None:
                self.io = io


def test_driver_without_config_gets_no_config():
    """A driver with no ``Config`` accepts only an empty config mapping."""

    @driver("acme.simple")
    class Simple:
        pass

    assert spec_of(Simple).config_model is NoConfig
    with pytest.raises(ValidationError):
        build_resource(spec_of(Simple), {"unexpected": 1}, name="x")


def test_decorator_returns_the_same_class_without_registering():
    """Decoration attaches a spec only; nothing is registered globally."""

    @driver("acme.plain")
    class Plain:
        pass

    assert spec_of(Plain).cls is Plain
    assert "acme.plain" not in Registry()


def test_build_resource_injects_config_io_and_logger():
    """Each annotated ``__init__`` parameter receives exactly what it asked for."""

    @driver("acme.full")
    class Full:
        class Config(DriverConfig):
            transport: TcpConfig
            channel: int = 1

        def __init__(self, cfg: Config, io: Scpi, log: logging.Logger) -> None:
            self.cfg, self.io, self.log = cfg, io, log

    fake = Scpi(FakeLineIO())
    built = build_resource(
        spec_of(Full), TCP | {"channel": 2}, name="psu", io_factory=lambda *_: fake
    )

    assert built.instance.cfg.channel == 2
    assert built.instance.io is fake and built.io == [fake]
    assert built.instance.log.name.endswith(".psu")


def test_build_resource_rejects_unknown_config_keys():
    """A typo in a profile's config is a validation error, not silently ignored."""
    with pytest.raises(ValidationError):
        build_resource(spec_of(ExamplePsu), TCP | {"chanel": 1}, name="psu")


def test_state_model_is_instantiated_when_declared():
    """Declaring ``state=`` gives every instance a fresh state object."""

    class State(BaseModel):
        booted: bool = False

    @dut("acme.stateful", state=State)
    class Stateful:
        pass

    built = build_resource(spec_of(Stateful), {}, name="dut")

    assert built.instance.state == State()


def test_channels_are_collected_with_their_contracts():
    """Each ``channel()`` is recorded with the contract from its annotation."""

    @dut("acme.board")
    class Board:
        console: Shell = channel()
        ctrl: MessageChannel = channel(optional=True)

    chans = spec_of(Board).channels

    assert (chans["console"].contract, chans["ctrl"].optional) == (Shell, True)


def test_unconnected_channel_read_raises():
    """Reading a required channel before the station attaches it fails clearly."""

    @dut("acme.board2")
    class Board:
        console: Shell = channel()

    with pytest.raises(ResourceError, match="not connected"):
        _ = Board().console


def test_channel_without_annotation_is_rejected():
    """A channel needs a contract annotation, so the station can check what it gets."""
    with pytest.raises(DriverDefinitionError, match="contract annotation"):

        @dut("acme.board3")
        class Board:
            console = channel()


def test_provides_contract_accepts_structural_match():
    """A driver can serve contracts it didn't declare, as long as it satisfies them."""

    @driver("acme.probe")
    class AnyProbe:
        def read(self) -> float:
            return 1.0

    assert spec_of(AnyProbe).provides_contract(Probe)


def test_make_safe_prefers_driver_hook():
    """A driver's own ``safe_state()`` replaces the contract's default action."""

    @driver("acme.relays", provides=[Relay])
    class Relays:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def set(self, channel, closed): ...

        def is_closed(self, channel):
            return False

        def open_all(self):
            self.calls.append("open_all")

        def safe_state(self):
            self.calls.append("custom")

    built = build_resource(spec_of(Relays), {}, name="r")

    assert make_safe(built) and built.instance.calls == ["custom"]


def test_make_safe_uses_contract_action():
    """Without a hook, the contract's safe-state action runs (supply output off)."""
    io = FakeLineIO()
    built = build_resource(spec_of(ExamplePsu), TCP, name="psu", io_factory=lambda *_: Scpi(io))

    assert make_safe(built) and io.written == ["OUTP OFF"]


def test_make_safe_reports_when_nothing_to_do():
    """Resources with no safe-state action report False, so the station can log it."""

    @driver("acme.inert")
    class Inert:
        pass

    assert not make_safe(build_resource(spec_of(Inert), {}, name="x"))


def test_call_hook_skips_missing_hooks():
    """Lifecycle hooks are optional; a missing one simply returns None."""
    assert call_hook(object(), "open") is None


def test_registry_lookup_and_unknown_id():
    """Ids resolve to specs; unknown ids list the known ones to help spot typos."""
    reg = Registry([ExamplePsu])

    assert reg.get("demo.example-psu").provides == (PowerSupply,)
    with pytest.raises(DriverNotFound, match="demo.example-psu"):
        reg.get("demo.example-pus")


def test_registry_rejects_conflicting_ids():
    """Two different classes with one id would make a profile ambiguous."""

    @driver("demo.example-psu")
    class Impostor:
        pass

    with pytest.raises(DriverDefinitionError, match="used by both"):
        Registry([ExamplePsu, Impostor])


def test_registry_includes_builtin_channels_by_default():
    """The built-in channel drivers are always available unless excluded."""
    assert {"mastif.udp", "mastif.line-shell"} <= set(Registry().ids())
    assert Registry(builtin=False).ids() == []


def test_registry_accepts_modules():
    """Adding a module collects every decorated class in it."""
    import mastif.resources._examples as examples

    assert Registry([examples], builtin=False).ids() == ["demo.example-psu"]


def test_builtin_channels_provide_their_contracts():
    """The built-in drivers satisfy the std contracts DUTs declare."""
    assert spec_of(LineShell).provides_contract(Shell)
    assert spec_of(UdpMessageChannel).provides_contract(MessageChannel)


def _shell(stream: FakeStream, **config) -> LineShell:
    """Build a LineShell over a fake stream with a ``# `` prompt.

    Args:
        stream: The fake console stream (opened by this helper).
        **config: Extra config fields.

    Returns:
        The shell.
    """
    stream.open()
    cfg = LineShell.Config.model_validate(
        {"transport": {"kind": "serial", "port": "COM3"}, "prompt": "# "} | config
    )
    return LineShell(cfg, stream)


def test_line_shell_strips_echo_and_prompt():
    """Output excludes the echoed command and the trailing prompt."""
    s = FakeStream()
    sh = _shell(s)
    s.feed(b"cat /etc/version\r\nfw 2.1\r\nbuilt today\r\n# ")

    assert sh.execute("cat /etc/version").output == "fw 2.1\nbuilt today"
    assert s.sent == b"cat /etc/version\n"


def test_line_shell_without_echo_keeps_first_line():
    """With ``echo: false`` the first output line is real output, not an echo."""
    s = FakeStream()
    sh = _shell(s, echo=False)
    s.feed(b"cat /etc/version\r\n# ")

    assert sh.execute("cat /etc/version").output == "cat /etc/version"


def test_line_shell_sync_on_open_waits_for_prompt():
    """Opening sends an empty line and consumes boot noise up to the prompt."""
    s = FakeStream()
    sh = _shell(s)
    s.feed(b"booting...\r\n# ")

    sh.open()

    assert s.sent == b"\n"


def test_line_shell_bad_exit_code_is_protocol_error():
    """An exit-code command printing non-numbers is a protocol error."""
    s = FakeStream()
    sh = _shell(s, exit_code_command="echo $?")
    s.feed(b"ls\nfile\n# ")
    s.feed(b"echo $?\nhuh\n# ")

    with pytest.raises(ProtocolError):
        sh.execute("ls")


def test_line_shell_times_out_without_prompt():
    """A hung command raises TransportTimeout instead of blocking the run."""
    s = FakeStream()
    sh = _shell(s)

    with pytest.raises(TransportTimeout):
        sh.execute("sleep 100", timeout=0.05)
