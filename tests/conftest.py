"""Shared fixtures: small seeded datasets and DuckDB results over them, built once per session."""

from __future__ import annotations

from pathlib import Path

import pytest

from realtime_olap_benchmark.datagen import generate
from realtime_olap_benchmark.engines.duck import DuckDBEngine
from realtime_olap_benchmark.harness import Plan, run
from realtime_olap_benchmark.queries import load_queries
from realtime_olap_benchmark.results import RunResult

SF = 0.02


@pytest.fixture(scope="session")
def ssb_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """SSB at scale factor 0.02 (about 120,000 lineorder rows)."""
    out = tmp_path_factory.mktemp("ssb")
    generate("ssb", SF, out, seed=7)
    return out


@pytest.fixture(scope="session")
def tpch_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """TPC-H at scale factor 0.02 (about 120,000 lineitem rows)."""
    out = tmp_path_factory.mktemp("tpch")
    generate("tpch", SF, out, seed=7)
    return out


def _duck_run(suite: str, data: Path, db: Path) -> RunResult:
    """Every query of a suite on DuckDB with one cold and two hot runs."""
    with DuckDBEngine(db, threads=2) as engine:
        return run(engine, suite, data, load_queries(suite), Plan(1, 0, 2))


@pytest.fixture(scope="session")
def ssb_result(ssb_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    """DuckDB result for the SSB fixture."""
    return _duck_run("ssb", ssb_dir, tmp_path_factory.mktemp("db") / "ssb.duckdb")


@pytest.fixture(scope="session")
def tpch_result(tpch_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    """DuckDB result for the TPC-H fixture."""
    return _duck_run("tpch", tpch_dir, tmp_path_factory.mktemp("db") / "tpch.duckdb")
