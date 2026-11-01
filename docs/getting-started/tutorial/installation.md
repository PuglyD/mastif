# Installation and your development environment

Let's get a working environment onto your machine. This takes a few minutes, and you
don't need any instruments.

!!! success "Works today"
    Everything on this page runs against the current code.

## What you need

- **Python 3.12 or newer.** mastif uses modern typing syntax throughout, including
  `type` statements and generic function syntax.
- **Git**, to get the source.
- **[uv](https://docs.astral.sh/uv/)**, which manages the Python environment.

mastif isn't published as a release yet, so for now you install it from a source
checkout. This is a *workspace*: one repository holding two distributions that are
developed together.

| Distribution | Import name | What it is |
|---|---|---|
| `mastif` | `mastif` | The framework itself |
| `mastif-testing` | `mastif_testing` | Fake instruments and conformance checks for your test suites |

## Get the code

<!-- termynal: {title: "Real commands · clone and sync"} -->
```console
$ git clone --branch develop https://github.com/PuglyD/mastif.git
$ cd mastif
$ uv sync --group docs
```

These docs track `develop`, so the clone command selects that branch explicitly.

`uv sync` reads the workspace, resolves its dependencies and creates a virtual
environment in `.venv`. The `docs` group adds what you need to preview this site locally.
You don't activate anything: prefix a command with `uv run`, and it runs inside that
environment.

## Check that it works

The smallest example in the repository judges two readings, without talking to any
hardware:

<!-- termynal: {title: "Real transcript · first_measurement.py"} -->
```console
$ uv run python docs/examples/first_measurement.py
idle_current: 180 mA -> PASS
idle_current: 300 mA -> FAIL
```

If you see that, you're ready. And yes, the second line is meant to say FAIL: 300 mA is
over the 250 mA limit, so a FAIL is mastif doing its job, and it doesn't indicate a problem
with your installation.

There's a second example that goes further, building a whole simulated station:

<!-- termynal: {title: "Real transcript · learn_station.py"} -->
```console
$ uv run python docs/examples/learn_station.py
idle_current: 180 mA -> PASS
after cleanup: output enabled = False
idle_current: 300 mA -> FAIL
after cleanup: output enabled = False
```

We'll take this one apart in the tutorial.

## Optional hardware support

The core has few dependencies on purpose, so that it stays small and installs anywhere.
Support for particular connection types comes as an extra, and you only install what your
bench uses.

| Extra | Adds | Needed for |
|---|---|---|
| `mastif[serial]` | pyserial | Serial ports |
| `mastif[visa]` | pyvisa | VISA instruments (you also need a VISA backend) |
| `mastif[ssh]` | paramiko | SSH shells and sessions |

Plain TCP, UDP and Telnet need nothing extra. If you ask for a
connection whose library isn't installed, you get a `TransportError` that names the
missing extra, at the moment the station opens.

## Set up your editor

mastif is heavily typed, and that pays off most in your editor. Point it at the
interpreter in `.venv` so that completion and go-to-definition work. Then try this
small experiment: type the following into a scratch file, and hover over `current`.

```python title="scratch.py"
from mastif.kernel.units import mA

current = 180 * mA
print(current.to("A"))
```

Your editor should tell you that `current` is a `Quantity`, and offer `.to` and
`.magnitude` as you type. Throughout this course, we encourage you to follow a symbol
into its definition: the source is written to be read, every public function has a
docstring with an example, and the [API reference](../../reference/kernel/index.md) is
generated directly from it.

## Preview these docs

If you'd like to read this course locally, perhaps while changing the examples:

```console
uv run mkdocs serve
```

Then open the address it prints.

## About the `mastif` command

Some chapters show a `mastif` command line, such as `mastif run`. It's part of the
engine design, so installing this checkout won't give you that command yet. Those chapters
are marked as design previews, and they always tell you what you can run today instead.

## Recap

You have a working environment, and you've seen mastif judge a measurement. Time to write
a test.

**Next:** [Your first test run](writing-tests/first-run.md)
