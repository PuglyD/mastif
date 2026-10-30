---
hide:
  - toc
---

# Test systems change. Your test logic shouldn't have to.

**mastif is a Python framework for automated test equipment (ATE): software that
connects instruments, exercises a device under test, and records the evidence.**
{ .mastif-lead }

A bench gets a new power supply. A product needs a different console protocol.
A test moves from a developer's laptop to a production station. Those changes should
not require rewriting how you express a measurement or decide whether it passes.

mastif separates **what a test needs**, **how hardware provides it**, and **which
devices are connected to this station**. Your organisation supplies its drivers,
product knowledge, test packages, and user interface.

[Take the guided walkthrough](wiki/walkthrough.md){ .md-button .md-button--primary }
[Try your first measurement](wiki/first-measurement.md){ .md-button }

## Explore mastif

<div class="grid cards" markdown>

-   **Learn by doing**

    Start with a simulated reading, give it units and limits, and inspect its verdict.
    No instruments or vendor software required.

    [Start learning](wiki/start-here.md)

-   **Understand the system**

    Follow the boundaries between a test, an organisation's SDK, and a physical station.

    [Explore the architecture](wiki/architecture.md)

-   **Build an integration**

    Describe a device's capabilities, write a driver, and connect it through a profile.

    [Write a driver](wiki/guides/write-a-driver.md)

-   **Find a precise answer**

    Look up Python signatures and types, or follow an architecture decision record
    (ADR) to its rationale and trade-offs.

    [API reference](reference/resources/identity.md) · [Design decisions](adr/index.md)

</div>

## One framework, organisation-specific systems

| mastif provides | Your organisation provides |
|---|---|
| Units, limits, results, and verdicts | Product acceptance criteria |
| Resource contracts and driver integration | Device drivers and additional capabilities |
| Station composition and lifecycle handling | Bench profiles and device-specific shutdown actions |
| Planned execution and API layers | Test packages, workflows, and user interfaces |

Read [the system overview](wiki/architecture.md) for the dependency rules and extension points.

!!! info "Current implementation and future design"
    This checkout includes the kernel, infrastructure, resources, station, and testing
    packages. Engine, runtime, and application API designs are future work and subject
    to revision. Architecture pages distinguish planned flows from executable examples.
    See the [project roadmap](wiki/roadmap.md).
