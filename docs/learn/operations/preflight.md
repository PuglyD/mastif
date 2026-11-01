# Preparing and validating a station

An operator arrives at a station in the morning. Before putting a unit on the fixture, they'd like to know: is this bench ready? Answering that with "try running something, and see" wastes time, and on a real bench it may waste a unit too.

The nice thing is that most of what could be wrong can be found without touching anything. Here, we'll work through checking a station in stages, from the cheapest checks to the most thorough.

!!! success "Works today"
    Building and role checks work today. `mastif validate`, which automates this for a whole plan, is a design preview.

## Three stages, three questions

| Stage | Question | Touches hardware? | Can run in CI? |
|---|---|---|---|
| **Build** | Is this configuration consistent? | No | Yes |
| **Open** | Is the bench what the configuration says it is? | Yes | No |
| **Smoke test** | Does it actually work? | Yes, and it may apply stimulus | No |

Run them in that order. Each one rules out a whole family of problems, so that when a later stage fails you know it can't be due to anything an earlier stage checked.

## Stage 1: build it

```python title="check_station.py — excerpt"
from mastif.resources.registry import Registry
from mastif.resources.std import PowerSupply, Shell
from mastif.station import Station, StationProfile

profile = StationProfile.load("profiles/bench-01.yaml")
station = Station.build(profile, Registry.discover())

problems = station.role_problems({"supply": PowerSupply, "console": Shell})
for problem in problems:
    print(problem)
```

This one checks a lot. Here's a list of what can be found at this stage:

- YAML syntax and the structure of the profile, with any unknown field rejected.
- Roles that point at resources which don't exist.
- Driver ids that aren't installed, listing what is.
- Driver configuration, including transport settings.
- DUT channels: all required ones mapped, none unknown, each providing its contract.
- Roles that don't provide what a test needs.

All of this needs nothing but the installed software and the file. So you should check it in **continuous integration**: for each station profile in your organisation, on each change to your SDK or your profiles. A driver's config change that would break bench 7 gets caught when someone submits it, not on a Monday morning.

## Stage 2: open it

Only a real connection can establish these things:

```python title="excerpt"
with station:
    for name, identity in station.identities().items():
        print(name, identity.serial)
```

| Checked at opening | What it finds |
|---|---|
| **Reachability** | Powered off, a wrong address, a missing extra |
| **Identity** | A swapped instrument, a moved cable |
| **Health** | A latched fault, a device not warmed up |
| **Discovery** | A child resource that isn't there |

Opening runs a driver's `open()`, so it's as safe as those hooks are, and that's why [we asked driver authors to keep them free of stimulus](../../getting-started/tutorial/hardware-integration/identity.md#why-its-checked-after-open). Leaving the `with` block runs safe state and closes everything.

Passing here tells you that the bench is what the profile claims it is, right now. It's not a promise about this afternoon.

### The serial of today's unit

Instruments are in the profile, but the unit under test changes constantly. Pass its scanned serial when opening, and the DUT must report that serial or the run stops:

```python title="excerpt"
station.open(expect={"dut": {"serial": scanned_serial}})
```

This catches something quite common on a production floor: a barcode scanned for one unit, with another one sitting on the fixture. Without it, a full set of results gets filed against the wrong serial number.

## Stage 3: smoke test

A short plan that uses each instrument at low risk can prove that it all works together: read a voltage with the output off, take one low-power reading. Keep it quick, and make it the first thing that runs in the morning.

```yaml title="plans/bench-check.yaml — preview"
name: bench-check
policies: {on_fail: continue, on_error: continue}
sequence:
  - task: instruments_respond
  - task: fixture_continuity
  - task: known_good_reference
```

That last task deserves a mention. If you keep a **golden unit** with known characteristics, a measurement on it tells you what no software check can: whether the whole bench still gives correct answers. It's the only one of these checks that says anything about accuracy.

## All in one command

With the engine, the first stage becomes a single command, with the plan included in the check:

<!-- termynal: {title: "Mock of the intended experience · validate"} -->
```console
$ mastif validate plans/widget-acceptance.yaml --station profiles/bench-01.yaml
Plan widget-acceptance (16 items)
  ✓ Plan structure and loop types
  ✓ Task configuration
  ✓ Roles: supply, meter, dut
  ✓ Context: every 'needs' has a producer
  · Not checked: positioner.azimuth (exists only after opening)
Nothing was opened. Ready to run.
```

Look at the "not checked" line. A check that quietly skipped something would give you false confidence. It's far better for it to say what it couldn't establish.

## Writing failures people can act on

If you build your own checking tool or UI on top of this, keep hold of what makes these messages useful. Each error says which resource and which field, and what would fix it. An operator should be able to tell the difference between these:

| Message | Who should act | What to do |
|---|---|---|
| `no driver 'acme.psu-x'; known: ...` | The deployer | Install the SDK |
| `invalid config: curent_ma` | The profile's author | Fix the typo |
| `TransportError: connection refused` | The technician | Check power and cable |
| `serial is 'B1', expected 'A1'` | The technician | Check which instrument is connected |
| `unhealthy: over-temperature` | The technician | Let it cool, and investigate |
| `role 'rf_source' not found` | The test author, or whoever chose this bench | This plan needs a different bench |

And a word of warning on the fourth row. When an identity check fails, the fix is *not* to delete `expect:` from the profile. That check just did its job, and the question it's asking is real: which is wrong, the bench or the file? If an instrument has been deliberately replaced, then update the profile, and make a note of it.

## What none of this proves

Being thorough here doesn't establish that every test will pass, or that an instrument can really do what's being asked of it. Whether a supply has the resolution for your limit, or whether a bench's wiring loss is within spec, comes from qualifying the bench, as a separate engineering activity. It's good to keep that record alongside the profile.

## Recap

- Check in **stages**: build (no hardware), open (reachability, identity, health), and then a smoke test.
- **Stage 1 belongs in CI**, for every profile.
- Pass today's **scanned serial** when opening, so results can't be filed against the wrong unit.
- A **golden unit** is the only check that says something about accuracy.
- **Don't remove `expect:` to silence a mismatch.** Find out which side is wrong.

Most organisations end up with lots of these profiles. Let's talk about how to manage them.

**Next:** [Managing environments and station profiles](environments.md)
