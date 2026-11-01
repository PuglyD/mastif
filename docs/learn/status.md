# What exists today and what we are designing

mastif is being built in layers, from the bottom up, and these docs deliberately describe more than exists. That's so a design can be read and argued with before anyone spends time building it. But you should always be able to find out exactly where the line sits, and this page is where you do that.

## The layers

| Layer | What it gives you | State |
|---|---|---|
| **Kernel** | Units, limits, verdicts, results | Implemented |
| **Infra** | Settings, logging, version information | Implemented |
| **Resources** | Contracts, drivers, DUTs, transports | Implemented |
| **Station** | Profiles, roles, the resource lifecycle | Implemented |
| **Testing kit** | Fake I/O and conformance checks | Implemented |
| **Engine** | Tasks, plans, loops, run records, resume | Designed |
| **Runtime** | One process owning the bench for many clients | Designed |
| **API and CLI** | The stable surface applications build on | Designed |

**Implemented** means that it runs and it's tested. **Designed** means it's described in these docs or the ADRs so it can be reviewed, but it won't run; individual previews identify unresolved decisions. Organisational deployment, identity services and shared recordkeeping sit outside this framework status table.

## What you can do today

- Write drivers and DUT types, for instruments over TCP, serial, VISA, UDP, Telnet or SSH, or through vendor libraries.
- Describe a bench in a validated profile, and check it with no hardware attached.
- Open, verify, make safe and close a station, with careful handling of failures.
- Record measurements, checks and tables with computed verdicts.
- Test all of that without hardware, using fakes and conformance checks.

You do this from your own Python application, which does by hand what the engine will do for you.

## What you can't do yet

- Write `Task` classes, or run plans. The `mastif` command doesn't exist.
- Resume a run after a crash, or get a run folder.
- Share a bench between a test and a GUI.

## Against the specification

For a requirement-by-requirement view, see [Where mastif stands](system-design/specification.md#where-mastif-stands), and for what comes next, see the [roadmap](../wiki/roadmap.md).

## Recap

The device layer, station lifecycle and evidence model are built and usable. The engine, API and CLI, and the optional persistent runtime are the planned layers above them.

**Next:** [Application settings and bootstrap](operations/bootstrap.md)
