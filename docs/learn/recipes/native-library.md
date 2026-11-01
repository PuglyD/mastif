# Wrap a vendor DLL

**You have:** an instrument with no documented protocol, only a vendor's library, a `.dll` or `.so`, along with a C header.

**You want:** a normal mastif driver, so that nothing above it knows there's a C library involved.

!!! success "Works today"
    In-process native libraries work today, and you can test them with a fake. Hosting a library in a child process, or in a 32-bit process, is part of the [runtime design](../system-design/execution-modes.md#containing-a-crash).

Calling C from Python is less forgiving than anything else in mastif. A wrong type won't raise an exception. It'll truncate a pointer, corrupt memory, or crash your process. So `NativeLibrary` makes you be explicit, and it refuses anything that isn't declared.

## Start from the header

Every declaration comes from here, so have the vendor's header open beside you:

```c title="the vendor's header (fictional)"
int         ACME_Open(const char *ip, void **handle);      /* 0 = ok */
int         ACME_Close(void *handle);
int         ACME_GetLine(void *handle, int line, int *level);
const char *ACME_ErrorText(int status);
```

Translate each type:

| C | ctypes | Passing it |
|---|---|---|
| `int` | `c_int` | A plain `int` |
| `const char *` (input) | `c_char_p` | `bytes` |
| `void *` | `c_void_p` | The handle |
| `void **`, `int *` (output) | `POINTER(c_void_p)`, `POINTER(c_int)` | `byref(x)` |
| `void` return | `None` | |

Check the calling convention as well. `WINAPI` or `__stdcall` in the header means `stdcall`, and otherwise it's `cdecl`. If you get that wrong, you might crash, or you might corrupt the stack and crash later on.

## The driver

```python
from ctypes import POINTER, byref, c_char_p, c_int, c_void_p

from mastif.resources.driver import DriverConfig, driver
from mastif.resources.std import DigitalIO
from mastif.resources.transports import NativeConfig, NativeLibrary, StatusCheck


@driver("acme.dio-dll", provides=[DigitalIO])
class AcmeDioDll:
    class Config(DriverConfig):
        transport: NativeConfig     # Where the library is: a fact about the station
        ip: str                     # Which box to open

    def __init__(self, cfg: Config, lib: NativeLibrary) -> None:
        self.cfg = cfg
        self.lib = lib
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

## The rules, and the reasons for them

**Declare each function before calling it.** Without a declaration, `ctypes` assumes that everything returns an `int`. On a 64-bit system, that cuts a pointer in half, and you'd get a crash some time later, somewhere unrelated. mastif refuses undeclared calls so that this can't happen.

**Attach a `StatusCheck`.** A vendor's C functions report failure with a return code, and it's so easy to ignore. With a check, a bad status raises `ProtocolError`, with the vendor's own message:

```text title="an example message"
ACME_SetLine returned status -5: line out of range
```

**Don't load the library yourself.** The station loads it, from the profile, before your `open()`, and it unloads it after your `close()`.

**Don't add your own threads.** By default, every call runs on a single dedicated thread, since that's what most vendor libraries need. Sessions opened on one thread and used from another are a common cause of mysterious failures.

**Handle a partial open.** Look at `close`: it checks `self.handle.value` before releasing the handle. If `ACME_Open` failed, then there's no handle, and closing an invalid one might crash. `close()` also runs after a failed `open()`, so it can't assume that anything worked.

## Point the station at it

```yaml title="in a profile"
resources:
  dio:
    driver: acme.dio-dll
    config:
      transport:
        kind: native
        library: acmedio                     # Finds acmedio.dll or libacmedio.so
        search_paths: ["C:/Program Files/Acme/DIO/bin"]
        calling_convention: cdecl            # stdcall if the header says WINAPI
      ip: 192.0.2.40
```

`search_paths` matters on Windows, where the vendor's DLL usually loads other DLLs from its install folder. mastif registers those paths for as long as the library's open.

**Never commit the vendor's library.** It's their proprietary code, so each station installs it using the vendor's own installer. The repository's `.gitignore` excludes these files.

## Test it without the library

`FakeNativeLibrary` stands in for the DLL, and each function is a Python callable or a fixed status. `set_out` fills in output parameters, in the way the C code would:

```python title="continuing the example above"
from mastif_testing import FakeNativeLibrary, check_lifecycle, set_out


def fake_acme() -> FakeNativeLibrary:
    levels = [0] * 8

    def open_(ip, handle):
        set_out(handle, 0x1234)
        return 0

    def get_line(handle, line, level):
        set_out(level, levels[line])
        return 0

    return FakeNativeLibrary({
        "ACME_Open": open_,
        "ACME_Close": 0,
        "ACME_SetLine": 0,
        "ACME_GetLine": get_line,
        "ACME_ErrorText": lambda code: b"line out of range",
    })


lib = fake_acme()
lib.open()
config = {"transport": {"kind": "native", "library": "acmedio"}, "ip": "192.0.2.40"}
report = check_lifecycle(AcmeDioDll, config, lib=lib)
print(report.steps)  # ['build', 'open', 'close']
```

The fake follows the real library's rules: undeclared calls, and functions that don't exist, fail in the same way.

## When loading fails

| The message says | The cause | The fix |
|---|---|---|
| `cannot load ... a library it depends on is missing` | A wrong path, or a missing dependency | Add the vendor's folder to `search_paths` |
| `not a library this 64-bit Python can load` | The SDK is 32-bit only | Install a 64-bit SDK, if there is one |

If the only available library is 32-bit, a 64-bit Python can't load it. Solving that needs a 32-bit host process, and that's part of the [runtime design](../system-design/execution-modes.md#containing-a-crash).

## What a crash means here

Since the library runs inside your process, a crash inside it is a crash of your process. There's no exception to catch. For a library you don't trust, the eventual answer is to host it in a child process, as the runtime will allow. Until then, know that the risk exists, and be sure your [run records](../../getting-started/tutorial/first-results/progress.md#surviving-a-crash) can survive it.

## See also

- The longer [vendor DLL guide](../../wiki/guides/wrap-a-vendor-dll.md).
- [ADR-0035](../../adr/0035-native-vendor-libraries.md), on thread confinement and fault isolation.

**Next:** [Replace hardware with simulation](simulation.md)
