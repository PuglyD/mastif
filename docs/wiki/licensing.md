# Licensing

mastif is licensed under the **GNU Affero General Public License, version 3 or later**
(`AGPL-3.0-or-later`). The author also sells a **commercial licence** for use without
the AGPL's obligations. Offering both is called [dual licensing](glossary.md). The full
reasoning is in [ADR-0031](../adr/0031-licensing-and-dependency-policy.md). This page is
the short version. It is not legal advice.

## What you may do

| You... | Obligation |
|---|---|
| run mastif and your org SDK on your organisation's own stations | none |
| modify mastif for internal use | none |
| ship your SDK, or a station image containing mastif, to a contract manufacturer, customer or partner | give the recipients the full source (mastif and the SDK) under the AGPL, **or** buy a commercial licence |
| let outside users interact with a **modified** mastif over a network | offer them the modified source, **or** buy a commercial licence |
| sell a closed product built on mastif | needs a commercial licence |

The key words are *conveying* (giving a copy to someone else) and *remote network
interaction* (AGPL section 13). Using software privately is neither.

## Why AGPL plus a commercial licence

- It is OSI-approved open source, so company policies can allow it.
- Internal use is free, which is the most common ATE case.
- Nobody can take mastif closed, as a product or a hosted service, without paying.
- The author keeps a way to fund the project.

Licences that forbid "commercial use" were ruled out: they are not open source, and an
internal test station counts as commercial use. See ADR-0031, section 2.4.

## Contributions

External contributions are **not accepted** at the moment. Selling a commercial licence
requires the author to own all of the code. If contributions open later, they will need
a [CLA](glossary.md) (Contributor Licence Agreement).

## Dependencies

A library can only be used if its licence is compatible with the AGPL:

| Allowed | Not allowed |
|---|---|
| MIT, BSD, ISC, Apache-2.0, PSF | GPL-2.0-only |
| LGPL (e.g. paramiko), MPL-2.0 | SSPL, BSL, Elastic, Commons Clause |
| GPL-3.0, GPL-2.0-or-later, AGPL-3.0 | non-commercial licences, proprietary code, no licence |

Anything not listed needs an analysis in an ADR first. Vendor DLLs are never committed
or shipped: each station installs its own.

## Where the licence lives

- `LICENSE`: the official text, verbatim. Never edit it.
- `NOTICE`: copyright and the commercial offer.
- Each package's `pyproject.toml` declares `license = "AGPL-3.0-or-later"`, and every
  wheel carries both files under `*.dist-info/licenses/`. A test keeps the per-package
  copies identical to the root ones.
