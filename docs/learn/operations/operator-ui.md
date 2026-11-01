# Connecting an operator interface

mastif doesn't ship a user interface, and that's on purpose. Operators at different organisations need very different things, so your UI should be designed around your people and your product. What mastif owes you is a foundation that makes a good UI possible: one that tells the truth, even when the news is bad.

This chapter is written for whoever builds that UI. The engineering here isn't really about widgets. It's about how to avoid showing somebody something that isn't true.

!!! example "Design preview"
    The API layer and the runtime's event stream don't exist yet. This describes the behaviour we're designing for, and it isn't a catalogue of real endpoints.

## Why UIs go wrong at test stations

The usual problems with operator software aren't about how it looks. They're mostly about the state on screen disagreeing with the state of the bench.

A green light left over from before the connection dropped. A "Stop" button which changes colour immediately, while the test is still running. A reading that froze an hour ago, and looks exactly the same as a live one. Configuration exposed that no operator should ever change, resulting in errors at the worst possible moment.

Each of these is a case of a UI having its own opinion about what's going on. So here's the principle:

> **A UI doesn't decide what's true. It displays what the owner reports, and it says how old that information is.**

## What a UI can build on

Your UI talks to `mastif.api`, a stable layer that's designed for applications. Here's what it gets:

| Need | Source | Learn more |
|---|---|---|
| What's happening in the run | The event stream | [Progress](../../getting-started/tutorial/first-results/progress.md) |
| What the instruments are doing | Published state, with its age | [Events and state](../system-design/events-state.md) |
| Who's in control | Lease information | [Lifetimes](../system-design/resource-lifetimes.md) |
| Starting, pausing and stopping | Commands | [Run lifecycle](../system-design/run-lifecycle.md) |
| Asking the operator something | Prompts | [Cleanup](../../getting-started/tutorial/writing-tests/cleanup.md) |
| Looking at the past | Run folders | [Results](../../getting-started/tutorial/first-results/results.md) |

All event types are exported as JSON Schema with `mastif schema events`, so a UI written in TypeScript can generate its types from the source of truth, and it won't drift out of step.

## Observing and controlling are different

A dashboard can consume published state without holding a hardware-control lease. Changing the hardware needs a lease; access to the dashboard itself is an application policy. Your UI's design should reflect this difference clearly.

```text title="an operator's view — preview"
Station bench-01                                         ● ready
────────────────────────────────────────────────────────────────
Run  widget-acceptance   Unit SN-42                  ▶ running
     11 of 16 items      idle_current  (profile=std, voltage=5 V)

Supply  bench_supply                 In use by this run
  Setpoint   5.000 V
  Output     ON
  Current    180 mA    0.2 s ago
  [ Manual control ]  unavailable: run 20261031T0900 is in control

[ Pause ]  [ Stop ]
```

See how the unavailable control explains itself. Hiding the button would leave someone wondering. Showing an active button that fails when pressed would be worse. "Unavailable: this run is in control" tells them what they need to know, along with what's holding things up.

When there's no run, that same panel becomes live for manual control, once your UI has requested and been granted a lease.

## Showing a stop honestly

This is where UIs most often lie, because it's tempting to give instant feedback. When someone presses Stop, change the button to "Stopping", and show what's really going on:

```text title="preview: stopping, in stages"
■ Stopping — waiting for bench_meter (12 s)
■ Stopping — cleaning up idle_current
■ Stopping — leaving profile=std
■ Making the bench safe
■ Stopped. 11 of 16 items completed.
```

Each of those comes straight from the run's [explicit states](../system-design/run-lifecycle.md). That first line is particularly important. An operator looking at "waiting for bench_meter (12 s)" can decide whether to wait or go and turn something off. Somebody looking at a stuck spinner cannot.

Cleanup failures have to stay visible as well. If the output couldn't be disabled, that belongs on the screen in a way that's hard to miss, however well the measurement went:

```text title="preview: the case to design for"
● PASS   idle_current   180 mA

⚠ CLEANUP FAILED   bench_supply: could not switch output off
  Check the bench before touching the unit.
```

## Showing verdicts and decisions separately

If your application records a [disposition](../system-design/dispositions.md), such as sending a failed unit for rework, show it alongside the automated verdict. A later decision must not make the original measurement look as though it passed. This workflow belongs to your application; it isn't a mastif approval API.

## Handling a lost connection

A UI's connection to a station can drop. When that happens, everything on the screen becomes a claim about the past. So don't keep showing it as if it's live:

1. **Mark everything as stale**, right away and prominently.
2. **Keep the last-known values visible**, with their age. They're useful, as long as they're labelled.
3. **Disable the controls.** A command sent now won't reach anything.
4. **Reconnect with the same routine as at start-up**: subscribe, get a snapshot, then apply updates.
5. **Don't resend commands automatically.** If you sent a command and lost the connection, you don't know if it arrived. Ask the station what state it's in. Re-sending "start run" could start a second one, unless the request has an ID that the server recognises.

## Designing for operators

A few things specifically about the people using it, since production floor users aren't the same as the engineers who wrote the tests.

**Show only what they need.** Most operators don't need to see voltages, roles, or a driver's name. They need to know which unit to load, what to do next, and whether to pass it along or set it aside. Keep the engineering view available, but keep it behind a door.

**Put the verdict's meaning into words.** FAIL and ERROR need different actions. For an operator, "This unit failed: set it aside for review" and "The test couldn't complete: call a technician, and don't scrap this unit" are far more useful than two shades of red. That difference exists all the way through the framework, and it would be a shame to lose it on the very last screen.

**Make prompts unambiguous.** When a test asks a person something, they're part of the procedure, so it's worth wording these as carefully as you'd write any test step. Say what to look at, what the options mean, and what will happen next.

**Scan, don't type.** Wherever a serial number is involved, use a barcode. `station.open(expect={"dut": {"serial": scanned}})` then verifies it against the unit itself, so a typing error gets caught, and so does the wrong unit on the fixture.

## What belongs in your UI, and what doesn't

| In your UI | Not in your UI |
|---|---|
| Layout, language, branding | Pass or fail logic |
| Your organisation's workflow | Instrument commands |
| Which plan suits which product | Limits |
| Operator permissions | Its own record of what's connected |

If you find yourself computing a verdict in your UI, or sending a raw command, it's a sign that something belongs in a lower layer. Keeping this logic out means that a run gives the same result whichever interface started it.

## Recap

- **A UI displays what the owner reports**, and it shows how old that information is.
- **Observing published state doesn't take a control lease.** Unavailable controls should say why.
- **Show a stop in stages**, and keep cleanup failures impossible to miss.
- On a lost connection, **mark everything stale**, and don't automatically resend commands.
- **Keep FAIL and ERROR distinct** all the way to the operator, in plain words.

We've covered how things should work. Last in this section is what to do when they don't.

**Next:** [Troubleshooting startup and execution](troubleshooting.md)
