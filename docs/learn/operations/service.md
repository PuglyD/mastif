# Running a persistent station service

You've read [why you might want a station runtime](../system-design/execution-modes.md). This chapter is about the practical side: once you've decided to run one, what does it mean to operate it? A long-lived process that holds real hardware is a different kind of thing to look after from a script that starts and stops.

!!! example "Design preview"
    The station runtime doesn't exist yet, so nothing on this page can be run. We've written it to work out what operating one should be like, before anyone builds it. See the [roadmap](../../wiki/roadmap.md).

## What you're taking on

Let's be clear about the trade first. In direct mode, a crash ends everything, and the next run starts cleanly. With a runtime, you've gained shared access, a live view and faster starts. In exchange, you now have:

- A process to install, start, monitor and upgrade.
- State that outlives any one run, and that can be wrong.
- Clients and a server that need compatible versions.
- A new failure mode: the service is up, and the bench isn't.

Those are real costs, which is why this is opt-in. If you don't need what it offers, then direct mode is the better choice.

## Starting up

<!-- termynal: {title: "Mock of the intended experience · starting a station"} -->
```console
$ mastif station up profiles/bench-01.yaml
Station bench-01   mastif 0.4.0, demo-sdk 2.1.3
  ✓ Profile valid, drivers found
  Opening
    bench_supply  ✓ identity A123  ✓ health
    bench_meter   ✓ identity M77   ✓ health
    old_analyser  ✓ identity S12   ✓ health   (32-bit host process)
  Monitors: chamber_temp every 5 s
  Listening on tcp://127.0.0.1:7410
Ready.
```

It's the same sequence as anywhere else: load, validate, open with identity and health checks. If it can't validate, then it doesn't start. Failing to come up with a clear message is much better than coming up in a confusing partial state.

An organisation will generally want this run by the operating system's service manager, such as systemd or a Windows service. mastif runs in the foreground and logs to its usual places, which suits any of them.

### Up isn't the same as ready

Here's a distinction your monitoring needs to make, and it's the most common confusion with services of this kind. The process being up says very little about the bench. So a status report has to keep them apart:

<!-- termynal: {title: "Mock of the intended experience · station status"} -->
```console
$ mastif station status bench-01
Service     up 3 d 04:12    mastif 0.4.0
Station     degraded
  bench_supply  ready       leased by run 20261031T0900
  bench_meter   ready       leased by run 20261031T0900
  old_analyser  FAULTED     host process crashed at 08:41; restart with: mastif station restart-resource
Monitors    chamber_temp  24.8 °C  (2.1 s ago)
Last cleanup  complete
```

Each resource is one of `opening`, `ready`, `faulted` or `closed`, and the station's overall status follows from them. "Degraded" is a useful state to have. A faulted analyser shouldn't stop an unrelated run which only needs the supply.

## Stopping

Intentional shutdown follows a defined sequence, the same way a run does:

1. **Stop accepting new work.** New lease requests are refused.
2. **Deal with what's active.** Either wait for it, or abort it, depending on what was asked for.
3. **Make everything safe**, and close it, using the usual [lifecycle](../../getting-started/tutorial/deploying/lifecycle.md).
4. **Report what didn't work.**

<!-- termynal: {title: "Mock of the intended experience · stopping a station"} -->
```console
$ mastif station down bench-01
Run 20261031T0900 is holding supply, meter, dut.
  Waiting for it to finish (use --abort to stop it now)...
```

A crash is a different matter. A crashed process can't perform that sequence, so instruments stay in their last state. That means **on the next start-up, the runtime mustn't assume anything about the state of the hardware**. It can't know whether the last shutdown was clean. So it should treat a start-up as if there's a possibility that outputs are on: open each resource, make it safe, and only then report that it's ready.

## Upgrades

A station with a long-lived process needs a real upgrade plan, as code and clients won't change at the same moment.

**Client and server have to agree.** When a client connects, there's a version handshake. An incompatible client gets a clear refusal, rather than undefined behaviour halfway through a run.

**Don't upgrade in the middle of a run.** `mastif station down` waits for the current run by default. A station's maintenance window is a real thing to plan for.

**Remember what's in memory.** Installing a new SDK wheel changes nothing until the runtime restarts, and drivers stay loaded until then. `mastif station status` reports the versions actually running, not those that are installed.

## Security

The moment a process accepts commands over a socket, you have to think about who can talk to it. Something that accepts network commands to switch a supply on is a real concern, and "it's only on the lab network" isn't much of an answer.

Our planned default is to **listen only on localhost**, which means it's only reachable from the machine itself. Going beyond that is a decision you should make deliberately, with authentication and encryption, so it isn't something you drift into. The details will be set out in the runtime's ADR, and we'd rather start with a conservative position.

## Diagnosing a stuck station

Because the runtime is long-lived, its failure modes are the kind that show up as "it's been weird since yesterday". Here's what to check first.

| Symptom | Check | Likely cause |
|---|---|---|
| A client says `LeaseConflict` | Who holds it, in `status` | A run, or a forgotten manual session |
| A lease never gets released | The holder's heartbeat | A client that's stuck, but still alive |
| A resource is `faulted` | The resource's log | A vendor library crashed, or the device went away |
| Everything's slow | Active monitors and bus usage | A monitor interval that's too aggressive |
| Displayed values are old | The age next to the values | A worker that's stuck on a blocking call |

Each of these should be obvious from `mastif station status`. If you find yourself having to read logs to work out who holds a lease, then that's a shortcoming in the tool.

??? question "Still open in this design"
    Here's what we still have to decide, and we'd value your thoughts. Should hardware open at start-up, or on first use? Opening early means that problems show up early, and that the first run is fast. Opening late means that a broken instrument doesn't stop a station from starting. We're leaning towards opening early, with resources that fail staying `faulted` rather than stopping the service. Also open are the IPC technology, and the authentication story beyond localhost.

## Recap

- A runtime brings real **operating costs**, which is why it's opt-in.
- **Up isn't the same as ready.** Report the service's health and each resource's status separately.
- Shutdown is a **defined sequence**. After a crash, a new start-up must **assume nothing** about the hardware.
- Plan for **version handshakes** and maintenance windows.
- **Listen only on localhost** by default.

A runtime usually exists for one main reason: so that someone can look at a bench while a test is running. Let's think about how that should work.

**Next:** [Connecting an operator interface](operator-ui.md)
