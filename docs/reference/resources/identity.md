# Identity and health

**Module:** `mastif.resources.identity`

Drivers use these models to report **what is connected** and **whether their own
readiness checks passed**. The station resource manager consumes the reports during
bring-up. These models do not open connections or interrogate devices themselves.

| Type | Use it when |
|---|---|
| [`Identity`][mastif.resources.identity.Identity] | Returning manufacturer, model, serial, revision, or additional identifying fields |
| [`Health`][mastif.resources.identity.Health] | Returning a readiness decision with an explanation and diagnostic readings |
| [`Reading`][mastif.resources.identity.Reading] | Describing the scalar values accepted in health diagnostics |

## Example

```python
from mastif.resources.identity import Health, Identity

identity = Identity(vendor="ACME", model="PSU-X", serial="A123")
assert identity.mismatches({"serial": "A123"}) == {}
assert identity.mismatches({"serial": "B999"}) == {"serial": ("B999", "A123")}

health = Health.good(temperature_c=35.0)
assert health.ok
```

## Behaviour at the station boundary

- Identity fields are optional. A missing field fails a comparison when that field is expected.
- Expected values are converted to text and compared exactly, without case folding.
- `Identity.mismatches()` returns differences. The **manager** raises
  [`IdentityMismatch`][mastif.resources.errors.IdentityMismatch] when verification fails.
- A reported `Health(ok=False)` causes the manager to raise
  [`ResourceFault`][mastif.resources.errors.ResourceFault].
- A healthy report reflects the driver's checks at that moment; it does not establish
  continuous monitoring.

## Python API

::: mastif.resources.identity
    options:
      show_root_heading: false

## Related explanations and decisions

- [Resource concepts](../../wiki/resources.md#4-check-what-is-connected): why verification is needed.
- [ADR-0010](../../adr/0010-identity-and-health.md): the models and their invariants.
- [ADR-0022](../../adr/0022-resource-manager.md): when checks run and how failures propagate.
- [Write a driver](../../wiki/guides/write-a-driver.md): implement the reporting hooks.
