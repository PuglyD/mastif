# mastif

A domain-neutral framework for automated test equipment (ATE).

- **Core**: the test execution engine, the instrument and DUT primitives, results and events.
- **API**: a stable Python API, plus an optional network service built on it (planned).

Organisations write their own SDK on top of it (contracts, drivers, DUT types, loop types) and attach their own UI.

Status: early development. See `docs/plan.md` and `docs/adr/`.

```
uv sync
uv run pytest
```

## Licensing

mastif is free software, licensed under the
[GNU Affero General Public License v3.0 or later](LICENSE) (`AGPL-3.0-or-later`).
Copyright and the commercial offer are in [`NOTICE`](NOTICE).

What that means in practice (this is a summary, not legal advice):

- **Internal use is free.** Your organisation may run mastif, modify it and build its
  own SDK on it for its own stations, with no obligation to publish anything.
- **Sharing triggers the copyleft.** If you distribute mastif, a modified mastif, or
  software built on it (for example an org SDK shipped to a contract manufacturer or a
  customer), you must offer the recipients the complete source under the AGPL. If you
  let people outside your organisation use a modified mastif over a network, you must
  offer them its source too.
- **A commercial licence is available** from the author for use without the AGPL's
  obligations, e.g. to distribute a proprietary SDK or service built on mastif.
- **Outside contributions are not accepted yet**, so the author can keep offering the
  commercial licence. Bug reports and feedback are welcome.

The reasoning, and the rule for which dependencies mastif may use, are in
[ADR-0031](docs/adr/0031-licensing-and-dependency-policy.md).
