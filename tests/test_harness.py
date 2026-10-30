"""The run loop with a scripted engine: run order, timing, failures and the row-count check."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from realtime_olap_benchmark.datagen import DataError
from realtime_olap_benchmark.engines.base import Cells, Engine, EngineError
from realtime_olap_benchmark.harness import Plan, load_data, machine, time_query, wait_ready
from realtime_olap_benchmark.queries import Query
from realtime_olap_benchmark.schema import Table

Q = Query("Q9", "test", "SELECT 9")


class Scripted(Engine):
    """An engine that records calls and returns scripted answers."""

    name = "scripted"
    deployment = "test double"

    def __init__(self, answers: list[list[Cells]] | None = None, fail_at: int = -1) -> None:
        """Answers are returned in turn (the last one repeats); fail_at raises on that call."""
        self.events: list[str] = []
        self.answers = answers or [[("1",)]]
        self.fail_at = fail_at
        self.calls = 0
        self.tables: dict[str, int] = {}
        self.ready_after = 0

    def connect(self) -> None:
        """Record."""
        self.events.append("connect")

    def close(self) -> None:
        """Record."""
        self.events.append("close")

    def ready(self) -> bool:
        """Ready after a number of polls."""
        self.ready_after -= 1
        return self.ready_after < 0

    def version(self) -> str:
        """Fixed version."""
        return "0"

    def settings(self) -> dict[str, str]:
        """No settings."""
        return {}

    @property
    def cold_method(self) -> str:
        """Fixed text."""
        return "scripted reset"

    def recreate(self, tables: Sequence[Table]) -> None:
        """Remember table names."""
        self.tables = {t.name: 0 for t in tables}

    def load(self, table: Table, path: Path) -> None:
        """Count data lines of the file."""
        self.tables[table.name] = len(path.read_text(encoding="utf-8").splitlines()) - 1

    def count(self, table: str) -> int:
        """Loaded rows."""
        return self.tables[table]

    def cold_reset(self) -> None:
        """Record."""
        self.events.append("reset")

    def query(self, sql: str) -> list[Cells]:
        """Scripted answer, or a failure on the chosen call."""
        i = self.calls
        self.calls += 1
        self.events.append("query")
        if i == self.fail_at:
            raise EngineError("boom")
        return self.answers[min(i, len(self.answers) - 1)]


def test_run_order_and_counts() -> None:
    """Cold runs each follow a reset; warm-up runs are not timed; hot runs are timed."""
    e = Scripted()
    t = [0.0]

    def clock() -> float:
        """Advance 4 ms per reading pair."""
        t[0] += 0.002
        return t[0]

    r = time_query(e, Q, Plan(cold_runs=2, warmup_runs=1, hot_runs=3), clock)
    assert e.events == ["reset", "query", "reset", "query", "query", "query", "query", "query"]
    assert r.status == "ok"
    assert len(r.cold_ms) == 2
    assert len(r.hot_ms) == 3
    assert all(abs(ms - 2.0) < 1e-6 for ms in [*r.cold_ms, *r.hot_ms])
    assert r.rows == 1
    assert r.answer == [["1"]]


def test_failure_recorded_not_raised() -> None:
    """A failing query is reported with its error; the run continues with the next query."""
    r = time_query(Scripted(fail_at=1), Q, Plan(1, 0, 2))
    assert r.status == "error"
    assert "boom" in r.error
    assert r.hot_ms == []


def test_changed_answer_is_an_error() -> None:
    """If an engine returns different rows on a later run, the query is marked failed."""
    r = time_query(Scripted(answers=[[("1",)], [("2",)]]), Q, Plan(1, 0, 1))
    assert r.status == "error"
    assert "answer changed" in r.error


def test_answer_truncated_to_limit() -> None:
    """Only the first 1,000 answer rows are stored, but the full count is kept."""
    big: list[Cells] = [(str(i),) for i in range(1500)]
    r = time_query(Scripted(answers=[big]), Q, Plan(0, 0, 1))
    assert r.rows == 1500
    assert len(r.answer) == 1000


@pytest.mark.parametrize(
    ("cold", "warm", "hot"), [(-1, 0, 1), (0, -1, 1), (0, 0, 0), (51, 0, 1), (0, 0, 51)]
)
def test_plan_bounds(cold: int, warm: int, hot: int) -> None:
    """Run counts are bounded and at least one hot run is required."""
    with pytest.raises(ValueError, match="must be between"):
        Plan(cold, warm, hot)


def test_load_checks_row_counts(ssb_dir: Path) -> None:
    """Loading compares each table's count with the manifest."""
    e = Scripted()
    seconds, rows = load_data(e, "ssb", ssb_dir)
    assert set(seconds) == set(rows) == set(e.tables)
    assert e.tables == rows

    class Lossy(Scripted):
        """Loses one row of lineorder."""

        def count(self, table: str) -> int:
            """One row short for lineorder."""
            return self.tables[table] - (table == "lineorder")

    with pytest.raises(DataError, match="lineorder has"):
        load_data(Lossy(), "ssb", ssb_dir)


def test_load_rejects_wrong_suite(ssb_dir: Path) -> None:
    """SSB files cannot be loaded as TPC-H."""
    with pytest.raises(DataError, match="not tpch"):
        load_data(Scripted(), "tpch", ssb_dir)


def test_wait_ready() -> None:
    """Polling stops when the engine is ready, or reports failure after the timeout."""
    e = Scripted()
    e.ready_after = 2
    assert wait_ready(e, timeout_s=5, interval_s=0.01)
    e.ready_after = 10**6
    assert not wait_ready(e, timeout_s=0.05, interval_s=0.01)


def test_machine_info() -> None:
    """The machine block names OS, CPU, cores and Python."""
    m = machine()
    assert set(m) == {"os", "cpu", "logical_cpus", "python"}
    assert int(m["logical_cpus"]) >= 1
