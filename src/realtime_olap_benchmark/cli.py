"""olapbench: generate data, run the query set on one engine, and report results."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from realtime_olap_benchmark.answers import compare
from realtime_olap_benchmark.datagen import DataError, generate
from realtime_olap_benchmark.engines import ENGINES, EngineError, make_engine
from realtime_olap_benchmark.harness import Plan, run, wait_ready
from realtime_olap_benchmark.queries import QueryError, load_queries, select_queries
from realtime_olap_benchmark.report import render
from realtime_olap_benchmark.results import ResultError, load, save
from realtime_olap_benchmark.schema import SUITES


def _gen(a: argparse.Namespace) -> int:
    """olapbench gen."""
    t0 = time.perf_counter()
    m = generate(a.suite, a.sf, a.out, a.seed)
    total = sum(m.rows.values())
    print(
        f"{a.suite} sf={a.sf:g} seed={a.seed}: {total:,} rows in {time.perf_counter() - t0:.1f} s"
    )
    for table, n in m.rows.items():
        print(f"  {table:<10} {n:>10,} rows  sha256 {m.sha256[table][:12]}")
    print(f"dataset digest {m.digest[:16]}")
    return 0


def _run(a: argparse.Namespace) -> int:
    """olapbench run."""
    queries = select_queries(load_queries(a.suite, a.engine), a.queries)
    plan = Plan(a.cold_runs, a.warmup_runs, a.hot_runs, a.drop_os_cache)
    with make_engine(a.engine, a.db_path, a.threads) as engine:
        result = run(engine, a.suite, a.data, queries, plan, progress=print)
    save(result, a.out)
    failed = [q.id for q in result.queries if q.status != "ok"]
    print(f"wrote {a.out}: {len(result.queries) - len(failed)} of {len(result.queries)} queries ok")
    return 1 if failed else 0


def _report(a: argparse.Namespace) -> int:
    """olapbench report."""
    runs = [load(p) for p in a.results]
    text = render(runs)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
    print(text, end="")
    _, bad = compare(runs)
    return 1 if bad and a.strict else 0


def _wait(a: argparse.Namespace) -> int:
    """olapbench wait."""
    engine = make_engine(a.engine)
    try:
        ok = wait_ready(engine, a.timeout)
    finally:
        engine.close()
    print(f"{a.engine}: {'ready' if ok else f'not ready after {a.timeout:.0f} s'}")
    return 0 if ok else 1


def _queries(a: argparse.Namespace) -> int:
    """olapbench queries."""
    for q in load_queries(a.suite, a.engine):
        print(f"{q.id:<6} {q.title}")
    return 0


def parser() -> argparse.ArgumentParser:
    """The command-line interface."""
    p = argparse.ArgumentParser(prog="olapbench", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="generate a seeded SSB or TPC-H dataset")
    g.add_argument("--suite", choices=sorted(SUITES), required=True)
    g.add_argument("--sf", type=float, default=0.1, help="scale factor, 0 < sf <= 10")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--out", type=Path, required=True)
    g.set_defaults(fn=_gen)

    r = sub.add_parser("run", help="load a dataset into one engine and time every query")
    r.add_argument("--engine", choices=ENGINES, required=True)
    r.add_argument("--suite", choices=sorted(SUITES), required=True)
    r.add_argument("--data", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--queries", help="comma-separated ids, e.g. Q1.1,Q2.1 (default: all)")
    r.add_argument("--cold-runs", type=int, default=3)
    r.add_argument("--warmup-runs", type=int, default=1)
    r.add_argument("--hot-runs", type=int, default=5)
    r.add_argument(
        "--drop-os-cache",
        action="store_true",
        help="Linux: drop the page cache before each cold run",
    )
    r.add_argument(
        "--db-path", type=Path, help="DuckDB database file (default .tmp/duckdb/bench.duckdb)"
    )
    r.add_argument("--threads", type=int, help="DuckDB threads (default: DuckDB's choice)")
    r.set_defaults(fn=_run)

    rep = sub.add_parser("report", help="markdown tables and the cross-engine answer check")
    rep.add_argument("results", type=Path, nargs="+")
    rep.add_argument("--out", type=Path)
    rep.add_argument("--strict", action="store_true", help="exit 1 when answers disagree")
    rep.set_defaults(fn=_report)

    w = sub.add_parser("wait", help="wait until a server engine accepts queries")
    w.add_argument("--engine", choices=ENGINES, required=True)
    w.add_argument("--timeout", type=float, default=600.0)
    w.set_defaults(fn=_wait)

    q = sub.add_parser("queries", help="list the query set")
    q.add_argument("--suite", choices=sorted(SUITES), required=True)
    q.add_argument("--engine", choices=ENGINES)
    q.set_defaults(fn=_queries)
    return p


def main(argv: list[str] | None = None) -> int:
    """Entry point; 2 on bad input, data, results or an unreachable engine."""
    a = parser().parse_args(argv)
    try:
        code: int = a.fn(a)
    except (DataError, QueryError, ResultError, EngineError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())
