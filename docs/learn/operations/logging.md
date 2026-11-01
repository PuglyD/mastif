# Logging and diagnostics

An instrument timed out, so the run's result correctly says ERROR. Good. Now an engineer has to work out why. Which command was it? What had been sent just before that? Did the instrument send anything back at all? A verdict doesn't answer those questions, and it isn't meant to. That's the job of logs.

!!! success "Works today"
    Everything on this page runs against the current code. Tying log lines to run events is part of the engine design.

## Logs aren't results

Let's start with the distinction that matters most. mastif keeps two channels, and they're for different readers.

| | Results and events | Logs |
|---|---|---|
| **Written for** | Programs, and auditors | Engineers debugging |
| **Format** | A typed, versioned schema | Whatever's most helpful today |
| **May change freely?** | No, it's a contract | Yes |
| **Is it evidence?** | Yes | No |

So the 180 mA that you put in a report comes from a `Measurement`, never from a parsed log line. And a dashboard reads events, never logs. This keeps you free to improve a log message without breaking anything.

## What you get

`bootstrap` sets up logging for you. With the bundled defaults, you get three destinations, for three levels of detail:

| Destination | Level | What goes there |
|---|---|---|
| Console (Rich, colour-coded) | INFO and above | Readable progress, with tables shown as tables |
| `mastif.log` (rotating: 10 MB, 5 files) | DEBUG and above | Everything, with timestamps |
| The `mastif.io` logger | DEBUG | **Raw instrument traffic**, to the file only |

That third one's the valuable one. Each byte exchanged with each instrument is written to the log file. When an engineer needs to know exactly what was on the wire at the moment of a failure, it's right there, without anyone having to reproduce the failure with extra logging turned on.

Using it is just the standard library, plus one convenience:

```python
import logging

from mastif.infra import bootstrap

bootstrap(log_level="INFO", rich_tracebacks=False)

log = logging.getLogger("demo.application")
log.info("preparing the selected station profile")
log.success("power-up complete")     # An extra level, 25, added by mastif
```

Note what you're doing in that code: calling standard `logging.getLogger`. Your drivers and tasks don't need to depend on anything from mastif in order to log. They use the standard library, and the application decides where it goes.

## Logging from a driver

A driver can ask for a logger in its constructor, and it receives one named after that resource. That means each log line says which instrument it's about, without you needing to do anything:

```python title="excerpt"
@driver("acme.psu-x", provides=[PowerSupply])
class PsuX:
    def __init__(self, cfg: Config, io: Scpi, log: logging.Logger) -> None:
        self.io = io
        self.log = log

    def open(self) -> None:
        self.log.debug("selecting channel %d", self.cfg.channel)
```

A driver must never configure logging or add handlers. That's a process-wide decision, and it belongs to the application alone. If a library changes global logging as a side effect of being imported, you've lost control of your diagnostics.

## Logging a table

If you've measured a sweep, the log can show that too:

```python
import logging

from mastif.infra import bootstrap
from mastif.kernel.limits import Limits
from mastif.kernel.results import Table
from mastif.kernel.units import mA

bootstrap(log_level="INFO", rich_tracebacks=False)

sweep = Table(
    name="idle_vs_supply",
    columns=("voltage_V", "current"),
    units={"current": "mA"},
    limits={"current": Limits.at_most(250 * mA)},
    rows=((4.75, 171.0), (5.0, 180.0)),
)
logging.getLogger("demo.tests").info(sweep)
```

It's a real table on the console, and Markdown in the file, so it can be read in both. A pandas DataFrame works as well, with the `mastif[pandas]` extra.

## Writing useful log lines

Here's what makes a line helpful when you read it at 2 a.m.

**Say which resource, and which operation.** "Timeout" is useless, and "bench_meter: no reply to MEAS:VOLT? within 2.0 s" tells you where to walk to.

**Log decisions, not only actions.** "Skipping idle_current: this revision has no idle mode" answers a question somebody will ask later.

**Keep the first cause.** When things go wrong, they cascade. Chain your exceptions with `from error`, so that the final "failed to close" doesn't hide the timeout that began it all.

**Never log secrets.** Transport passwords are `SecretStr`, so they won't appear unless someone deliberately reveals them. Think about your own payloads too: a device's response might contain something sensitive.

**Turn up the detail deliberately.** A `TRACE` level is available for very fine-grained communication details. Large transfers and frequent commands can swamp both your disk and the useful information. Turn it on when you need it.

## Customising it

Put a standard `logging.yaml` (in Python's `dictConfig` format) into your config directory, or add a `logging:` section to your settings. Copy `mastif/infra/default_logging.yaml` as a starting point. Relative log file names get placed under the `log_dir` that you gave to `bootstrap`.

A good thing to do on a production station is to keep the log rotation generous, and to back up the log directory along with the run folders. When someone investigates a failure from three weeks ago, the wire traffic is often what solves it.

## Connecting logs to runs

Once the engine exists, log records carry the run's identity and position, so that you'll be able to line up a log with the events from the same moment.

```text title="a log line with run context — preview"
09:00:01.204 | DEBUG | mastif.io.bench_supply | > MEAS:CURR? | run=20261031T0900 task=idle_current voltage=5V
```

Until then, timestamps do that job, as long as your clocks are sensible.

## Recap

- **Results are evidence, and logs are diagnostics.** Never parse one to get the other.
- The default setup gives you a readable **console**, a detailed **file**, and all of the **raw instrument traffic**.
- Use **standard `logging`** everywhere. Only the application configures it.
- Name the **resource and operation**, log **decisions**, and keep the **first cause**.

Now let's use this to confirm that a station is in a fit state to run anything.

**Next:** [Preparing and validating a station](preflight.md)
