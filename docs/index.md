# mastif

A domain-neutral framework for automated test equipment (ATE).

mastif provides two things:

- **Core**: the test execution engine, the instrument and DUT primitives, results and events.
- **API**: a stable Python API, plus an optional network service built on it.

Organisations write their own **SDK** on top of mastif and attach their own **UI**. An SDK contains:

- contracts
- drivers
- DUT types
- loop types
- test packages
