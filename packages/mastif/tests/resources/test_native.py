"""Tests for `mastif.resources.transports.native` and `mastif_testing.FakeNativeLibrary`.

Vendor libraries fail hard (a crashed process, a truncated handle), so the rules that
prevent that are pinned down here:

- a real system library (``kernel32`` on Windows, the C library elsewhere) loads, its
  declared functions are called, and calls run on one dedicated thread when confined
- functions must be declared before they're called, and arguments must match
- load failures carry actionable hints (missing dependency, wrong architecture)
- library names are resolved through ``search_paths`` with each platform's file names
- `StatusCheck` turns status codes into `ProtocolError` with the vendor's text
- `FakeNativeLibrary` follows the same rules, so a driver tested against it behaves the
  same against the real library; the guide's ``acme.dio-dll`` example runs against it
"""

import ctypes
import ctypes.util
import sys
import threading
from ctypes import POINTER, byref, c_char_p, c_int, c_void_p
from types import SimpleNamespace

import pytest

from mastif.resources import DriverDefinitionError, ProtocolError, TransportError
from mastif.resources.driver import DriverConfig, build_resource, driver, spec_of
from mastif.resources.std import DigitalIO
from mastif.resources.transports import (
    NativeConfig,
    NativeLibrary,
    Scpi,
    StatusCheck,
    TcpConfig,
    build_io,
)
from mastif.resources.transports.native import load_error_hint, resolve_library
from mastif_testing import FakeNativeLibrary, check_lifecycle, set_out

WINDOWS = sys.platform == "win32"


def system_library() -> NativeConfig:
    """A library every test machine has: ``kernel32`` (stdcall) or the C library."""
    if WINDOWS:
        return NativeConfig(library="kernel32", calling_convention="stdcall")
    libc = ctypes.util.find_library("c")
    if libc is None:
        pytest.skip("no C library found on this system")
    return NativeConfig(library=libc)


def thread_id_function(lib: NativeLibrary) -> str:
    """Declare and return the name of a function reporting the calling OS thread."""
    if WINDOWS:
        lib.function("GetCurrentThreadId", ctypes.c_uint32, [])
        return "GetCurrentThreadId"
    lib.function("pthread_self", ctypes.c_ulong, [])
    return "pthread_self"


def caller_thread_id() -> int:
    """The calling thread's id, in the same terms as `thread_id_function`."""
    return threading.get_native_id() if WINDOWS else threading.get_ident()


# ---------------------------------------------------------- a real system library


def test_system_library_loads_and_calls_declared_functions():
    """A real library loads, a declared function is called, and close unloads it.

    This is the whole real path: name resolution, the platform loader and calling
    convention, prototype binding, argument conversion and unloading.
    """
    lib = NativeLibrary(system_library())
    lib.open()
    name = "lstrlenA" if WINDOWS else "strlen"
    lib.function(name, ctypes.c_size_t if not WINDOWS else c_int, [c_char_p])

    assert lib.call(name, b"hello") == 5
    lib.close()
    assert not lib.is_open


def test_confined_calls_all_run_on_one_dedicated_thread():
    """With ``thread_confined`` (the default) every call runs on the same worker thread.

    Many vendor libraries keep per-thread state or aren't thread-safe; calls arriving
    from different Python threads must still reach the library from one thread.
    """
    lib = NativeLibrary(system_library())
    lib.open()
    fn = thread_id_function(lib)
    seen: list[int] = []

    seen.append(lib.call(fn))
    other = threading.Thread(target=lambda: seen.append(lib.call(fn)))
    other.start()
    other.join()
    lib.close()

    assert seen[0] == seen[1]
    assert seen[0] != caller_thread_id()


def test_unconfined_calls_run_on_the_callers_thread():
    """With ``thread_confined: false`` calls run directly on the calling thread."""
    cfg = system_library().model_copy(update={"thread_confined": False})
    lib = NativeLibrary(cfg)
    lib.open()
    fn = thread_id_function(lib)

    assert lib.call(fn) == caller_thread_id()
    lib.close()


def test_functions_declared_before_open_are_bound_when_it_loads():
    """Declarations made before ``open`` are bound on load, and survive a reopen.

    Drivers may declare their prototypes in ``__init__``, before the station opens the
    library.
    """
    lib = NativeLibrary(system_library())
    fn = thread_id_function(lib)
    lib.open()
    lib.call(fn)
    lib.close()

    lib.open()
    assert isinstance(lib.call(fn), int)
    lib.close()


def test_missing_symbol_is_a_transport_error_naming_it():
    """Declaring a function the library doesn't export fails clearly.

    Usually the installed vendor library is an older or newer version than the driver
    expects.
    """
    lib = NativeLibrary(system_library())
    lib.open()

    with pytest.raises(TransportError, match="no function 'mastif_no_such_fn'"):
        lib.function("mastif_no_such_fn", c_int, [])
    lib.close()


def test_calling_an_undeclared_function_is_refused():
    """Calling a function without a declared prototype is a `DriverDefinitionError`.

    Undeclared functions are assumed to return a C ``int``, which silently truncates
    64-bit handles and pointers: the classic crash that this rule prevents.
    """
    lib = NativeLibrary(system_library())
    lib.open()

    with pytest.raises(DriverDefinitionError, match="before being declared"):
        lib.call("GetTickCount64" if WINDOWS else "getpid")
    lib.close()


def test_arguments_not_matching_the_prototype_are_a_definition_error():
    """Passing an argument ctypes can't convert to the declared type is a driver bug."""
    lib = NativeLibrary(system_library())
    lib.open()
    name = "lstrlenA" if WINDOWS else "strlen"
    lib.function(name, c_int, [c_char_p])

    with pytest.raises(DriverDefinitionError, match="don't match the declared argtypes"):
        lib.call(name, 12345)
    lib.close()


def test_calling_before_open_is_a_transport_error():
    """A closed library refuses calls, like a closed connection."""
    lib = NativeLibrary(NativeConfig(library="acmedio"))
    lib.function("ACME_Count", c_int, [])

    with pytest.raises(TransportError, match="not open"):
        lib.call("ACME_Count")


# --------------------------------------------------------------- load failures


def test_missing_library_explains_search_paths_and_dependencies():
    """A library that can't be found raises `TransportError` with what to check.

    On Windows the same error appears when the DLL exists but one of *its* dependencies
    is missing, so the hint covers both.
    """
    lib = NativeLibrary(NativeConfig(library="mastif_no_such_library_xyz"))

    with pytest.raises(TransportError, match="cannot load.*search_paths") as caught:
        lib.open()
    assert not lib.is_open
    assert "depends" in str(caught.value)


@pytest.mark.skipif(not WINDOWS, reason="Windows error 193 is specific to Windows")
def test_non_loadable_file_points_to_a_32_bit_host_process(tmp_path):
    """A file of the wrong architecture (or no library at all) gets the 32-bit hint.

    A 32-bit vendor DLL can never load into 64-bit Python; the message must say so and
    point to the planned host-process mechanism instead of a cryptic Windows error.
    """
    fake_dll = tmp_path / "acmedio.dll"
    fake_dll.write_bytes(b"MZ not really a library")

    with pytest.raises(TransportError, match="32-bit host process"):
        NativeLibrary(NativeConfig(library=str(fake_dll))).open()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (OSError("libacme.so: wrong ELF class: ELFCLASS32"), "32-bit host process"),
        (OSError("dlopen: mach-o file, but is an incompatible architecture"), "architecture"),
        (FileNotFoundError("Could not find module 'acmedio'"), "search_paths"),
        (OSError("libacme.so: cannot open shared object file: No such file"), "search_paths"),
        (OSError("something unusual"), "installed for this platform"),
    ],
)
def test_load_error_hints_cover_every_platform(error, expected):
    """Load errors from Windows, Linux and macOS each map to the right advice.

    Args:
        error: The loader's error, with the platform's wording.
        expected: Text the hint must contain.
    """
    assert expected in load_error_hint(error)


def test_stdcall_is_refused_outside_windows(monkeypatch):
    """``stdcall`` only exists on Windows; asking for it elsewhere fails before loading."""
    monkeypatch.setattr(sys, "platform", "linux")
    lib = NativeLibrary(NativeConfig(library="acmedio", calling_convention="stdcall"))

    with pytest.raises(TransportError, match="Windows-only"):
        lib.open()


# ---------------------------------------------------------- name resolution


@pytest.mark.parametrize(
    ("platform", "filename"),
    [("win32", "acmedio.dll"), ("linux", "libacmedio.so"), ("darwin", "libacmedio.dylib")],
)
def test_library_names_are_found_in_search_paths(tmp_path, platform, filename):
    """A bare name finds the platform's file name in ``search_paths``.

    Profiles can then name the library once (``acmedio``) and stay portable.

    Args:
        tmp_path: A folder standing in for the vendor's install folder.
        platform: The ``sys.platform`` value.
        filename: The file the vendor installs on that platform.
    """
    (tmp_path / filename).write_bytes(b"")

    found = resolve_library("acmedio", [str(tmp_path)], platform=platform, find=lambda _: None)

    assert found == str(tmp_path / filename)


def test_explicit_paths_are_used_as_given_and_names_fall_back_to_the_system():
    """A value with a folder is used as is; an unknown name falls back to the system search."""
    assert resolve_library("C:/Acme/acmedio.dll") == "C:/Acme/acmedio.dll"
    assert resolve_library("acmedio", [], find=lambda name: f"/usr/lib/lib{name}.so") == (
        "/usr/lib/libacmedio.so"
    )
    assert resolve_library("acmedio", [], find=lambda _: None) == "acmedio"


def test_loading_happens_on_the_worker_thread_with_an_injected_loader():
    """The library is loaded on the same thread that later serves its calls.

    Some vendor libraries initialise per-thread state in their load routine.
    """
    threads: dict[str, int] = {}

    def where(label: str):
        def fn() -> int:
            threads[label] = threading.get_ident()
            return 0

        return fn

    def loader(path: str, convention: str) -> SimpleNamespace:
        threads["load"] = threading.get_ident()
        return SimpleNamespace(ACME_Init=where("call"))

    lib = NativeLibrary(NativeConfig(library="acmedio"), loader=loader)
    lib.open()
    lib.function("ACME_Init", c_int, [])
    lib.call("ACME_Init")
    lib.close()

    assert threads["load"] == threads["call"] != threading.get_ident()


# --------------------------------------------------------------- status checks


def test_status_check_raises_with_the_vendor_text():
    """A failing status becomes `ProtocolError` carrying the vendor's own message.

    The vendor's text ("device busy") is what an engineer needs to act on; a bare
    number isn't.
    """
    status = StatusCheck(error_text=lambda code: b"device busy" if code == -3 else b"")

    assert status(0, "ACME_SetLine") == 0
    with pytest.raises(ProtocolError, match="ACME_SetLine returned status -3: device busy"):
        status(-3, "ACME_SetLine")


def test_status_check_survives_a_failing_error_text_function():
    """If fetching the error text fails too, the original failure is still reported."""

    def broken(code: int) -> str:
        raise RuntimeError("library gone")

    with pytest.raises(ProtocolError, match="status 5: .*unavailable: library gone"):
        StatusCheck(error_text=broken)(5, "ACME_Close")


def test_status_check_accepts_several_success_codes():
    """Libraries that return "1 = done" as well as "0 = ok" can list both."""
    assert StatusCheck(ok=(0, 1))(1, "ACME_Poll") == 1


# ---------------------------------------------------- factory and the fake


def test_build_io_makes_a_native_library_only_from_native_configs():
    """`NativeLibrary` is injectable from ``kind: native``, and only from it."""
    assert isinstance(build_io(NativeLibrary, NativeConfig(library="acmedio")), NativeLibrary)
    with pytest.raises(DriverDefinitionError, match="over a 'native' transport"):
        build_io(Scpi, NativeConfig(library="acmedio"))
    with pytest.raises(DriverDefinitionError, match="over a 'tcp' transport"):
        build_io(NativeLibrary, TcpConfig(host="h", port=1))


def test_fake_follows_the_real_rules():
    """The fake refuses what the real library refuses.

    That is: undeclared calls, unknown names, calls while closed, and missing argtypes. A
    driver that passes against the fake must not fail against the real library for one
    of these reasons.
    """
    lib = FakeNativeLibrary({"ACME_Count": 3})
    with pytest.raises(DriverDefinitionError, match="argtypes"):
        lib.function("ACME_Count", c_int, None)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TransportError, match="no function 'ACME_Nope'"):
        lib.function("ACME_Nope", c_int, [])
    lib.function("ACME_Count", c_int, [])
    with pytest.raises(TransportError, match="not open"):
        lib.call("ACME_Count")


# -------------------------------------------- the guide's example driver


@driver("acme.dio-dll", provides=[DigitalIO])
class AcmeDioDll:
    """A digital I/O box driven through its vendor DLL (fictional; see the guide).

    The DLL opens a session handle to the box's IP address, like many networked lab
    boxes with a vendor SDK.
    """

    class Config(DriverConfig):
        """Where the DLL is (``transport``) and which box to open (``ip``)."""

        transport: NativeConfig
        ip: str

    def __init__(self, cfg: Config, lib: NativeLibrary) -> None:
        """Keep the config and the library the station injects."""
        self.cfg = cfg
        self.lib = lib
        self.handle = c_void_p()

    def open(self) -> None:
        """Declare the functions and open a session to the box."""
        status = StatusCheck(error_text=self._error_text)
        self.lib.function("ACME_ErrorText", c_char_p, [c_int])
        self.lib.function("ACME_Open", c_int, [c_char_p, POINTER(c_void_p)], check=status)
        self.lib.function("ACME_Close", c_int, [c_void_p], check=status)
        self.lib.function("ACME_SetLine", c_int, [c_void_p, c_int, c_int], check=status)
        self.lib.function("ACME_GetLine", c_int, [c_void_p, c_int, POINTER(c_int)], check=status)
        self.lib.call("ACME_Open", self.cfg.ip.encode(), byref(self.handle))

    def _error_text(self, code: int) -> bytes:
        """Ask the DLL what a status code means."""
        return self.lib.call("ACME_ErrorText", code)

    def write(self, line: str | int, high: bool) -> None:
        """Drive one output line."""
        self.lib.call("ACME_SetLine", self.handle, int(line), int(high))

    def read(self, line: str | int) -> bool:
        """Read one input line."""
        level = c_int()
        self.lib.call("ACME_GetLine", self.handle, int(line), byref(level))
        return bool(level.value)

    def close(self) -> None:
        """Close the session."""
        if self.handle.value:
            self.lib.call("ACME_Close", self.handle)
            self.handle = c_void_p()


def fake_acme_dll() -> FakeNativeLibrary:
    """A fake of the fictional ACME DIO DLL: 8 lines, session handle 0x1234."""
    levels = [0] * 8

    def open_(ip: bytes, handle) -> int:
        if ip != b"10.0.0.40":
            return -2
        set_out(handle, 0x1234)
        return 0

    def set_line(handle, line: int, high: int) -> int:
        if not 0 <= line < 8:
            return -5
        levels[line] = high
        return 0

    def get_line(handle, line: int, level) -> int:
        set_out(level, levels[line])
        return 0

    texts = {-2: b"no device at address", -5: b"line out of range"}
    return FakeNativeLibrary(
        {
            "ACME_Open": open_,
            "ACME_Close": 0,
            "ACME_SetLine": set_line,
            "ACME_GetLine": get_line,
            "ACME_ErrorText": lambda code: texts.get(code, b"unknown error"),
        }
    )


def build_acme(fake: FakeNativeLibrary, ip: str = "10.0.0.40"):
    """Build the example driver as the station would, with the fake injected."""
    return build_resource(
        spec_of(AcmeDioDll),
        {"transport": {"kind": "native", "library": "acmedio"}, "ip": ip},
        name="dio",
        io_factory=lambda want, cfg, log: fake,
    )


def test_example_driver_round_trip_with_the_fake():
    """The guide's ``acme.dio-dll`` driver works end to end against `FakeNativeLibrary`.

    Output parameters (the session handle, the line level) are filled with `set_out`,
    exactly as the vendor's C functions would fill them.
    """
    fake = fake_acme_dll()
    built = build_acme(fake)
    fake.open()
    dio = built.instance
    dio.open()

    dio.write(3, True)

    assert dio.read(3) is True
    assert dio.read(4) is False
    assert dio.handle.value == 0x1234
    dio.close()
    assert [name for name, _ in fake.calls][-1] == "ACME_Close"


def test_example_driver_reports_vendor_errors_by_text():
    """A vendor failure surfaces as `ProtocolError` with the DLL's own explanation."""
    fake = fake_acme_dll()
    dio = build_acme(fake).instance
    fake.open()
    dio.open()

    with pytest.raises(ProtocolError, match="ACME_SetLine returned status -5: line out of range"):
        dio.write(9, True)


def test_example_driver_passes_the_lifecycle_conformance_check():
    """The example driver satisfies mastif's standard lifecycle and contract check."""
    fake = fake_acme_dll()
    fake.open()  # the station opens injected I/O before the driver's open()
    config = {"transport": {"kind": "native", "library": "acmedio"}, "ip": "10.0.0.40"}

    report = check_lifecycle(AcmeDioDll, config, lib=fake)

    assert report.steps == ["build", "open", "close"]
    assert fake.calls[0] == ("ACME_Open", (b"10.0.0.40", fake.calls[0][1][1]))
