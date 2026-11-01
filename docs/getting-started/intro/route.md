# The route through the course

Here's the whole journey, so that you can see what's ahead and pick your own way through.

## Getting Started: build your first tests and deploy them

The tutorial follows one test for one fictional product, a *widget board* that must draw no more than 250 mA while idle.

**[Installation](../tutorial/installation.md)** gets a working environment onto your machine.

**[Writing tests](../tutorial/writing-tests/first-run.md)** starts with a complete test, then builds it up: a reusable structure, parameters, requesting instruments, combining tests into a plan and packaging them. It ends with [outcomes](../tutorial/writing-tests/measurements.md): measurements, limits and verdicts, and what failure really means.

**[First results](../tutorial/first-results/results.md)** looks at what a run leaves behind, and how it survives a crash.

**[Build your own hardware integration](../tutorial/hardware-integration/first-driver.md)** moves to the other side of the contract: drivers, DUT types, testing without hardware, and packaging an SDK.

**[Running and deploying on a station PC](../tutorial/deploying/profiles.md)** describes a real bench, connects real hardware, and installs everything on it.

## Learn: understand how it works

**[Framework fundamental concepts](../../learn/fundamentals/index.md)** gives you the map, and the general ideas mastif relies on.

**[System design](../../learn/system-design/concepts.md)** covers the specification, the design of the whole system, and how a run behaves inside a station. If you're evaluating mastif, this is the section to read closely.

**[Architecture as built](../../learn/architecture/index.md)** describes the code that exists today, package by package.

**[What exists today](../../learn/status.md)** says exactly what's implemented and what's designed.

**[Operate a station](../../learn/operations/bootstrap.md)** and the **[recipes](../../learn/recipes/scpi.md)** are for when you need something specific.

## If you only have ten minutes

Read [What mastif wants to solve](problem.md) and [Your first test run](../tutorial/writing-tests/first-run.md). That's enough to decide whether this way of thinking suits you.

**Next:** [Installation and your development environment](../tutorial/installation.md)
