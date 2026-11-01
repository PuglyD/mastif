"""Logging: a readable console, a complete log file, and tables that render as tables.

Why this exists:
    At a test station, logs serve two audiences:

    - The **operator** watches the console. It should show what's happening, colour-coded
      by severity, without noise.
    - The **engineer investigating a failure** reads the log file afterwards. It should
      hold everything, including every byte exchanged with instruments, with timestamps.

    Test data is often tabular (a sweep over channels, a pandas DataFrame). Printed as
    ``str(df)`` it becomes unreadable on a console and unparseable in a file. Logging a
    table should just work: a real table on the console, a markdown table in the file.

    Python's standard ``logging`` already routes messages to handlers. This module
    supplies the pieces that make it fit a test station:

    - A Rich console handler (`RichTableHandler`) with a level colour theme.
    - A table-aware formatter for files (`TableAwareFormatter`).
    - Two extra levels: ``TRACE`` (below DEBUG, for raw protocol traffic) and ``SUCCESS``
      (between INFO and WARNING, for "step passed" messages).
    - `configure_logging`, which applies a standard ``dictConfig`` from YAML, a dict or the
      bundled default.

How it's set up:
    Logging is process-global in Python, so it's configured **once**, at the
    application's start-up (see `mastif.infra.bootstrap`). Everything else just calls
    ``logging.getLogger(name)``, or receives an injected logger: drivers get one per
    resource, named ``mastif.resources.<resource>``. Transports trace bytes on
    ``mastif.io``, which the default config sends to the file only.

Logging a table::

    log = logging.getLogger("acme.tests")
    log.info(table)                      # a kernel Table result, or a pandas DataFrame
    log.info(df, extra={"title": "Channel sweep"})

Configuration resolution (`resolve_logging_config`), first match wins:

1. ``logging.yaml`` / ``logging.yml`` in the app's config directory
2. a ``logging`` section in the settings
3. the bundled default (``mastif/infra/default_logging.yaml``)
"""

import copy
import logging
import logging.config
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table as RichTable
from rich.theme import Theme

from mastif.infra.config import Settings, _plain
from mastif.infra.errors import ConfigError
from mastif.kernel.results import Table
from mastif.kernel.verdict import Verdict

TRACE: int = 5
"""Level below DEBUG for raw protocol traffic (every byte to and from instruments)."""
SUCCESS: int = 25
"""Level between INFO and WARNING for positive milestones ("step passed")."""

THEME: Theme = Theme(
    {
        "logging.level.trace": "bright_black",
        "logging.level.debug": "dark_goldenrod",
        "logging.level.info": "dodger_blue1",
        "logging.level.success": "green3",
        "logging.level.warning": "orange1",
        "logging.level.error": "red1",
        "logging.level.critical": "bold white on red",
    }
)
"""Console colours per level, used by `RichTableHandler`."""

_VERDICT_STYLES = {
    Verdict.PASS: "green3",
    Verdict.WARN: "orange1",
    Verdict.FAIL: "red1",
    Verdict.ERROR: "bold red1",
    Verdict.SKIPPED: "bright_black",
    Verdict.ABORTED: "bold magenta",
}

LOGGING_FILE_NAMES: tuple[str, ...] = ("logging.yaml", "logging.yml")
"""Configuration filenames considered when resolving application logging settings."""


class MastifLogger(logging.Logger):
    """A standard logger with ``trace()`` and ``success()`` methods for the two extra levels.

    `configure_logging` installs it as the logger class, so loggers created afterwards
    have these methods. With plain loggers, use ``log.log(TRACE, ...)``.

    Examples:
        >>> log = MastifLogger("demo")
        >>> log.isEnabledFor(SUCCESS) or True
        True
    """

    def trace(self, msg: object, *args: object, **kwargs: Any) -> None:
        """Log at TRACE level: raw protocol traffic, the noisiest detail.

        Examples:
            ``log.trace(">> %r", b"*IDN?\\n")``
        """
        if self.isEnabledFor(TRACE):
            self._log(TRACE, msg, args, **kwargs)

    def success(self, msg: object, *args: object, **kwargs: Any) -> None:
        """Log at SUCCESS level: a positive milestone such as a passed step.

        Examples:
            ``log.success("power-up sequence complete")``
        """
        if self.isEnabledFor(SUCCESS):
            self._log(SUCCESS, msg, args, **kwargs)


@dataclass(frozen=True)
class TabularData:
    """A table extracted from a log message, ready to render.

    Attributes:
        title: Shown above the table.
        columns: Column headers.
        rows: Cell values as text.
        row_styles: Optional Rich style per row, e.g. a verdict colour.

    Examples:
        >>> TabularData("t", ("a",), (("1",),)).columns
        ('a',)
    """

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    row_styles: tuple[str | None, ...] = field(default=())


def _cell(value: object) -> str:
    """Render one cell as text, with empty text for missing values.

    Examples:
        >>> _cell(None), _cell(1.5)
        ('', '1.5')
    """
    return "" if value is None else str(value)


def as_tabular(message: object, title: str | None = None) -> TabularData | None:
    """Recognise a loggable table and extract its contents; anything else gives ``None``.

    Recognised:

    - mastif `Table` results, rendered with an extra *verdict* column and rows coloured
      by verdict
    - pandas DataFrames, detected without importing pandas, so pandas stays optional

    Args:
        message: The object passed to ``log.info(...)``.
        title: Overrides the default title (the table's name, or "DataFrame").

    Returns:
        The table contents, or ``None`` if the message isn't tabular.

    Examples:
        >>> from mastif.kernel import Limits, Table
        >>> t = Table(name="sweep", columns=("ch", "p"), rows=((1, 9.5), (2, 12.0)),
        ...           limits={"p": Limits.at_most(10.0)})
        >>> data = as_tabular(t)
        >>> data.columns, data.rows[1]
        (('ch', 'p', 'verdict'), ('2', '12.0', 'fail'))
        >>> as_tabular("plain text") is None
        True
    """
    if isinstance(message, Table):
        verdicts = message.row_verdicts
        return TabularData(
            title=title or message.name,
            columns=(*message.columns, "verdict"),
            rows=tuple(
                (*(_cell(c) for c in row), str(v))
                for row, v in zip(message.rows, verdicts, strict=True)
            ),
            row_styles=tuple(_VERDICT_STYLES.get(v) for v in verdicts),
        )
    module = type(message).__module__ or ""
    if module.startswith("pandas") and hasattr(message, "itertuples"):
        df: Any = message
        return TabularData(
            title=title or f"DataFrame ({df.shape[0]} rows x {df.shape[1]} columns)",
            columns=tuple(str(c) for c in df.columns),
            rows=tuple(tuple(_cell(v) for v in row) for row in df.itertuples(index=False)),
        )
    return None


def to_markdown(data: TabularData) -> str:
    """Render a table as GitHub-style markdown, for log files and reports.

    Pipes inside cells are escaped, so the table structure can't break.

    Examples:
        >>> print(to_markdown(TabularData("t", ("a", "b"), (("1", "x|y"),))))
        **t**
        <BLANKLINE>
        | a | b |
        | --- | --- |
        | 1 | x\\|y |
    """

    def esc(text: str) -> str:
        """Escape pipe characters inside a cell.

        Examples:
            ``esc("a|b")`` returns ``"a\\|b"``.
        """
        return text.replace("|", "\\|")

    lines = [
        f"**{data.title}**",
        "",
        "| " + " | ".join(esc(c) for c in data.columns) + " |",
        "| " + " | ".join("---" for _ in data.columns) + " |",
    ]
    lines += ["| " + " | ".join(esc(c) for c in row) + " |" for row in data.rows]
    return "\n".join(lines)


def to_rich_table(data: TabularData) -> RichTable:
    """Render a table as a Rich table, for the console.

    Examples:
        >>> to_rich_table(TabularData("t", ("a",), (("1",),))).row_count
        1
    """
    table = RichTable(title=data.title, show_header=True, header_style="bold")
    for column in data.columns:
        table.add_column(column)
    for i, row in enumerate(data.rows):
        style = data.row_styles[i] if i < len(data.row_styles) else None
        table.add_row(*row, style=style)
    return table


def _tabular_of(record: logging.LogRecord) -> TabularData | None:
    """Extract a table from a log record, honouring an ``extra={"title": ...}``.

    Examples:
        Returns ``None`` for ordinary text records.
    """
    return as_tabular(record.msg, getattr(record, "title", None))


class RichTableHandler(RichHandler):
    """Console handler: colour-coded log lines, and logged tables printed as tables.

    A tabular record prints a one-line summary (as a normal log line) followed by the
    table, so the console keeps its timeline.

    Examples:
        In a logging YAML::

            handlers:
              console:
                (): mastif.infra.logs.RichTableHandler
                level: INFO
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Create the handler with mastif's colour theme, unless a console is given.

        Examples:
            ``RichTableHandler(level=logging.INFO)``
        """
        kwargs.setdefault("console", Console(theme=THEME, stderr=True))
        super().__init__(*args, **kwargs)

    def emit(self, record: logging.LogRecord) -> None:
        """Print the record; tables become a summary line plus a Rich table.

        Examples:
            Called by ``logging`` for each record that reaches this handler.
        """
        data = _tabular_of(record)
        if data is None:
            super().emit(record)
            return
        summary = logging.makeLogRecord(record.__dict__)
        summary.msg, summary.args = f"{data.title} ({len(data.rows)} rows)", ()
        super().emit(summary)
        try:
            self.console.print(to_rich_table(data))
        except Exception:
            self.handleError(record)


class TableAwareFormatter(logging.Formatter):
    """File formatter that writes logged tables as markdown, below the usual prefix.

    It formats a *copy* of the record, so other handlers (such as the console) still
    see the original table object.

    Examples:
        In a logging YAML::

            formatters:
              detailed:
                (): mastif.infra.logs.TableAwareFormatter
                format: "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the record; tables become markdown on the lines after the prefix.

        Examples:
            ``2026-10-25 10:00:00 | INFO | acme | sweep`` followed by a markdown table.
        """
        data = _tabular_of(record)
        if data is None:
            return super().format(record)
        copy_ = logging.makeLogRecord(record.__dict__)
        copy_.msg, copy_.args = "\n\n" + to_markdown(data) + "\n", ()
        return super().format(copy_)


class Loggers:
    """Attribute and item access to named loggers: ``loggers.traffic``, ``loggers["acme.x"]``.

    A convenience for scripts and notebooks. It's equivalent to
    ``logging.getLogger(name)`` and holds no state.

    Examples:
        >>> Loggers()["acme.tests"].name
        'acme.tests'
        >>> Loggers().traffic.name
        'traffic'
    """

    def __getattr__(self, name: str) -> logging.Logger:
        """Return the logger with this name.

        Examples:
            ``Loggers().station.info("ready")``
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return logging.getLogger(name)

    def __getitem__(self, name: str) -> logging.Logger:
        """Return the logger with this (possibly dotted) name.

        Examples:
            ``Loggers()["mastif.io"]``
        """
        return logging.getLogger(name)


def default_logging_config() -> dict[str, Any]:
    """Return a fresh copy of mastif's bundled logging configuration.

    Console: INFO and above, colour-coded, with tables rendered. File: ``mastif.log``,
    DEBUG and above, rotated at 10 MB with 5 backups, tables as markdown. The
    ``mastif.io`` logger (instrument byte traffic) goes to the file only.

    Examples:
        >>> cfg = default_logging_config()
        >>> io_logger = cfg.get("loggers").get("mastif.io")
        >>> sorted(cfg.get("handlers")), io_logger.get("propagate")
        (['console', 'file'], False)
    """
    text = files("mastif.infra").joinpath("default_logging.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def resolve_logging_config(
    settings: Settings | None = None, config_dir: str | Path | None = None
) -> dict[str, Any]:
    """Choose the logging configuration an application should use.

    First match wins:

    1. ``logging.yaml`` / ``logging.yml`` in ``config_dir``
    2. a ``logging`` section in ``settings``
    3. the bundled default

    Args:
        settings: The application's settings.
        config_dir: The application's config directory.

    Returns:
        A ``dictConfig``-style dict.

    Raises:
        ConfigError: If a ``logging.yaml`` exists but can't be parsed.

    Examples:
        >>> from mastif.infra.config import create_settings
        >>> s = create_settings(defaults={"logging": {"version": 1, "root": {"level": "WARNING"}}})
        >>> resolve_logging_config(s).get("root")
        {'level': 'WARNING'}
        >>> "handlers" in resolve_logging_config()
        True
    """
    if config_dir is not None:
        for name in LOGGING_FILE_NAMES:
            path = Path(config_dir) / name
            if path.is_file():
                return _load_yaml(path)
    if settings is not None:
        section = settings.get("logging")
        if isinstance(section, Mapping):
            return _plain(section)
    return default_logging_config()


def _load_yaml(path: Path) -> dict[str, Any]:
    """Read a logging YAML file.

    Raises:
        ConfigError: If the file can't be read or isn't a mapping.

    Examples:
        ``_load_yaml(Path("config/logging.yaml"))``
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"{path}: cannot read logging config: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: logging config must be a mapping")
    return data


def _place_log_files(config: dict[str, Any], log_dir: Path) -> None:
    """Make relative ``filename`` entries of file handlers relative to ``log_dir``.

    The directory is created if needed, so a fresh station can log on its first run.

    Examples:
        ``filename: mastif.log`` with ``log_dir=/data/logs`` gives ``/data/logs/mastif.log``.
    """
    for handler in (config.get("handlers") or {}).values():
        name = handler.get("filename") if isinstance(handler, dict) else None
        if name and not Path(name).is_absolute():
            handler["filename"] = str(log_dir / name)
            log_dir.mkdir(parents=True, exist_ok=True)


def configure_logging(
    config: str | Path | Mapping[str, Any] | None = None,
    *,
    log_dir: str | Path | None = None,
    level: int | str | None = None,
    rich_tracebacks: bool = True,
) -> None:
    """Configure process-wide logging. Call once, at application start-up.

    This is the one place where mastif changes global state, and it does so only when
    called, never at import time. It:

    1. registers the ``TRACE`` and ``SUCCESS`` levels and installs `MastifLogger` as the
       logger class
    2. loads the configuration: a YAML path, a ``dictConfig`` mapping, or the bundled
       default when ``None``
    3. places relative log-file names under ``log_dir``, creating it if needed
    4. applies it with ``logging.config.dictConfig``
    5. optionally installs Rich's pretty tracebacks for uncaught exceptions

    Args:
        config: YAML file path, ``dictConfig`` mapping, or ``None`` for the default.
        log_dir: Directory for relative log-file names; defaults to the working
            directory.
        level: Overrides the root logger's level, e.g. ``"DEBUG"`` for a verbose run.
        rich_tracebacks: Install Rich tracebacks, with local variables, for uncaught
            exceptions.

    Raises:
        ConfigError: If the file can't be read or the configuration is invalid (for
            example an unknown handler class).

    Examples:
        >>> configure_logging({"version": 1, "disable_existing_loggers": False,
        ...                    "root": {"level": "INFO"}}, rich_tracebacks=False)
        >>> logging.getLevelName(SUCCESS)
        'SUCCESS'

        At an application's entry point it is usually just
        ``configure_logging(resolve_logging_config(settings, config_dir), log_dir=...)``.
    """
    logging.addLevelName(TRACE, "TRACE")
    logging.addLevelName(SUCCESS, "SUCCESS")
    logging.setLoggerClass(MastifLogger)
    if config is None:
        cfg = default_logging_config()
    elif isinstance(config, str | Path):
        cfg = _load_yaml(Path(config))
    else:
        cfg = copy.deepcopy(dict(config))
    _place_log_files(cfg, Path(log_dir) if log_dir is not None else Path.cwd())
    if level is not None:
        cfg.setdefault("root", {})["level"] = level
    try:
        logging.config.dictConfig(cfg)
    except (ValueError, TypeError, AttributeError, ImportError) as exc:
        raise ConfigError(f"invalid logging configuration: {exc}") from exc
    if rich_tracebacks:
        from rich.traceback import install  # noqa: PLC0415  (only when asked for)

        install(show_locals=True)
