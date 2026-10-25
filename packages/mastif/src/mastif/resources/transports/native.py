"""Native vendor libraries: load a DLL or shared object and call it safely through ctypes.

Why this exists:
    Some instruments can only be driven through the vendor's own library: a Windows
    DLL or a Linux shared object that talks to the hardware (over USB, PCIe or the
    network) and exposes C functions such as ``ACME_Open(ip, &handle)``. Calling such a
    library from Python with ``ctypes`` is easy to get subtly wrong, and the failures
    are severe (a crashed process, a corrupted handle) rather than a clean exception:

    - **Undeclared prototypes truncate pointers.** ctypes assumes every function
      returns a C ``int``. On 64-bit Python a returned handle or pointer loses its top
      32 bits and the next call crashes. Every function must declare ``restype`` and
      ``argtypes`` first, so `NativeLibrary` refuses to call anything undeclared.
    - **Many vendor libraries are not thread-safe**, or keep state per thread (the
      thread that opened a session must be the one using it). `NativeLibrary` runs every
      call on one dedicated thread by default.
    - **Dependent DLLs aren't found.** A vendor DLL usually loads further DLLs from its
      install folder, which Windows doesn't search by default. ``search_paths`` are
      registered with ``os.add_dll_directory`` while the library is open.
    - **Error codes need translating.** The usual pattern is "return a status code; on
      failure, call ``GetErrorText(code)``". `StatusCheck` does that once and raises a
      typed error with the vendor's text.
    - **Load failures are cryptic** ("%1 is not a valid Win32 application"). They are
      turned into `TransportError` with a hint: a missing dependency, or a 32-bit
      library that a 64-bit Python can never load (it needs a 32-bit host process; see
      ADR-0030).

Where it fits:
    A driver asks for ``lib: NativeLibrary`` in its ``__init__``; the station builds it
    from ``transport: {kind: native, library: ...}`` in the profile and opens it (loads
    the library) before the driver's ``open()``. The driver declares the functions it
    uses, usually in ``open()``, then calls them. In tests,
    ``mastif_testing.FakeNativeLibrary`` stands in, with Python functions in place of
    the vendor's.
"""

import ctypes
import ctypes.util
import logging
import os
import sys
import threading
from collections.abc import Callable, Collection, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from mastif.resources.errors import DriverDefinitionError, ProtocolError, TransportError
from mastif.resources.transports.config import NativeConfig

type Loader = Callable[[str, str], Any]
"""Loads a library: ``(path, calling_convention) -> library object``. Tests pass their own."""


@dataclass(frozen=True)
class StatusCheck:
    """Turn a vendor status code into success, or a `ProtocolError` with the vendor's text.

    Attach it to a function declaration (``lib.function(..., check=status)``) and every
    call of that function is checked automatically.

    Attributes:
        ok: Status codes meaning success.
        error_text: Turns a failing code into the vendor's message, typically by calling
            the library's own error-string function. May return ``str`` or ``bytes``.

    Example:
        >>> status = StatusCheck(error_text=lambda code: {-3: b"device busy"}.get(code, b"?"))
        >>> status(0, "ACME_SetLine")
        0
        >>> status(-3, "ACME_SetLine")
        Traceback (most recent call last):
        ...
        mastif.resources.errors.ProtocolError: ACME_SetLine returned status -3: device busy
    """

    ok: Collection[int] = (0,)
    error_text: Callable[[int], str | bytes | None] | None = None

    def __call__(self, status: int, what: str) -> int:
        """Return ``status`` if it means success, else raise with the vendor's message.

        Args:
            status: The code the function returned.
            what: The call, for the message (e.g. ``"native:acmedio: ACME_Open"``).

        Returns:
            ``status`` unchanged.

        Raises:
            ProtocolError: If ``status`` is not in ``ok``. If ``error_text`` itself fails,
                the error is still raised, noting that the text was unavailable.

        Example:
            >>> StatusCheck(ok=(0, 1))(1, "ACME_Poll")
            1
        """
        if status in self.ok:
            return status
        detail = ""
        if self.error_text is not None:
            try:
                text = self.error_text(status)
            except Exception as exc:  # the error path must not hide the original failure
                text = f"(error text unavailable: {exc})"
            if isinstance(text, bytes):
                text = text.decode(errors="replace")
            detail = f": {text}" if text else ""
        raise ProtocolError(f"{what} returned status {status}{detail}")


@dataclass(frozen=True)
class NativeFunction:
    """A declared C function: name, return type, argument types and optional status check.

    Create it through `NativeFunction.declare` (or `NativeLibrary.function`), which
    validates the declaration.

    Attributes:
        name: The exported symbol name.
        restype: The ctypes return type, or ``None`` for ``void``.
        argtypes: The ctypes argument types, in order.
        check: Applied to the return value of every call, if given.

    Example:
        >>> f = NativeFunction.declare("ACME_GetLine", ctypes.c_int, [ctypes.c_void_p])
        >>> f.argtypes
        (<class 'ctypes.c_void_p'>,)
    """

    name: str
    restype: Any
    argtypes: tuple[Any, ...]
    check: StatusCheck | None = None

    @classmethod
    def declare(
        cls,
        name: str,
        restype: Any,
        argtypes: Sequence[Any],
        check: StatusCheck | None = None,
    ) -> "NativeFunction":
        """Validate and build a declaration.

        Args:
            name: The exported symbol name.
            restype: The ctypes return type, or ``None`` for ``void``.
            argtypes: The ctypes argument types; ``[]`` for a function without arguments.
            check: Optional status check for the return value.

        Returns:
            The declaration.

        Raises:
            DriverDefinitionError: If ``argtypes`` is not a list or tuple. Leaving it out
                is exactly the mistake that truncates 64-bit pointers.

        Example:
            >>> NativeFunction.declare("ACME_Count", ctypes.c_int, None)
            Traceback (most recent call last):
            ...
            mastif.resources.errors.DriverDefinitionError: ACME_Count: argtypes must be a list...
        """
        if not isinstance(argtypes, list | tuple):
            raise DriverDefinitionError(
                f"{name}: argtypes must be a list of ctypes types; "
                "use [] for a function without arguments"
            )
        return cls(name, restype, tuple(argtypes), check)


def library_candidates(library: str, platform: str = sys.platform) -> list[str]:
    """File names a library name may have on a platform.

    Args:
        library: A name like ``"acmedio"``, or a file name with an extension.
        platform: A ``sys.platform`` value.

    Returns:
        Candidate file names, most literal first.

    Example:
        >>> library_candidates("acmedio", "win32")
        ['acmedio', 'acmedio.dll']
        >>> library_candidates("acmedio", "linux")
        ['acmedio', 'libacmedio.so', 'acmedio.so']
        >>> library_candidates("acmedio.so.2", "linux")
        ['acmedio.so.2']
    """
    if os.path.splitext(library)[1]:
        return [library]
    if platform == "win32":
        return [library, f"{library}.dll"]
    ext = ".dylib" if platform == "darwin" else ".so"
    return [library, f"lib{library}{ext}", f"{library}{ext}"]


def resolve_library(
    library: str,
    search_paths: Sequence[str] = (),
    *,
    platform: str = sys.platform,
    exists: Callable[[str], bool] = os.path.isfile,
    find: Callable[[str], str | None] = ctypes.util.find_library,
) -> str:
    """Work out what to hand to the loader for a configured library.

    The rules, in order:

    1. A value containing a folder (``C:/Acme/acmedio.dll``, ``./libx.so``) is used as is.
    2. Otherwise each folder in ``search_paths`` is searched for the candidate file names
       (`library_candidates`).
    3. Otherwise the system's search (``ctypes.util.find_library``) is asked.
    4. Otherwise the name is returned unchanged, and the loader's own search applies.

    Args:
        library: The configured library (``~`` is expanded).
        search_paths: Folders to search.
        platform: A ``sys.platform`` value.
        exists: Tests whether a file exists (injectable for tests).
        find: The system library search (injectable for tests).

    Returns:
        A path or name for the loader.

    Example:
        >>> resolve_library("acmedio", ["C:/Acme"], platform="win32",
        ...                 exists=lambda p: p.endswith("acmedio.dll"), find=lambda n: None)
        'C:/Acme...acmedio.dll'
        >>> resolve_library("C:/Acme/acmedio.dll")
        'C:/Acme/acmedio.dll'
    """
    lib = os.path.expanduser(library)
    if os.path.dirname(lib):
        return lib
    for folder in search_paths:
        for name in library_candidates(lib, platform):
            path = os.path.join(os.path.expanduser(folder), name)
            if exists(path):
                return path
    return find(lib) or lib


def load_error_hint(exc: OSError) -> str:
    """Explain a library load failure in terms of what to do about it.

    Matches the error number and the messages Windows, Linux and macOS use, so it works
    on any platform.

    Args:
        exc: The error raised by the loader.

    Returns:
        A sentence or two of advice.

    Example:
        >>> load_error_hint(OSError("libacme.so: wrong ELF class: ELFCLASS32"))[:30]
        'The file is not a library this'
        >>> load_error_hint(FileNotFoundError("Could not find module 'acmedio'"))[:40]
        'Check `library` and `search_paths`. If t'
    """
    text = str(exc)
    winerror = getattr(exc, "winerror", None)
    wrong_arch = (
        "not a valid Win32 application",
        "wrong ELF class",
        "incompatible architecture",
        "mach-o file, but is an incompatible",
    )
    if winerror == 193 or any(marker in text for marker in wrong_arch):
        bits = ctypes.sizeof(ctypes.c_void_p) * 8
        return (
            f"The file is not a library this {bits}-bit Python can load. It may be built "
            "for another architecture: a 32-bit-only vendor DLL can never load into "
            "64-bit Python and needs a 32-bit host process (see ADR-0030). Or the file "
            "is not a library at all."
        )
    missing = ("cannot open shared object file", "image not found", "no such file")
    if (
        isinstance(exc, FileNotFoundError)
        or winerror == 126
        or any(marker in text.lower() for marker in missing)
    ):
        return (
            "Check `library` and `search_paths`. If the file exists, a library it depends "
            "on is missing: add that library's folder to `search_paths`."
        )
    return "Check that the library and its dependencies are installed for this platform."


def _ctypes_loader(path: str, calling_convention: str) -> Any:
    """Load a library with ctypes: ``WinDLL`` for stdcall, ``CDLL`` for cdecl.

    Example:
        ``_ctypes_loader("kernel32", "stdcall")`` on Windows.
    """
    if calling_convention == "stdcall":
        return getattr(ctypes, "WinDLL")(path)  # noqa: B009  # WinDLL exists only on Windows
    return ctypes.CDLL(path)


def _free(lib: Any) -> None:
    """Unload a library loaded by `_ctypes_loader`; objects without a handle are skipped.

    Example:
        Called by `NativeLibrary.close` on the thread that loaded the library.
    """
    import _ctypes  # the C half of ctypes; provides the unload functions

    handle = getattr(lib, "_handle", None)
    if not isinstance(handle, int):
        return
    if sys.platform == "win32":
        getattr(_ctypes, "FreeLibrary")(handle)  # noqa: B009  # Windows-only function
    else:
        getattr(_ctypes, "dlclose")(handle)  # noqa: B009  # POSIX-only function


class NativeLibrary:
    """A vendor library, loaded on `open`, with declared functions and confined calls.

    Example:
        Calling a Windows system DLL (runs on Windows only)::

            lib = NativeLibrary(NativeConfig(library="kernel32", calling_convention="stdcall"))
            lib.open()
            lib.function("GetTickCount64", ctypes.c_uint64, [])
            print(lib.call("GetTickCount64"))
            lib.close()

        A driver wrapping a vendor DLL declares its functions in ``open()``::

            def open(self) -> None:
                status = StatusCheck(error_text=self._error_text)
                self.lib.function("ACME_Open", c_int, [c_char_p, POINTER(c_void_p)],
                                  check=status)
                self.lib.call("ACME_Open", self.cfg.ip.encode(), byref(self.handle))
    """

    def __init__(
        self,
        config: NativeConfig,
        logger: logging.Logger | None = None,
        loader: Loader | None = None,
    ) -> None:
        """Prepare the library; nothing is loaded until `open`.

        Args:
            config: Which library, where to search, the calling convention and whether
                calls are confined to one thread.
            logger: Where to trace calls.
            loader: Loads the library; defaults to ctypes. Tests pass their own.

        Example:
            >>> NativeLibrary(NativeConfig(library="acmedio")).name
            'native:acmedio'
        """
        self.config = config
        self.name = f"native:{config.library}"
        self.log = logger or logging.getLogger("mastif.io")
        self._loader = loader or _ctypes_loader
        self._lib: Any = None
        self._path: str | None = None
        self._functions: dict[str, NativeFunction] = {}
        self._bound: dict[str, Any] = {}
        self._worker: ThreadPoolExecutor | None = None
        self._worker_ident: int | None = None
        self._dll_dirs: list[Any] = []

    @property
    def is_open(self) -> bool:
        """Whether the library is loaded.

        Example:
            >>> NativeLibrary(NativeConfig(library="acmedio")).is_open
            False
        """
        return self._lib is not None

    @property
    def path(self) -> str | None:
        """What was handed to the loader, once open; useful in logs and bug reports.

        Example:
            >>> NativeLibrary(NativeConfig(library="acmedio")).path is None
            True
        """
        return self._path

    def open(self) -> None:
        """Load the library and bind every function declared so far.

        With ``thread_confined``, the worker thread starts first and the library is
        loaded on it, because some libraries initialise per-thread state when loaded.

        Raises:
            TransportError: If the library can't be loaded (with a hint), ``stdcall`` is
                requested outside Windows, or a declared function is missing from it.

        Example:
            Called by the station before the driver's ``open()``.
        """
        if self._lib is not None:
            return
        cfg = self.config
        if cfg.calling_convention == "stdcall" and sys.platform != "win32":
            raise TransportError(f"{self.name}: calling_convention 'stdcall' is Windows-only")
        self._path = resolve_library(cfg.library, cfg.search_paths)
        if cfg.thread_confined:
            self._worker = ThreadPoolExecutor(1, thread_name_prefix=f"mastif-{self.name}")
            self._worker_ident = self._worker.submit(threading.get_ident).result()
        try:
            self._add_dll_directories()
            self._lib = self._run(self._load)
            for fn in self._functions.values():
                self._bind(fn)
        except BaseException:
            self._lib = None
            self._shutdown()
            raise
        self.log.debug("%s: loaded %s", self.name, self._path)

    def _add_dll_directories(self) -> None:
        """Register ``search_paths`` for dependent-DLL lookup (Windows only).

        The registration is process-wide and lasts until `close`.

        Example:
            ``search_paths: ["C:/Program Files/Acme/bin"]`` lets ``acmedio.dll`` find
            ``acmeusb.dll`` next to it.
        """
        add = getattr(os, "add_dll_directory", None)
        if add is None:
            return
        for folder in self.config.search_paths:
            path = os.path.abspath(os.path.expanduser(folder))
            if os.path.isdir(path):
                self._dll_dirs.append(add(path))

    def _load(self) -> Any:
        """Call the loader, translating its errors.

        Raises:
            TransportError: With a hint from `load_error_hint`.

        Example:
            Runs on the worker thread when calls are confined.
        """
        assert self._path is not None
        try:
            return self._loader(self._path, self.config.calling_convention)
        except OSError as exc:
            raise TransportError(
                f"{self.name}: cannot load {self._path!r}: {exc}. {load_error_hint(exc)}"
            ) from exc

    def _bind(self, fn: NativeFunction) -> None:
        """Look up a declared function and apply its prototype.

        Raises:
            TransportError: If the library doesn't export it.

        Example:
            Called by `open` and by `function` once the library is loaded.
        """
        try:
            target = getattr(self._lib, fn.name)
        except AttributeError as exc:
            raise TransportError(
                f"{self.name}: the library has no function {fn.name!r}; "
                "check the installed library version"
            ) from exc
        target.restype = fn.restype
        target.argtypes = fn.argtypes
        self._bound[fn.name] = target

    def function(
        self,
        name: str,
        restype: Any,
        argtypes: Sequence[Any],
        check: StatusCheck | None = None,
    ) -> NativeFunction:
        """Declare a function's prototype; required before it can be called.

        May be called before or after `open`. Before, the declaration is bound when the
        library loads; after, it is bound at once. Declaring a name again replaces its
        prototype.

        Args:
            name: The exported symbol name.
            restype: The ctypes return type, or ``None`` for ``void``.
            argtypes: The ctypes argument types; ``[]`` for none.
            check: Applied to every call's return value, e.g. a `StatusCheck`.

        Returns:
            The declaration, which `call` also accepts in place of the name.

        Raises:
            DriverDefinitionError: If ``argtypes`` is missing or not a list.
            TransportError: If the library is open and doesn't export ``name``.

        Example:
            >>> lib = NativeLibrary(NativeConfig(library="acmedio"))
            >>> lib.function("ACME_Count", ctypes.c_int, []).name
            'ACME_Count'
        """
        fn = NativeFunction.declare(name, restype, argtypes, check)
        self._functions[name] = fn
        if self._lib is not None:
            self._bind(fn)
        return fn

    def call(self, fn: NativeFunction | str, *args: Any) -> Any:
        """Call a declared function, on the worker thread if calls are confined.

        The call blocks until the library returns; a hung vendor call can't be
        interrupted from Python.

        Args:
            fn: The function's name or declaration.
            *args: The arguments, converted by ctypes according to ``argtypes``.

        Returns:
            The return value, converted according to ``restype``. If the declaration has
            a ``check``, it has passed.

        Raises:
            TransportError: If the library is not open, or the call failed inside the
                library (e.g. an access violation reported by Windows).
            DriverDefinitionError: If the function wasn't declared, or the arguments
                don't match the declared types.
            ProtocolError: If the declaration's status check fails.

        Example:
            ``lib.call("ACME_SetLine", handle, 3, 1)`` returns ``0``.
        """
        name = fn if isinstance(fn, str) else fn.name
        if self._lib is None:
            raise TransportError(f"{self.name}: not open")
        target = self._bound.get(name)
        if target is None:
            raise DriverDefinitionError(
                f"{self.name}: {name!r} was called before being declared; "
                "declare it with function(name, restype, argtypes) first"
            )
        self.log.debug("%s: %s%r", self.name, name, args)
        try:
            result = self._run(lambda: target(*args))
        except ctypes.ArgumentError as exc:
            raise DriverDefinitionError(
                f"{self.name}: {name}: arguments don't match the declared argtypes: {exc}"
            ) from exc
        except OSError as exc:
            raise TransportError(f"{self.name}: {name} failed inside the library: {exc}") from exc
        self.log.debug("%s: %s -> %r", self.name, name, result)
        check = self._functions[name].check
        if check is not None:
            check(result, f"{self.name}: {name}")
        return result

    def _run(self, work: Callable[[], Any]) -> Any:
        """Run ``work`` on the worker thread, or inline if unconfined or already on it.

        Example:
            ``self._run(lambda: target(*args))``
        """
        if self._worker is None or threading.get_ident() == self._worker_ident:
            return work()
        return self._worker.submit(work).result()

    def close(self) -> None:
        """Unload the library (on the thread that loaded it) and stop the worker.

        Safe to call repeatedly. Declarations are kept, so `open` can be called again.
        Unload errors are logged, never raised: closing must always finish.

        Example:
            Called by the station after the driver's ``close()``.
        """
        lib, self._lib = self._lib, None
        self._bound.clear()
        try:
            if lib is not None:
                try:
                    self._run(lambda: _free(lib))
                except Exception as exc:
                    self.log.warning("%s: unloading failed: %s", self.name, exc)
                self.log.debug("%s: unloaded", self.name)
        finally:
            self._shutdown()

    def _shutdown(self) -> None:
        """Stop the worker thread and remove the DLL search directories.

        Example:
            Called by `close`, and by `open` when loading fails.
        """
        if self._worker is not None:
            self._worker.shutdown(wait=True)
            self._worker = None
            self._worker_ident = None
        for handle in self._dll_dirs:
            handle.close()
        self._dll_dirs.clear()
