# Guide: wrap a vendor DLL

Some instruments come with a vendor library (a Windows DLL or a Linux shared object)
instead of a documented protocol. This guide wraps one in a mastif driver, step by step,
and tests it without the library. The design is
[ADR-0035](../../adr/0035-native-vendor-libraries.md); read
[Write a driver](write-a-driver.md) first if you haven't.

The example is a fictional digital I/O box, **ACME DIO**, whose SDK opens a session
handle to the box's IP address, a common shape for networked lab boxes.

## 1. Read the vendor header

The SDK ships a C header. The parts we need:

```c
int         ACME_Open(const char *ip, void **handle);      /* 0 = ok */
int         ACME_Close(void *handle);
int         ACME_SetLine(void *handle, int line, int high);
int         ACME_GetLine(void *handle, int line, int *level);
const char *ACME_ErrorText(int status);
```

Translate each C type into a ctypes type:

| C | ctypes |
|---|---|
| `int` | `c_int` |
| `const char *` (in) | `c_char_p` (pass `bytes`) |
| `void *` | `c_void_p` |
| `void **` / `int *` (out) | `POINTER(c_void_p)` / `POINTER(c_int)`; pass `byref(x)` |
| `void` return | `None` |

Check the calling convention too. A header saying `WINAPI` or `__stdcall` means
`stdcall`; otherwise it's `cdecl`.

## 2. Write the driver

```python
from ctypes import POINTER, byref, c_char_p, c_int, c_void_p

from mastif.resources.driver import DriverConfig, driver
from mastif.resources.std import DigitalIO
from mastif.resources.transports import NativeConfig, NativeLibrary, StatusCheck


@driver("acme.dio-dll", provides=[DigitalIO])
class AcmeDioDll:
    class Config(DriverConfig):
        transport: NativeConfig  # where the DLL is: a station fact
        ip: str  # which box to open

    def __init__(self, cfg: Config, lib: NativeLibrary):
        self.cfg = cfg
        self.lib = lib  # injected, already loaded when open() runs
        self.handle = c_void_p()

    def open(self) -> None:
        status = StatusCheck(error_text=self._error_text)
        self.lib.function("ACME_ErrorText", c_char_p, [c_int])
        self.lib.function("ACME_Open", c_int, [c_char_p, POINTER(c_void_p)], check=status)
        self.lib.function("ACME_Close", c_int, [c_void_p], check=status)
        self.lib.function("ACME_SetLine", c_int, [c_void_p, c_int, c_int], check=status)
        self.lib.function("ACME_GetLine", c_int, [c_void_p, c_int, POINTER(c_int)], check=status)
        self.lib.call("ACME_Open", self.cfg.ip.encode(), byref(self.handle))

    def _error_text(self, code: int) -> bytes:
        return self.lib.call("ACME_ErrorText", code)

    def write(self, line, high: bool) -> None:
        self.lib.call("ACME_SetLine", self.handle, int(line), int(high))

    def read(self, line) -> bool:
        level = c_int()
        self.lib.call("ACME_GetLine", self.handle, int(line), byref(level))
        return bool(level.value)

    def close(self) -> None:
        if self.handle.value:
            self.lib.call("ACME_Close", self.handle)
            self.handle = c_void_p()
```

The rules that matter:

- **Declare every function before calling it**, with its return type and argument types.
  mastif refuses undeclared calls, because ctypes would otherwise assume an `int` return
  and cut 64-bit handles in half.
- **Attach a `StatusCheck`** to functions that return status codes. A failure then
  raises `ProtocolError` with the vendor's own text, e.g. `ACME_SetLine returned status
  -5: line out of range`. Never ignore a status code.
- **Don't load the library yourself.** The station loads it (from the profile) before
  your `open()` and unloads it after your `close()`.
- **Don't create threads around the library.** By default every call already runs on one
  dedicated thread, which most vendor libraries need.

## 3. Point the station profile at the DLL

```yaml
resources:
  dio:
    driver: acme.dio-dll
    config:
      transport:
        kind: native
        library: acmedio                     # finds acmedio.dll / libacmedio.so
        search_paths: ["C:/Program Files/Acme/DIO/bin"]
        calling_convention: cdecl            # stdcall if the header says WINAPI
      ip: 10.0.0.40
```

`search_paths` matters on Windows: the vendor DLL usually loads further DLLs from its
install folder, and Windows only finds them if that folder is registered. mastif
registers `search_paths` while the library is open.

**Never commit the vendor library.** It is the vendor's proprietary code. Each station
installs the SDK; the repository's `.gitignore` excludes `*.dll`, `*.so` and `*.dylib`.

## 4. Test it without the DLL

`mastif_testing.FakeNativeLibrary` stands in for the library. Each function is a Python
callable (or a fixed status code), and `set_out` fills output parameters the way the C
code would:

```python
from mastif_testing import FakeNativeLibrary, check_lifecycle, set_out


def fake_acme() -> FakeNativeLibrary:
    levels = [0] * 8

    def open_(ip, handle):
        set_out(handle, 0x1234)  # fills the void** the driver passed
        return 0

    def set_line(handle, line, high):
        if not 0 <= line < 8:
            return -5
        levels[line] = high
        return 0

    def get_line(handle, line, level):
        set_out(level, levels[line])
        return 0

    return FakeNativeLibrary(
        {
            "ACME_Open": open_,
            "ACME_Close": 0,
            "ACME_SetLine": set_line,
            "ACME_GetLine": get_line,
            "ACME_ErrorText": lambda code: b"line out of range",
        }
    )


def test_lifecycle():
    lib = fake_acme()
    lib.open()  # the station does this before open()
    config = {"transport": {"kind": "native", "library": "acmedio"}, "ip": "10.0.0.40"}
    report = check_lifecycle(AcmeDioDll, config, lib=lib)
    assert report.steps == ["build", "open", "close"]
```

The fake follows the real library's rules: undeclared calls, names the library doesn't
have, and calls while closed all fail the same way. A driver that passes against the fake
fails against the real DLL only if the fake's behaviour is wrong. This exact driver and
fake run in mastif's own test suite (`tests/resources/test_native.py`).

## 5. When loading fails

| Message | Cause | Fix |
|---|---|---|
| `cannot load ... Check library and search_paths. ... a library it depends on is missing` | wrong path, or a dependent DLL isn't found | fix `library`; add the SDK's `bin` folder to `search_paths` |
| `... not a library this 64-bit Python can load ... 32-bit host process` | the SDK is 32-bit only | install the vendor's 64-bit SDK; 32-bit host processes are planned (ADR-0030) |
| `the library has no function 'X'` | a different SDK version than the driver expects | install the expected version |
| `'X' was called before being declared` | missing `function(...)` in the driver | declare it |
| `arguments don't match the declared argtypes` | wrong Python type passed (e.g. `str` for `c_char_p`) | pass `bytes`, or fix the prototype |
