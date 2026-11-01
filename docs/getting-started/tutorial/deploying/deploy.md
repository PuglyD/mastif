# Running and deploying on a station PC

You've written tests, packaged them, written a driver, described a bench and watched it open and close. The last step is to put all of it onto the PC that runs that bench, in a way you could repeat on the next one.

!!! example "Part implemented, part preview"
    Building and installing wheels works today. The `mastif` commands are a design preview.

## Shipping to a station

Here's where it all comes together. A test package is a normal Python wheel, so a station's installation can be a normal, versioned, repeatable thing.

```console
uv build
```

<!-- termynal: {title: "Mock of the intended experience · deploying to a station"} -->
```console
$ uv pip install widget_tests-1.7.0-py3-none-any.whl
$ mastif validate widget-acceptance --station /etc/mastif/stations/bench-01.yaml
  ✓ All 16 items are valid on bench-01
$ mastif run widget-acceptance --station /etc/mastif/stations/bench-01.yaml --unit SN-42
```

Think about what this replaces: a folder of scripts copied onto a PC by hand, modified on site, and differing slightly from every other PC. With wheels, a station is running one identifiable version of everything, and
every run records exactly which ones. Updating means installing a new version. Rolling back means installing the old one.

Note that the profile lives *outside* the wheel, on the station. It's a fact about that machine, so it isn't something you'd ship with the code.


## Testing at each level

We've met several kinds of test along the way. Together they form a pyramid, with each level answering a question the others can't.

| Level | Tool | Needs | Answers |
|---|---|---|---|
| Pure logic | pytest | Nothing | Are my calculations and decisions right? |
| Driver protocol | [Fake I/O](../hardware-integration/fake-io.md) | Nothing | Does my driver send and parse the right things? |
| Driver shape | [Conformance](../hardware-integration/conformance.md) | Nothing | Does it honour the contract and the lifecycle? |
| Plan structure | `mastif plan` with golden files | Nothing | Will it run in the order I intended? |
| Task logic | A [simulated station](simulation.md) | Nothing | Does my test pass and fail when it should? |
| Station setup | `mastif validate` | The profile | Does this plan fit this bench? |
| Physics | A real bench | A real bench | Does it actually work? |

Look at how many of those rows need nothing but a laptop. That's the payoff for all of the separation we've been building. Your CI can catch nearly everything, and your scarce bench time gets used for the only question that
truly needs a bench.


## You've finished the tutorial

Let's take a moment to look back at where we began: ten lines of Python, opening a socket. Here's where we've ended up, for the same question.

- It runs on any bench, and on a laptop, with no changes to the test.
- A value can't lose its unit, and a verdict can't contradict its evidence.
- A wrong instrument is caught before it's used, and most setup mistakes are caught before anything's switched on.
- A failure in the unit can't be confused with a failure in the bench.
- The hardware's cleanup is attempted, in order, whatever happens, and you're told the truth about how it went.
- The sequence can be reordered with one line, and you can read what's going to happen before it does.
- A crash doesn't cost you the run, and in two years' time you can still say exactly what was tested, with what.

That's a lot more machinery than ten lines, and you should be asking whether it's worth it. For one board on one bench, it isn't, and that script is fine. It starts to be worth it about the time the second bench arrives.


## Where to go next

You've reached the end of the tutorial. To understand how all of this works, and why, continue with [Learn](../../../learn/index.md). If you're responsible for keeping stations running, go to [Operate a station](../../../learn/operations/bootstrap.md).

**Next:** [Learn](../../../learn/index.md)
