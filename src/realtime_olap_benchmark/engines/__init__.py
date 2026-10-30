"""Engine registry: names the CLI accepts and how to build each engine."""

from __future__ import annotations

from pathlib import Path

from realtime_olap_benchmark.engines.base import Engine, EngineError
from realtime_olap_benchmark.engines.clickhouse import ClickHouseEngine
from realtime_olap_benchmark.engines.duck import DuckDBEngine
from realtime_olap_benchmark.engines.mysqlfamily import DorisEngine, StarRocksEngine

ENGINES = ("duckdb", "clickhouse", "doris", "starrocks")

__all__ = ["ENGINES", "Engine", "EngineError", "make_engine"]


def make_engine(name: str, db_path: Path | None = None, threads: int | None = None) -> Engine:
    """Build an engine by name; db_path and threads apply to DuckDB only."""
    if name == "duckdb":
        return DuckDBEngine(db_path or Path(".tmp/duckdb/bench.duckdb"), threads)
    if name == "clickhouse":
        return ClickHouseEngine()
    if name == "doris":
        return DorisEngine()
    if name == "starrocks":
        return StarRocksEngine()
    raise ValueError(f"unknown engine {name!r}; choose one of {list(ENGINES)}")
