"""The cross-engine answer check."""

from __future__ import annotations

import copy

from realtime_olap_benchmark.answers import answers_equal, cells_equal, compare
from realtime_olap_benchmark.results import RunResult


def test_cells_equal() -> None:
    """Numbers compare within tolerance whatever their formatting; text compares exactly."""
    assert cells_equal("25.50", "25.5012")  # avg() scale differs between engines
    assert cells_equal("1E+2", "100")
    assert cells_equal("123456789012.34", "123456789012.35")
    assert not cells_equal("25.50", "25.60")
    assert not cells_equal("1000000", "1000100")
    assert cells_equal("JAPAN", " JAPAN ")
    assert not cells_equal("JAPAN", "CHINA")
    assert not cells_equal("1995-03-15", "1995-03-16")
    assert cells_equal("NaN", "NaN")  # non-finite values compare as text


def test_answers_equal_reports_first_difference() -> None:
    """Row count, column count and cell differences are described."""
    assert answers_equal([["a", "1"]], [["a", "1.000"]]) == ""
    assert "rows" in answers_equal([["a"]], [])
    assert "columns" in answers_equal([["a"]], [["a", "b"]])
    assert "row 1 column 1" in answers_equal([["a", "1"], ["b", "2"]], [["a", "1"], ["b", "3"]])


def _other(r: RunResult, engine: str) -> RunResult:
    """A copy of a result under another engine name."""
    o = copy.deepcopy(r)
    o.engine = engine
    return o


def test_compare_agreement(ssb_result: RunResult, tpch_result: RunResult) -> None:
    """Identical answers agree; each suite is compared with its own first run."""
    checked, bad = compare(
        [ssb_result, tpch_result, _other(ssb_result, "x"), _other(tpch_result, "y")]
    )
    assert checked == 21
    assert bad == []


def test_compare_finds_disagreement(ssb_result: RunResult) -> None:
    """A changed cell and a different dataset are both reported."""
    o = _other(ssb_result, "x")
    o.queries[0].answer = [["1"]]
    checked, bad = compare([ssb_result, o])
    assert checked == 13
    assert [(b.query, b.engine) for b in bad] == [("Q1.1", "x")]
    d = _other(ssb_result, "y")
    d.data_digest = "other"
    _, bad = compare([ssb_result, d])
    assert bad[0].detail == "different dataset"


def test_failed_queries_not_compared(ssb_result: RunResult) -> None:
    """A failed query on either side is skipped (the report lists failures separately)."""
    o = _other(ssb_result, "x")
    o.queries[0].status = "error"
    o.queries[0].answer = []
    checked, bad = compare([ssb_result, o])
    assert checked == 12
    assert bad == []


def test_large_sums_compare_within_relative_tolerance() -> None:
    """Large aggregates may differ by more than 0.01 in the last digits (float sums) and still agree."""
    assert cells_equal("123456789012.00", "123456789012.50")  # 4e-12 relative
    assert not cells_equal("123456789012", "123456989012")  # 1.6e-6 relative
