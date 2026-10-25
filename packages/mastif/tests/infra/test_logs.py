"""Unit tests for `mastif.infra.logs`.

Logging is what operators and investigators read, so these tests pin down:

- tables (kernel results and DataFrame-like objects) are recognised and rendered
- file output gets markdown without corrupting what other handlers see
- the extra TRACE and SUCCESS levels work
- configuration resolution order holds, relative log files go under ``log_dir``, and
  invalid configs raise `ConfigError`

A fixture restores global logging state after every test.
"""

import io
import logging

import pytest
from rich.console import Console

from mastif.infra.config import create_settings
from mastif.infra.errors import ConfigError
from mastif.infra.logs import (
    SUCCESS,
    TRACE,
    MastifLogger,
    RichTableHandler,
    TableAwareFormatter,
    as_tabular,
    configure_logging,
    default_logging_config,
    resolve_logging_config,
    to_markdown,
)
from mastif.kernel import Limits, Table


@pytest.fixture(autouse=True)
def _restore_logging():
    """Put the root logger and logger class back after each test."""
    root = logging.getLogger()
    handlers, level, cls = root.handlers[:], root.level, logging.getLoggerClass()
    yield
    for h in root.handlers[:]:
        if h not in handlers:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)
    logging.setLoggerClass(cls)


def _table() -> Table:
    """A two-row table with one failing row.

    Returns:
        The table.
    """
    return Table(
        name="sweep",
        columns=("ch", "p"),
        rows=((1, 9.5), (2, 12.0)),
        limits={"p": Limits.at_most(10.0)},
    )


class FakeFrame:
    """Imitates the parts of a pandas DataFrame that logging uses."""

    __module__ = "pandas.core.frame"
    columns = ("a", "b")
    shape = (2, 2)

    def itertuples(self, index: bool = False):
        """Yield rows."""
        return iter([(1, "x"), (2, None)])


class _Collect(logging.Handler):
    """Collects the level names of records it receives."""

    def __init__(self) -> None:
        """Start empty."""
        super().__init__()
        self.levels: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Remember the level name."""
        self.levels.append(record.levelname)


def _record(msg: object, **extra: object) -> logging.LogRecord:
    """Build a log record carrying an arbitrary message object.

    Args:
        msg: The message.
        **extra: Extra record attributes.

    Returns:
        The record.
    """
    record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, (), None)
    record.__dict__.update(extra)
    return record


def test_kernel_table_becomes_tabular_with_verdicts():
    """Kernel tables render with a verdict column, so failures stand out in logs."""
    data = as_tabular(_table())

    assert data is not None
    assert data.rows == (("1", "9.5", "pass"), ("2", "12.0", "fail"))


def test_dataframe_detected_without_importing_pandas():
    """DataFrames are recognised by type, so pandas remains an optional extra."""
    data = as_tabular(FakeFrame())

    assert data is not None
    assert (data.columns, data.rows[1]) == (("a", "b"), ("2", ""))


def test_plain_messages_are_not_tabular():
    """Ordinary messages pass through untouched."""
    assert as_tabular("hello") is None


def test_markdown_escapes_pipes():
    """A pipe inside a cell must not break the markdown table."""
    data = as_tabular(Table(name="t", columns=("a",), rows=(("x|y",),)))
    assert data is not None

    md = to_markdown(data)

    assert "| x\\|y | pass |" in md


def test_file_formatter_writes_markdown_without_mutating_record():
    """The file gets markdown, but the record still holds the table for other handlers."""
    record = _record(_table())

    text = TableAwareFormatter("%(levelname)s %(message)s").format(record)

    assert "| 2 | 12.0 | fail |" in text
    assert isinstance(record.msg, Table)


def test_extra_title_overrides_table_title():
    """``extra={"title": ...}`` names the table in the output."""
    text = TableAwareFormatter("%(message)s").format(_record(_table(), title="Channel sweep"))

    assert "**Channel sweep**" in text


def test_console_handler_prints_summary_and_table():
    """The console shows a summary log line followed by the rendered table."""
    buffer = io.StringIO()
    handler = RichTableHandler(console=Console(file=buffer, width=120))

    handler.emit(_record(_table()))

    out = buffer.getvalue()
    assert "sweep (2 rows)" in out and "fail" in out


def test_trace_and_success_levels_work_after_configure():
    """Configured loggers gain ``trace()`` and ``success()`` and the level names."""
    configure_logging(
        {"version": 1, "disable_existing_loggers": False, "root": {"level": "NOTSET"}},
        rich_tracebacks=False,
    )
    handler = _Collect()
    log = logging.getLogger("mastif.test.levels.unique")
    assert isinstance(log, MastifLogger)
    log.addHandler(handler)

    log.trace("bytes")
    log.success("done")

    assert handler.levels == ["TRACE", "SUCCESS"]
    assert (TRACE, SUCCESS) == (5, 25)


def test_relative_log_files_go_under_log_dir(tmp_path):
    """Relative file names are placed under ``log_dir``, which is created if needed."""
    cfg = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"f": {"class": "logging.FileHandler", "filename": "run.log"}},
        "loggers": {"mastif.test.file": {"handlers": ["f"], "level": "INFO"}},
    }

    configure_logging(cfg, log_dir=tmp_path / "logs", rich_tracebacks=False)
    logging.getLogger("mastif.test.file").info("hello")
    for h in logging.getLogger("mastif.test.file").handlers:
        h.close()

    assert "hello" in (tmp_path / "logs" / "run.log").read_text()


def test_invalid_logging_config_is_config_error():
    """An unknown handler class fails as ConfigError, not a raw library exception."""
    with pytest.raises(ConfigError, match="invalid logging configuration"):
        configure_logging(
            {"version": 1, "handlers": {"x": {"class": "no.such.Handler"}}},
            rich_tracebacks=False,
        )


def test_resolution_prefers_logging_yaml_in_config_dir(tmp_path):
    """A logging.yaml in the config directory beats the settings section."""
    (tmp_path / "logging.yaml").write_text("version: 1\nroot: {level: ERROR}\n")
    s = create_settings(defaults={"logging": {"version": 1, "root": {"level": "INFO"}}})

    assert resolve_logging_config(s, tmp_path)["root"]["level"] == "ERROR"


def test_resolution_falls_back_to_bundled_default():
    """With nothing configured, the bundled default (console + file) is used."""
    assert resolve_logging_config() == default_logging_config()


def test_default_config_keeps_traffic_off_the_console():
    """Instrument byte traffic (mastif.io) goes to the file only, not the operator's console."""
    io_logger = default_logging_config()["loggers"]["mastif.io"]

    assert (io_logger["handlers"], io_logger["propagate"]) == (["file"], False)


def test_broken_logging_yaml_is_config_error(tmp_path):
    """A logging.yaml that isn't a mapping is reported with its path."""
    (tmp_path / "logging.yaml").write_text("- just\n- a list\n")

    with pytest.raises(ConfigError, match="must be a mapping"):
        resolve_logging_config(config_dir=tmp_path)
