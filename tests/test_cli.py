"""olapbench end to end on DuckDB: gen, run, report, queries, and error exits."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from realtime_olap_benchmark.cli import main


def test_gen_run_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A full local run writes a valid result file and a report whose answer check passes."""
    data = tmp_path / "ssb"
    assert main(["gen", "--suite", "ssb", "--sf", "0.002", "--seed", "5", "--out", str(data)]) == 0
    out = capsys.readouterr().out
    assert "lineorder" in out
    assert "dataset digest" in out
    results = []
    for i in (1, 2):
        res = tmp_path / f"r{i}.json"
        code = main([
            "run", "--engine", "duckdb", "--suite", "ssb", "--data", str(data), "--out", str(res),
            "--cold-runs", "1", "--hot-runs", "2", "--threads", "1",
            "--db-path", str(tmp_path / f"db{i}.duckdb"), "--queries", "Q1.1,Q2.1,Q4.1",
        ])  # fmt: skip
        assert code == 0
        results.append(str(res))
    doc = json.loads(Path(results[0]).read_text(encoding="utf-8"))
    assert [q["id"] for q in doc["queries"]] == ["Q1.1", "Q2.1", "Q4.1"]
    assert doc["engine"] == "duckdb"
    assert doc["settings"]["threads"] == "1"
    capsys.readouterr()
    report = tmp_path / "report.md"
    assert main(["report", *results, "--out", str(report), "--strict"]) == 0
    text = report.read_text(encoding="utf-8")
    assert "| Q2.1 |" in text
    assert "geometric mean" in text
    assert "Answer check: 3 of 3" in text


def test_queries_listing(capsys: pytest.CaptureFixture[str]) -> None:
    """`olapbench queries` lists ids and titles."""
    assert main(["queries", "--suite", "tpch"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("Q01")
    assert len(out.splitlines()) == 8


def test_error_exits(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Bad input exits 2 with a message instead of a traceback."""
    assert main(["gen", "--suite", "ssb", "--sf", "11", "--out", str(tmp_path / "x")]) == 2
    assert main([
        "run", "--engine", "duckdb", "--suite", "ssb", "--data", str(tmp_path / "missing"),
        "--out", str(tmp_path / "r.json"), "--db-path", str(tmp_path / "d.duckdb"),
    ]) == 2  # fmt: skip
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    assert main(["report", str(bad)]) == 2
    assert main(["run", "--engine", "duckdb", "--suite", "ssb", "--data", ".", "--out", "r.json",
                 "--hot-runs", "0"]) == 2  # fmt: skip
    assert "error:" in capsys.readouterr().err


def test_wait_unreachable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`olapbench wait` gives up after its timeout when no server answers."""
    monkeypatch.setenv("CLICKHOUSE_URL", "http://127.0.0.1:9")
    assert main(["wait", "--engine", "clickhouse", "--timeout", "0"]) == 1
    assert "not ready" in capsys.readouterr().out
