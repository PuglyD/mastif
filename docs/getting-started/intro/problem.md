# What mastif wants to solve

Let's start with how test software usually comes to exist, because mastif is a response to that story.

## Every test system starts as a script

Someone needs to know whether a new board draws the right current. They connect a
power supply, open a socket, and write ten lines of Python:

```python title="the script everyone has written — not mastif"
import socket

psu = socket.create_connection(("10.0.0.5", 5025))
psu.sendall(b"VOLT 5.0\n")
psu.sendall(b"OUTP ON\n")
psu.sendall(b"MEAS:CURR?\n")
current = float(psu.recv(64))
print("PASS" if current < 0.25 else "FAIL")
psu.sendall(b"OUTP OFF\n")
```

There's nothing wrong with this script. It answers the question, and it took five
minutes. If you only ever had one board and one bench, you could stop reading here.

But look at what happens next.

**The supply gets replaced.** The new model uses different commands, and the address
changes. Both are written directly into the test, so the test has to change even
though the question it asks hasn't.

**A second bench appears.** Somebody copies the file and edits the IP address. There
are now two versions of the test, and a bug fixed in one stays in the other.

**A reading comes back wrong.** `recv` returns `b"9.9E37\n"`, the value many
instruments use to mean "overrange". The script parses it happily, and now you have
a very large current and a plain FAIL, for a board that might be perfectly fine.

**The instrument doesn't answer.** The script raises an exception on the `recv` line.
It never reaches `OUTP OFF`, so the supply stays on, powering a board nobody is
watching, until someone notices.

**A customer asks a question.** "Which unit was this, tested on which instrument,
against which limit, with which version of the software?" The script printed `PASS`
to a terminal that has since been closed.

**The sequence grows.** Now it's every test, at each of three voltages, on each of
two firmware configurations. Changing the order means editing nested loops. A crash
four hours in means starting again from the beginning, because nothing recorded how
far it got.

None of these are exotic. Every organisation that tests hardware hits all of them,
and each one gets solved locally. Over a few years that produces a familiar landscape:
one codebase per station, drivers copied between projects and slowly diverging,
configuration that only one person understands, and results scattered through text
files. The tools work, one at a time. The system as a whole doesn't scale, and it
gets harder to change every year.

## Every station becomes an island

It's worth naming the mental model behind that landscape, since nobody chooses it deliberately. We call it the **local paradigm**: each station is treated as its own isolated system, and software is written for the machine in front of you.

It's a perfectly reasonable way to start. You get something working quickly, and for one bench it's the right trade. But look at how it plays out over time:

- Each chamber has its own motion code, even though the hardware behaves the same.
- Several configuration files describe the same flow, and they're rarely in sync.
- Projects meant to configure a product identically end up using different modes.
- Software is installed by hand, by whoever owns that station, and it's updated by copying source files.
- A fix goes into the local script, and it stays there. The next station still has the bug.

Different setups, different behaviours and different assumptions, even when the job's identical. Every station becomes its own island.

## Why that fails at scale

The local paradigm works with a few stations, a small product line, and a handful of people who know everything. Growth changes the rules, because the costs compound. Four failure modes show up, in roughly this order.

**Coordination cost explodes.** Every change has to be aligned across people, environments and timelines. Instead of scaling output, the organisation scales friction.

**Copy and paste becomes the default form of reuse.** Teams don't share capabilities, they replicate them. "The same" system exists in several slightly different versions, and improvements don't spread.

**Manual work creates inconsistency.** Each environment gathers small differences in setup and configuration. Together those make reliability impossible to guarantee, and troubleshooting far more expensive than the original change.

**There are no feedback loops.** Without shared logging, metrics or reporting, failures are only visible locally, and so are improvements. The organisation can't see its systemic problems, so it stays reactive.

There's a human side as well. It's common for a test software foundation to have been built largely by one capable engineer, and for everyone else to have extended it, because it worked and there was nothing better. That isn't a criticism of the original work, since it was never designed to be a platform. But the result is real risk: critical knowledge lives in someone's head, the system evolves by patching rather than design, and each new project inherits the same constraints. A shared foundation has to be able to outlive any one engineer. That's a large part of why this project cares so much about its documentation.

These problems tend to hit at a bad moment too: as production grows, with more stations, more products and more sites. Each new station becomes another isolated environment, and each new product another codebase, so the gap between what's being asked for and what the software can support keeps on widening.

## How other fields solved this

This problem isn't unique to test equipment. Datacentres went through the same transition.

A modern datacentre isn't a collection of carefully hand-tended servers. It's a shared platform: compute is pooled, services are deployed consistently, everything is centrally monitored, and you scale by adding resources rather than rewriting software. The same model applies here. Instead of treating each test station as its own mini-system, you build a shared foundation that applications are deployed onto, once, and reuse everywhere.

We're not suggesting that a test bench is a web server. A station has physical hardware, device connections can fail, and a mistake can damage real equipment, all of which shapes [the design](../../learn/system-design/specification.md) a great deal. But the principle carries over: shared foundations, standard execution, observable behaviour, and consistent delivery.

| | The local paradigm | A shared foundation |
|---|---|---|
| **Structure** | No defined architecture; logic tightly coupled | Layered, with enforced boundaries |
| **Flexibility** | Hardcoded flows; changes need invasive edits | Parameter-driven behaviour, reusable workflows |
| **Reuse** | Forks tailored to specific fixes | A versioned SDK of shared components |
| **Delivery** | Copying files by hand | Versioned packages and repeatable rollout |
| **Evidence** | Flat text files | Structured results, queryable and auditable |
| **Knowledge** | In someone's head | In documentation that's kept with the code |
| **Operators** | Cluttered tools that expose internals | Interfaces designed around the workflow |

### Lessons from earlier attempts

Organisations have tried to fix this before, and often got a lot right. Efforts to model the test domain properly, with abstractions for instruments, stations and flows, have frequently produced sound models, and they've still failed to be adopted. In our experience that's rarely because of the modelling. It's the gap around it: no shared infrastructure, no deployment story, no documentation, and no path for the next engineer. mastif tries to build on those lessons, reusing what's proven and addressing what was missing.

## The problems are always the same ones

Here's the observation that mastif is built on. The products under test are completely
different from one company to the next, but the *problems above* are not.

Every station has to answer the same questions:

- Who is connected, and is it really the device I expected?
- What does this number mean, and in what unit?
- Did this reading meet the requirement, and can I prove it later?
- What happens to the hardware when something goes wrong?
- Which test runs next, at which conditions, and how do I carry on after a crash?
- How do a test and an operator's screen share the same instrument?

Those questions have nothing to do with your product. They can be answered once, well,
in one framework. What genuinely is specific to your organisation (what your product
does, which instruments you own, what counts as a pass, what your operators need to
see) stays yours.

That is the split at the centre of mastif:

| mastif provides | Your organisation provides |
|---|---|
| Quantities, limits, verdicts, results | Your product's acceptance criteria |
| Contracts, transports, the driver model | Drivers for the instruments you own |
| Station composition and hardware lifecycle | Bench profiles for your stations |
| A test engine: tasks, plans, loops, run records | Your test packages and loop types |
| A runtime and API for sharing a station | Your user interface |

Together, your drivers, DUT types and loop types form your **SDK**. mastif is the
foundation you build that SDK on, and it never imports your code by name. A different
organisation with a different product can build on the same foundation without
inheriting anything from yours.

## Recap

Test software stops scaling for reasons that have little to do with any one product. The questions it has to answer are the same everywhere, so they can be answered once, in a shared foundation, leaving your product knowledge in an SDK you own.

So why this foundation, in particular?

**Next:** [Why mastif?](why-mastif.md)
