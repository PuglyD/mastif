# How to learn mastif

You can read these docs in order, like a short book, and each chapter is also written to stand on its own, so that you can come back later with a specific question. Here's how they're arranged, and what to expect from them.

You don't need a bench. Most of the tutorial runs on a laptop.

## How we teach

We teach from first principles. Almost every chapter starts with a real situation: a cable falls out mid-run, a replacement supply arrives on a different port, a current reading comes back without a unit. From there we work out what the software has to do about it, and only then do we name the mastif class that does it.

We do it this way because a framework's abstractions look arbitrary until you've felt the problem they solve. If you understand why `Station.build` refuses to touch hardware, you can predict how the rest of the system behaves, and you'll know when a rule doesn't apply to your situation.

Three habits repeat throughout:

- **We run things.** Examples are complete enough to run, and we show you the output.
- **We follow failures as carefully as successes.** A test system earns its keep on the day something goes wrong, so we spend real time on those days.
- **We say what is guaranteed.** Software can attempt to turn an output off. It can't promise the output is off if the cable is gone. We try to be exact about that difference everywhere.

## Telling what's real from what's planned

mastif is being built in layers, from the bottom up, and this course deliberately crosses the line between what's built and what's designed. [What exists today](../../learn/status.md) shows where that line is.

Pages about working code open with this notice:

!!! success "Works today"
    Everything on this page runs against the current code.

Pages about the engine or runtime open with this one:

!!! example "Design preview"
    This page describes how mastif is intended to work. The code shows the interface we're designing, and it won't run yet.

We write those pages in the present tense, as if the engine already existed, because that's the honest way to find out whether a design reads well. Terminal recordings follow the same rule: the title bar of each one says whether it's a real transcript or a mock of the intended experience.

## Getting Started and Learn

The docs have two main parts, and they answer different questions.

**Getting Started** is about doing. It takes you from nothing to tests running on a station.

**Learn** is about understanding. It explains the concepts, the system design, the architecture as built, and how to operate a station.

You don't have to finish one before starting the other. Plenty of people will want to run something first and read about it later, and others will want the reasoning up front.

**Next:** [The route through the course](route.md)
