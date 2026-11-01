# Software versions and reproducibility

A customer returns a unit. It passed its test eleven months ago, and it's failing now. The question that everyone will ask is whether the test has changed. If you can't answer that, then you can't tell whether the product has degraded or the test simply got stricter, and that's a very expensive thing not to know.

Answering it comes down to recording what ran, at the time that it ran. It's cheap to do, and you can't do it afterwards.

!!! success "Works today"
    `VersionInfo` works today. Recording versions in a run's manifest is a design preview.

## Knowing what's running

mastif includes a small helper that reports the version of any installed distribution:

```python
from mastif.infra.version import VersionInfo

info = VersionInfo.load("mastif")
print(info.summary())
```

```text title="Real output, from a development checkout"
mastif 0.1.0.dev0 | edc1568 on feature/architecture-specs | uncommitted changes
```

There's more information in that line than you might expect. It has the package version, the commit it was built from, the branch, and a warning that this isn't exactly that commit. That last part is the important one. A version number alone doesn't identify modified code, and someone's local edits can produce a result that nobody can ever reproduce.

Here's where that information comes from:

| Where the code's running | Source of the commit | `info.git.source` |
|---|---|---|
| An installed wheel | Embedded when the wheel was built | `"embedded"` |
| A development checkout | Asked of git, live | `"runtime"` |
| Neither is available | Not known, and it says so | `"unavailable"` |

Note that last row. When the information isn't available, mastif says that it's not available. There's no fake `0.0.0`. A record which admits what it doesn't know is more useful than one that makes something up, since you can trust the rest of it.

Your SDK can embed its commit the same way, by copying mastif's build hook, `packages/mastif/hatch_build.py`, and changing the package name. We'd recommend doing that, since it's the commit of your driver that you'll most want to know about.

## The five things to record

A result depends on more than the code. To really explain a measurement, here's what you need:

| What | Why | Recorded as |
|---|---|---|
| **Software** | The code that ran | Package versions and commits |
| **Environment** | Dependencies can change behaviour | A lock file, or package versions |
| **Procedure** | What was asked for | The frozen plan and resolved config |
| **Equipment** | What did the measuring | Instrument identities and revisions |
| **The unit** | What was measured | DUT identity and state |

Here's what a run's manifest looks like, bringing all of these together:

```json title="manifest.json — preview, abridged"
{
  "run_id": "20261031T090000Z-3fa9c2",
  "started": "2026-10-31T09:00:00Z",
  "software": {
    "mastif": {"version": "0.4.0", "commit": "edc1568", "dirty": false},
    "demo-sdk": {"version": "2.1.3", "commit": "a91f002", "dirty": false},
    "widget-tests": {"version": "1.7.0", "commit": "33be1c9", "dirty": false}
  },
  "plan": {"name": "widget-acceptance", "sha256": "4d1e...", "items": 16},
  "station": {
    "name": "bench-01",
    "profile_sha256": "9f2c...",
    "resources": {
      "bench_supply": {"identity": {"model": "PSU-X", "serial": "A123", "revision": "1.4"}}
    }
  },
  "unit": {"serial": "SN-42", "firmware": "2.1"}
}
```

With that, the question at the start of this chapter gets a precise answer: *same test package? Same limits? Same instrument?* If so, you can reasonably look at the unit.

## Controlling what gets deployed

Recording a version is only useful if what's running was really built from it. So the deployment side matters as well.

**Deploy built wheels, not checkouts.** A wheel is a fixed artifact with its commit embedded. A checkout on a station can have someone's edits on it, and it'll be different tomorrow.

**Lock your dependencies.** `uv lock` pins everything, and it's what lets you recreate a given environment, including transitive dependencies you've never heard of. Keep a lock file per deployment.

**Treat "dirty" as a problem on production stations.** A production run that says `uncommitted changes` means that somebody edited something on the floor. You might decide your application should refuse to run in that state. It's a one-line check at start-up:

```python title="excerpt"
runtime = bootstrap(config_dir, distribution="widget-tests")
if runtime.version.git.dirty:
    raise SystemExit("refusing to run modified test code on a production station")
```

## Reproducible isn't the same as repeatable

There's a distinction worth holding on to. Everything so far is about **provenance**: knowing precisely what ran. It's not the same as getting the same number twice.

Even with identical software, instruments and procedure, physics moves on. An instrument drifts. It's warmer today. A calibration has aged. Your settling time was slightly too short, and you've been measuring the tail of a transient all along.

Recording these things won't remove the variation, but it does let you ask about it. With a year of structured results, you can plot one instrument's readings of your golden unit over time, and see the drift, and see that it changes at the instrument's calibration date. That's only possible because the data was recorded with its context. It's one of the best reasons to build this way.

## Incomplete evidence is still evidence

Sometimes a record is going to be incomplete. A driver can't report a revision. A package wasn't built with an embedded commit. A device returned no serial.

When that happens, record what's missing explicitly. Don't substitute a placeholder that looks like a real value. An honest gap keeps the rest of the record trustworthy, whereas a single invented value casts doubt on all of it.

## Recap

- **`VersionInfo`** reports versions, commits and uncommitted changes, and it says when it doesn't know.
- A result needs five things recorded: **software, environment, procedure, equipment and the unit**.
- **Deploy built wheels from a lock file**, and be suspicious of a dirty production run.
- **Provenance isn't repeatability**, but it's what lets you investigate variation.
- **Record gaps honestly.** Never invent a value.

So far in this section, everything has been about a single process. What if you're running a shared station?

**Next:** [Running a persistent station service](service.md)
