"""The root of mastif's exception hierarchy, and the kernel's own errors.

Why this exists:
    In test equipment the difference between "the device failed" and "the test broke"
    matters: the first is a FAIL verdict, the second an ERROR. Typed exceptions let the
    engine, drivers and org code tell these apart reliably. Every error mastif raises
    derives from `MastifError`, so ``except MastifError`` catches exactly mastif's own
    failures and nothing else.

Where it fits:
    Each layer adds its own subclasses. For example, the resources layer adds transport
    and identity errors. The engine turns uncaught exceptions inside a task into an
    ERROR verdict and never swallows them.

Design note:
    mastif errors deliberately don't subclass `ValueError`. Pydantic wraps any
    `ValueError` raised in a validator into a generic ``ValidationError``. Keeping them
    separate means a `LimitsError` or `UnitError` reaches the caller as itself.
"""


class MastifError(Exception):
    """Base class for every error raised by mastif.

    Catch this at a boundary (CLI, service, org tooling) to handle all mastif failures
    in one place.

    Example:
        >>> try:
        ...     raise UnitError("cannot convert 'V' to 'A'")
        ... except MastifError as exc:
        ...     print(type(exc).__name__, exc)
        UnitError cannot convert 'V' to 'A'
    """


class UnitError(MastifError):
    """A value was combined with or compared to a value of an incompatible unit.

    This almost always means a mistake in test or driver code, such as comparing volts
    with amps or adding two dBm levels, so mastif fails loudly instead of guessing.

    Example:
        >>> from mastif.kernel.units import V, A
        >>> (1 * V).to("A")
        Traceback (most recent call last):
        ...
        mastif.kernel.errors.UnitError: cannot convert 'V' to 'A'
    """


class LimitsError(MastifError):
    """Limits or a table are malformed, or no limits exist for a requested index.

    Raised when the limits are built, so specification mistakes surface before any
    hardware is touched.

    Example:
        >>> from mastif.kernel.limits import Range
        >>> Range()
        Traceback (most recent call last):
        ...
        mastif.kernel.errors.LimitsError: a range needs at least one bound
    """
