# Guide: bootstrap an application

How a mastif-based application starts: settings, logging and version, then the
station. Concepts: [Infra](../../learn/architecture/infra.md). Design: ADR-0026–0029.

## 1. Lay out the station's folders

mastif doesn't dictate folder layouts. Each org decides. A typical layout:

```
C:/stations/bench-01/
├── config/
│   ├── 00-base.toml        # shared settings (often deployed from your SDK)
│   ├── 10-site.yaml        # this site's overrides
│   ├── logging.yaml        # optional: custom logging (dictConfig)
│   └── station.yaml        # the station profile (not a settings file: see below)
└── logs/
```

!!! warning "Keep the station profile out of the settings directory"
    `create_settings` loads *every* yaml/toml/json/ini file in the config directory.
    Put `station.yaml` in a separate folder, or name it with another suffix, if you
    don't want it merged into the settings.

## 2. Write the settings

```toml
# 00-base.toml
[station]
name = "bench-01"
retries = 2

[acme.psu]
settle_time_s = 0.2
```

## 3. Start the application

```python
import sys
from mastif.infra import bootstrap, ConfigError, VersionError
from mastif.resources.registry import Registry
from mastif.station import Station, StationProfile


def main() -> int:
    try:
        runtime = bootstrap(
            "C:/stations/bench-01/config",
            distribution="acme-sdk",  # logs "starting acme-sdk 1.2.0 | abc1234 on main"
            log_dir="C:/stations/bench-01/logs",
            envvar_prefix="ACME",
        )
    except (ConfigError, VersionError) as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2

    profile = StationProfile.load("C:/stations/bench-01/profiles/station.yaml")
    station = Station.build(profile, Registry.discover(), settings=runtime.settings)
    with station:
        ...  # run tests (engine: planned)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 4. Override per machine or per run

```powershell
$env:ACME_STATION__RETRIES = "5"     # nested key: double underscore
python -m acme_app
```

Or pass `files=[".../local.yaml"]` for machine-specific files, and
`log_level="DEBUG"` for a verbose run.

## 5. Read typed settings where they matter

```python
from pydantic import BaseModel
from mastif.infra import section


class PsuDefaults(BaseModel):
    settle_time_s: float = 0.1


defaults = section(runtime.settings, "acme.psu", PsuDefaults)
```

A typo in the file now fails at start-up with the field named, instead of silently
reading as missing.

## Testing code that takes settings

```python
from mastif.infra import create_settings


def test_psu_uses_settle_time():
    settings = create_settings(defaults={"acme": {"psu": {"settle_time_s": 0.0}}})
    station = Station.build(profile, registry, settings=settings)
```

No globals, no monkey-patching. Each test builds exactly the settings it needs.
