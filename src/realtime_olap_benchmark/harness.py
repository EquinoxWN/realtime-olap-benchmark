"""The run loop: create and load tables, verify row counts, then time each query cold and hot."""

from __future__ import annotations

import datetime as dt
import os
import platform
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from realtime_olap_benchmark.datagen import DataError, load_manifest
from realtime_olap_benchmark.engines.base import Engine, EngineError
from realtime_olap_benchmark.queries import Query
from realtime_olap_benchmark.results import MAX_ANSWER_ROWS, QueryResult, RunResult
from realtime_olap_benchmark.schema import suite_tables

MAX_RUNS = 50


@dataclass(frozen=True)
class Plan:
    """How often each query runs: cold runs (cache reset before each), warm-up, hot runs."""

    cold_runs: int = 3
    warmup_runs: int = 1
    hot_runs: int = 5
    drop_os_cache: bool = False

    def __post_init__(self) -> None:
        """Bounded counts; at least one hot run so every query has a hot median."""
        for name, v, lo in (
            ("cold_runs", self.cold_runs, 0),
            ("warmup_runs", self.warmup_runs, 0),
            ("hot_runs", self.hot_runs, 1),
        ):
            if not lo <= v <= MAX_RUNS:
                raise ValueError(f"{name} must be between {lo} and {MAX_RUNS}, got {v}")


def cpu_name() -> str:
    """CPU model from /proc/cpuinfo on Linux, else what the platform module reports."""
    info = Path("/proc/cpuinfo")
    if sys.platform == "linux" and info.is_file():
        for line in info.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or platform.machine()


def machine() -> dict[str, str]:
    """Where the run happened."""
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": cpu_name(),
        "logical_cpus": str(os.cpu_count() or 0),
        "python": platform.python_version(),
    }


def drop_os_cache() -> None:
    """Flush and drop the Linux page cache (needs passwordless sudo, as on CI runners)."""
    if sys.platform != "linux":
        raise EngineError("--drop-os-cache works on Linux only")
    subprocess.run(
        ["/usr/bin/sudo", "-n", "/bin/sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"],
        check=True,
        timeout=120,
    )


def load_data(
    engine: Engine, suite: str, data_dir: Path
) -> tuple[dict[str, float], dict[str, int]]:
    """Recreate the tables, load every file and check each table's row count against the manifest."""
    manifest = load_manifest(data_dir)
    if manifest.suite != suite:
        raise DataError(f"{data_dir} holds {manifest.suite} data, not {suite}")
    tables = suite_tables(suite)
    engine.recreate(tables)
    seconds: dict[str, float] = {}
    for t in tables:
        t0 = time.perf_counter()
        engine.load(t, data_dir / f"{t.name}.tbl")
        seconds[t.name] = round(time.perf_counter() - t0, 3)
        got = engine.count(t.name)
        if got != manifest.rows[t.name]:
            raise DataError(
                f"{engine.name}: {t.name} has {got} rows, manifest says {manifest.rows[t.name]}"
            )
    return seconds, dict(manifest.rows)


def time_query(
    engine: Engine, query: Query, plan: Plan, clock: Callable[[], float] = time.perf_counter
) -> QueryResult:
    """Run one query cold (reset before each run), warm it up, then run it hot; record timings."""
    result = QueryResult(id=query.id, status="ok")
    answer: list[tuple[str, ...]] | None = None

    def timed() -> float:
        """One execution in milliseconds; every execution must return the same rows."""
        nonlocal answer
        t0 = clock()
        rows = engine.query(query.sql)
        ms = (clock() - t0) * 1000.0
        if answer is None:
            answer = rows
        elif rows != answer:
            raise EngineError(f"{query.id}: answer changed between runs")
        return ms

    try:
        for _ in range(plan.cold_runs):
            if plan.drop_os_cache:
                drop_os_cache()
            engine.cold_reset()
            result.cold_ms.append(round(timed(), 3))
        for _ in range(plan.warmup_runs):
            timed()
        for _ in range(plan.hot_runs):
            result.hot_ms.append(round(timed(), 3))
    except (EngineError, subprocess.SubprocessError, OSError) as e:
        result.status, result.error = "error", str(e)[:500]
        result.hot_ms = []
    if answer is not None:
        result.rows = len(answer)
        result.answer = [list(r) for r in answer[:MAX_ANSWER_ROWS]]
    return result


def run(
    engine: Engine,
    suite: str,
    data_dir: Path,
    queries: list[Query],
    plan: Plan,
    progress: Callable[[str], None] = lambda s: None,
) -> RunResult:
    """Load the data into a connected engine and time every query."""
    started = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    manifest = load_manifest(data_dir, verify=False)
    load_seconds, rows = load_data(engine, suite, data_dir)
    progress(
        f"{engine.name}: loaded {sum(rows.values()):,} rows in {sum(load_seconds.values()):.1f} s"
    )
    warnings = engine.post_load(suite_tables(suite))
    results = []
    for q in queries:
        r = time_query(engine, q, plan)
        hot = f"hot median {r.hot.median_ms:.1f} ms" if r.hot else f"error: {r.error[:120]}"
        progress(f"{engine.name} {suite} {q.id}: {hot}")
        results.append(r)
    return RunResult(
        engine=engine.name,
        engine_version=engine.version(),
        deployment=engine.deployment,
        settings={**engine.settings(), "drop_os_cache": str(plan.drop_os_cache).lower()},
        cold_method=engine.cold_method
        + ("; Linux page cache dropped" if plan.drop_os_cache else ""),
        suite=suite,
        scale_factor=manifest.scale_factor,
        seed=manifest.seed,
        data_digest=manifest.digest,
        machine=machine(),
        started_at=started,
        cold_runs=plan.cold_runs,
        hot_runs=plan.hot_runs,
        warmup_runs=plan.warmup_runs,
        load_seconds=load_seconds,
        rows=rows,
        warnings=warnings,
        queries=results,
    )


def wait_ready(engine: Engine, timeout_s: float, interval_s: float = 3.0) -> bool:
    """Poll engine.ready() until it is true or the timeout passes."""
    deadline = time.monotonic() + timeout_s
    while True:
        if engine.ready():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval_s)
