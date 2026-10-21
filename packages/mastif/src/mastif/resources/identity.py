"""Who a resource is (`Identity`) and how it is doing (`Health`).

Why this exists:
    Traceability and safety both start with knowing exactly what is connected. Every
    result should be traceable to the serial numbers of the instruments and the unit
    that produced it. A station must also refuse to run if the wrong device is
    plugged in. `Identity` is the common answer to "who are you?" for instruments and
    DUTs alike. `Health` is the common answer to "are you fit to be used right now?".

Where it fits:
    Drivers optionally implement ``identify() -> Identity`` and ``health() -> Health``.
    When the station opens resources, it compares the identity against the profile's
    ``expect:`` block (see `Identity.mismatches`) and refuses unhealthy resources. The
    engine records identities in the run manifest.
"""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

type Reading = float | int | str | bool


class Identity(BaseModel):
    """What a resource reports about itself: vendor, model, serial, revision.

    Every field is optional, because devices differ in what they can tell you. Put
    anything else useful (part number, MAC address, calibration due date) in ``extra``.

    Attributes:
        vendor: Manufacturer, e.g. ``"ACME"``.
        model: Model name or number.
        serial: Serial number; the field most profiles check.
        revision: Firmware or hardware revision.
        extra: Any other identifying facts, as text.

    Example:
        >>> idn = Identity(vendor="ACME", model="PSU-X", serial="A123", revision="1.4")
        >>> idn.mismatches({"serial": "A123"})
        {}
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    vendor: str | None = None
    model: str | None = None
    serial: str | None = None
    revision: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)

    def get(self, field: str) -> str | None:
        """Return a field by name, looking in ``extra`` for non-standard names.

        This lets a station profile's ``expect:`` block check any identifying fact with
        the same syntax: ``{serial: A123}`` or ``{part_number: 900-0042}``.

        Args:
            field: A standard field name or a key in ``extra``.

        Returns:
            The value, or ``None`` if the resource did not report it.

        Example:
            >>> Identity(serial="A123", extra={"part_number": "900-0042"}).get("part_number")
            '900-0042'
        """
        if field in {"vendor", "model", "serial", "revision"}:
            return getattr(self, field)
        return self.extra.get(field)

    def mismatches(self, expected: Mapping[str, object]) -> dict[str, tuple[str, str | None]]:
        """Compare against expected values and return every field that differs.

        Comparison is exact, after converting expected values to text. A field the
        resource did not report counts as a mismatch, because "unknown" isn't proof it's
        the right device.

        Args:
            expected: Field name to required value, e.g. from a profile's ``expect:``.
                Values are compared as text, so a serial YAML parsed as a number still
                matches.

        Returns:
            ``{field: (expected, actual)}`` for every mismatch; empty if all match.

        Example:
            >>> Identity(serial="B999").mismatches({"serial": "A123", "model": "PSU-X"})
            {'serial': ('A123', 'B999'), 'model': ('PSU-X', None)}
        """
        out: dict[str, tuple[str, str | None]] = {}
        for field, want in expected.items():
            actual = self.get(field)
            if actual != str(want):
                out[field] = (str(want), actual)
        return out


class Health(BaseModel):
    """Whether a resource is fit for use right now, with optional supporting readings.

    Return ``ok=False`` with a ``detail`` when the device reports a fault, is not
    warmed up, or is out of calibration. Readings such as internal temperature are
    recorded alongside, so they are available when investigating a failed run.

    Attributes:
        ok: True if the resource may be used.
        detail: Explanation, mainly when not ok.
        readings: Diagnostic readings, e.g. ``{"temperature_c": 41.5}``.

    Example:
        >>> Health(ok=False, detail="over-temperature", readings={"temperature_c": 82.0}).ok
        False
        >>> Health.good().ok
        True
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    detail: str = ""
    readings: dict[str, Reading] = Field(default_factory=dict)

    @classmethod
    def good(cls, **readings: Reading) -> "Health":
        """Shortcut for a healthy result, optionally with readings.

        Args:
            **readings: Diagnostic readings to record.

        Returns:
            A `Health` with ``ok=True``.

        Example:
            >>> Health.good(temperature_c=35.0).readings
            {'temperature_c': 35.0}
        """
        return cls(ok=True, readings=readings)
