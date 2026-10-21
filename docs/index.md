# mastif

**mastif** is a domain-neutral framework for **automated test equipment (ATE)**: the
software that drives power supplies, signal generators, switches and the device under
test (DUT), runs test plans, and records trustworthy results.

It has two parts:

- **The core.** A test execution engine (planned), primitives for instruments and
  DUTs, and the vocabulary of results.
- **A generic API.** A stable Python API, plus a network service (planned).

Organisations build their own **SDK** on top: their contracts, drivers, DUT types and
test packages. They also attach their own **UI**. mastif contains nothing specific to
any one company or product.

## How to read this wiki

| If you want to… | Read |
|---|---|
| Get oriented on your first day | [Start here](wiki/start-here.md) |
| See the whole system at once | [Architecture](wiki/architecture.md) |
| Follow one run from profile to results | [Life of a station](wiki/life-of-a-station.md) |
| Look up a term | [Glossary](wiki/glossary.md) |
| Understand an exception | [Error map](wiki/errors.md) |
| Write a driver, DUT type or station profile | [Guides](wiki/guides/write-a-driver.md) |
| Know *why* something is the way it is | [Decisions (ADRs)](adr/index.md) |
| Look up a function's signature | [API reference](reference/kernel.md) |

## Status

The kernel, the resources layer, the station layer and the testing kit are built and
tested. The engine is the next step. See the [roadmap](wiki/roadmap.md).
