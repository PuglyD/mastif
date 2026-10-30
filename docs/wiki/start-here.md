# Start here

You know Python and want to understand how mastif helps build a test system.
You do not need prior experience with automated test equipment or access to a bench.

## Start with the problem

Suppose a device must draw no more than 250 mA while idle. A test system needs to:

1. Ask an instrument for a current reading.
2. Retain the unit so that amperes and milliamperes are compared correctly.
3. Compare the reading with the product's acceptance limit.
4. Record the evidence and its verdict.
5. Handle hardware setup, faults, and shutdown around that work.

These are separate responsibilities. The **kernel** handles units and evaluation.
**Resources** describe hardware capabilities and communication. A **station** connects
those resources into a particular bench. The planned **engine** will coordinate test
execution on top of them.

## Choose your path

| Your goal | Start with | Then read |
|---|---|---|
| See the framework as a whole | [Guided walkthrough](walkthrough.md) | [System architecture](architecture.md) |
| Run a small example | [Your first measurement](first-measurement.md) | [Kernel concepts](kernel.md) |
| Integrate an instrument | [Resource concepts](resources.md) | [Write a driver](guides/write-a-driver.md) |
| Connect a bench | [Station concepts](station.md) | [Write a station profile](guides/write-a-station-profile.md) |

## A few terms you will encounter

- **Device under test (DUT):** the item whose behaviour you are checking.
- **Instrument:** equipment used to stimulate or measure that item.
- **Contract:** a Python interface describing a capability, independent of device model.
- **Driver:** the device-specific implementation of that interface.
- **Role:** the name a test uses to request a capability, such as `psu_main`.
- **Profile:** configuration describing the resources and role mappings on a bench.

The [glossary](glossary.md) is the reference for the wider vocabulary.

## What to expect from the examples

Examples use fictional `acme` and `demo` organisations. The first tutorial uses a
fixed simulated reading; it does not access hardware. Later guides explain which
parts must be supplied by your own SDK (software development kit).

Terminal demonstrations are recorded command/output sequences, not live Python
sessions. Copy the accompanying code to run it yourself.

You can learn the public concepts without learning the repository's contribution
workflow. When you are ready to change mastif itself, see
[Working on mastif](working-on-mastif.md).

**Next:** [Create your first measurement](first-measurement.md).
