# Managing environments and station profiles

Your test code runs on a developer's laptop, on a qualification bench, and on twelve production stations at two sites. These all differ, and there's a temptation to deal with that through `if environment == "production":` branches in the code. We'd urge you not to go that way. Every such branch means that the code you tested isn't the code that's running.

The alternative is to treat the differences as **inputs**, and in this chapter we'll look at how to organise them.

!!! success "Works today"
    Profile selection, simulation and settings all work today. Recording the effective configuration in a run manifest is a design preview.

## Choose the right input for the difference

We've seen three kinds of configuration. Here's how to use them when deciding where a difference between environments belongs.

| What differs | Use | Example |
|---|---|---|
| The hardware on this bench | A **station profile** | `bench-01.yaml`, `bench-02.yaml` |
| No hardware at all | A profile with **simulators** | `sim.yaml` or `sim:` |
| How the software is deployed | **Settings** | Log directory, report path |
| The product's requirements | The **plan** or task config | Limits, sequence |

Let's look at what doesn't appear in that table: there's no "environment" that changes a product's limits. A unit should pass or fail in the same way wherever it's tested. If a limit differs between sites, that's a decision worth writing down in a plan, rather than something that happens because of which machine it's running on.

## One profile per bench

The simplest arrangement that works is one file per physical bench, under version control:

```text title="a profiles repository"
profiles/
├── sim.yaml                 # Runs anywhere; used by CI and laptops
├── site-a/
│   ├── bench-01.yaml
│   └── bench-02.yaml
└── site-b/
    └── bench-01.yaml
```

Treat these as you'd treat code. Each change gets reviewed. Their history tells you when an instrument was swapped, and by whom. And your CI builds every one of them against the current SDK.

Yes, this does mean some repetition: two benches with the same instruments have nearly identical files. We've deliberately not added includes or templates to the profile format. What you can read in one file, with no resolution steps, is what that bench actually is. When you're standing in front of a bench trying to work out what's going on, that matters more than saving a few lines. If you've got dozens of nearly identical stations, then generating these files with a small script of your own, and committing the output, gives you the best of both.

## Simulation

There are two ways to get a hardware-free station, and they suit different situations.

**A separate simulated profile** is simple and explicit. It's good for CI and for development, where there's no real bench in the picture at all.

**A `sim:` section in a real profile** gives you a simulated twin of one specific bench, with the same roles:

```yaml title="profiles/site-a/bench-01.yaml"
station: bench-01
resources:
  bench_supply:
    driver: acme.psu-x
    config:
      transport: {kind: tcp, host: 192.0.2.10, port: 5025}
    expect: {serial: A123}
roles:
  supply: bench_supply
sim:
  bench_supply:
    driver: demo.learn-supply
    config: {current_ma: 180}
    expect: {serial: SIM-001}
```

Remember the two rules from [the simulation chapter](../../getting-started/tutorial/deploying/simulation.md). A `sim:` entry **replaces** the whole resource, with nothing merged. And a resource **without** an entry **stays real**. So before you describe a run as hardware-free, have a look at what's really been selected:

```python
from mastif.station import StationProfile

profile = StationProfile.from_yaml("""
station: bench-01
resources:
  bench_supply: {driver: acme.psu-x}
  bench_meter: {driver: acme.dmm-1}
roles:
  supply: bench_supply
sim:
  bench_supply: {driver: demo.learn-supply}
""")

for name, entry in profile.entries(sim=True).items():
    print(name, entry.driver)
```

```text title="Real output"
bench_supply demo.learn-supply
bench_meter acme.dmm-1
```

The meter is still real. That may be precisely what you want, as a mixed station is a useful way of testing with one real instrument. It should be a deliberate choice, though.

## Settings per environment

Settings can vary per site by layering files, which we covered in [bootstrap](bootstrap.md). A typical arrangement is one base file shipped with your software, and a site file that's installed on each machine:

```text title="a site's configuration"
config/
├── 00-base.toml       # The same everywhere
└── 10-site.yaml       # What's specific to this site
```

Dynaconf also offers a `[production]` and `[development]` sections feature, enabled by `environments=True`. It's off by default, for a reason you should know about: once it's enabled, Dynaconf ignores every key outside those sections, which is an easy way to lose settings without noticing. We'd generally stick with layered files.

## Keeping what was actually used

Here's something that gets overlooked until the day it matters. Suppose you need to explain a result from eight months ago. Your profile file says that the supply's serial is A123. But is that what it said eight months ago? And was there an environment variable overriding something that day?

A file name isn't a record, since the file may have changed. **What you want is the effective configuration, as it was at the time.** So the engine records in each run's manifest the facts that were really used, not the names of the files they came from:

```json title="manifest.json — preview, abridged"
{
  "station": {
    "name": "bench-01",
    "profile_sha256": "9f2c1e...",
    "resources": {
      "bench_supply": {"driver": "acme.psu-x", "identity": {"serial": "A123", "revision": "1.4"}}
    }
  },
  "sim": false,
  "config": {"idle_current": {"voltage": "5 V", "max_current": "250 mA"}}
}
```

The hash tells you whether today's file is the same one, and the identities are what the instruments reported that day, not what the file expected.

Secrets need care here. A manifest must never contain a password. Fields that are declared as `SecretStr` are stored as placeholders, and you should treat any custom secret in the same way.

## Update identity when you really change equipment

An instrument going out for calibration and being replaced by a spare is a normal event, and a mismatch is the right response when that happens. Here's the process we'd suggest. The technician sees the `IdentityMismatch`, confirms that the swap was intended, and updates the profile through your normal review. Now your version history shows when each instrument was on each bench. That's useful, as you can then trace a set of results to a specific calibration period.

## Recap

- Treat differences between environments as **inputs**. Avoid branches in your code.
- **Limits don't change with the environment.** They're product requirements.
- Keep **one profile per bench**, in version control, built by CI.
- Keep an eye on **mixed stations**: `sim=True` doesn't guarantee that there's no hardware.
- A run should record the **effective configuration**, not just a file name.

The configuration is only half of what it takes to reproduce something. The other half is the software.

**Next:** [Software versions and reproducibility](reproducibility.md)
