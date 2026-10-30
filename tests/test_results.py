"""Result file statistics, round trip and schema validation."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest

from realtime_olap_benchmark.results import (
    ResultError,
    RunResult,
    from_dict,
    geomean,
    load,
    save,
    summarize,
)


def test_summarize() -> None:
    """Median, extremes, sample standard deviation and coefficient of variation."""
    s = summarize([10.0, 12.0, 11.0, 30.0, 9.0])
    assert s.median_ms == 11.0
    assert (s.min_ms, s.max_ms) == (9.0, 30.0)
    assert math.isclose(s.stdev_ms, 8.7920, rel_tol=1e-4)  # sqrt(309.2 / 4)
    assert math.isclose(s.cv, s.stdev_ms / 14.4)
    one = summarize([5.0])
    assert (one.median_ms, one.stdev_ms, one.cv) == (5.0, 0.0, 0.0)


@pytest.mark.parametrize("bad", [[], [-1.0], [float("nan")], [float("inf")]])
def test_summarize_rejects(bad: list[float]) -> None:
    """Empty, negative or non-finite timings are refused."""
    with pytest.raises(ValueError, match=r"samples|finite"):
        summarize(bad)


def test_geomean() -> None:
    """Geometric mean; 0 when undefined."""
    assert math.isclose(geomean([1.0, 100.0]), 10.0)
    assert geomean([]) == 0.0
    assert geomean([1.0, 0.0]) == 0.0


def test_round_trip(ssb_result: RunResult, tmp_path: Path) -> None:
    """A saved result loads back equal, with summaries added for readers."""
    path = tmp_path / "r.json"
    save(ssb_result, path)
    back = load(path)
    assert back == ssb_result
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["queries"][0]["hot"]["median_ms"] > 0
    assert raw["schema_version"] == 1


def _mutations() -> list[tuple[str, Any]]:
    """(description, function that breaks a valid document)."""

    def set_(path: list[Any], value: Any) -> Any:
        """Set a nested key."""

        def f(d: dict[str, Any]) -> None:
            """Apply."""
            target = d
            for p in path[:-1]:
                target = target[p]
            target[path[-1]] = value

        return f

    return [
        ("schema version", set_(["schema_version"], 2)),
        ("suite", set_(["suite"], "tpcds")),
        ("status", set_(["queries", 0, "status"], "maybe")),
        ("negative timing", set_(["queries", 0, "hot_ms"], [-1.0])),
        ("bool timing", set_(["queries", 0, "hot_ms"], [True])),
        ("ok without hot runs", set_(["queries", 0, "hot_ms"], [])),
        ("answer type", set_(["queries", 0, "answer"], [[1]])),
        ("answer too long", set_(["queries", 0, "answer"], [["x"]] * 1001)),
        ("missing key", lambda d: d.pop("engine")),
        ("settings value", set_(["settings", "x"], 1)),
        ("rows bool", set_(["rows", "dates"], True)),
        ("duplicate ids", lambda d: d["queries"].append(copy.deepcopy(d["queries"][0]))),
        ("not an object", None),
    ]


@pytest.mark.parametrize(("name", "mutate"), _mutations())
def test_validation_rejects(ssb_result: RunResult, name: str, mutate: Any) -> None:
    """Each kind of malformed document is a ResultError."""
    doc: Any = json.loads(json.dumps(ssb_result.to_dict()))
    if mutate is None:
        doc = [doc]
    else:
        mutate(doc)
    with pytest.raises(ResultError):
        from_dict(doc)


def test_load_rejects_non_json(tmp_path: Path) -> None:
    """A file that is not JSON is a ResultError."""
    p = tmp_path / "x.json"
    p.write_text("{nope", encoding="utf-8")
    with pytest.raises(ResultError, match="not JSON"):
        load(p)
