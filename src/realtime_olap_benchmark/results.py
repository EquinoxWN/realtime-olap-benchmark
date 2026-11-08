"""The result file: one JSON document per engine and suite, validated on write and on read."""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from realtime_olap_benchmark.fsutil import write_text_atomic

SCHEMA_VERSION = 1
MAX_ANSWER_ROWS = 1000


class ResultError(ValueError):
    """A result file does not match the schema."""


@dataclass(frozen=True)
class Summary:
    """Median, spread and extremes of a list of timings in milliseconds."""

    median_ms: float
    min_ms: float
    max_ms: float
    stdev_ms: float
    cv: float  # coefficient of variation, stdev / mean


def summarize(samples: list[float]) -> Summary:
    """Summary of timings; stdev and cv are 0 for fewer than two samples."""
    if not samples:
        raise ValueError("no samples")
    if any(not math.isfinite(s) or s < 0 for s in samples):
        raise ValueError("timings must be finite and non-negative")
    sd = statistics.stdev(samples) if len(samples) > 1 else 0.0
    mean = statistics.fmean(samples)
    return Summary(
        median_ms=statistics.median(samples),
        min_ms=min(samples),
        max_ms=max(samples),
        stdev_ms=sd,
        cv=sd / mean if mean > 0 else 0.0,
    )


def geomean(values: list[float]) -> float:
    """Geometric mean of positive values (0 if any is not positive or the list is empty)."""
    if not values or any(v <= 0 for v in values):
        return 0.0
    return math.exp(statistics.fmean(math.log(v) for v in values))


@dataclass
class QueryResult:
    """Timings and answer of one query on one engine."""

    id: str
    status: str  # "ok" or "error"
    cold_ms: list[float] = field(default_factory=list)
    hot_ms: list[float] = field(default_factory=list)
    rows: int = 0
    answer: list[list[str]] = field(default_factory=list)
    error: str = ""

    @property
    def cold(self) -> Summary | None:
        """Summary of the cold runs, if any succeeded."""
        return summarize(self.cold_ms) if self.cold_ms else None

    @property
    def hot(self) -> Summary | None:
        """Summary of the hot runs, if any succeeded."""
        return summarize(self.hot_ms) if self.hot_ms else None


@dataclass
class RunResult:
    """Everything one `olapbench run` measured."""

    engine: str
    engine_version: str
    deployment: str
    settings: dict[str, str]
    cold_method: str
    suite: str
    scale_factor: float
    seed: int
    data_digest: str
    machine: dict[str, str]
    started_at: str
    cold_runs: int
    hot_runs: int
    warmup_runs: int
    load_seconds: dict[str, float]
    rows: dict[str, int]
    warnings: list[str]
    queries: list[QueryResult]
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Plain dict with summaries added for readers that do not recompute them."""
        d = asdict(self)
        for q, raw in zip(self.queries, d["queries"], strict=True):
            raw["cold"] = asdict(q.cold) if q.cold else None
            raw["hot"] = asdict(q.hot) if q.hot else None
        return d


def _req(d: dict[str, Any], key: str, typ: type | tuple[type, ...]) -> Any:
    """A required key of the given type."""
    if key not in d:
        raise ResultError(f"missing key {key!r}")
    v = d[key]
    if (isinstance(v, bool) and typ is not bool) or not isinstance(v, typ):
        raise ResultError(f"{key!r} has type {type(v).__name__}")
    return v


def _str_map(d: dict[str, Any], key: str, typ: type | tuple[type, ...]) -> dict[str, Any]:
    """A required mapping from strings to values of one type."""
    m = _req(d, key, dict)
    for k, v in m.items():
        if not isinstance(k, str) or not isinstance(v, typ) or isinstance(v, bool):
            raise ResultError(f"{key!r} has a bad entry {k!r}")
    return dict(m)


def _timings(d: dict[str, Any], key: str) -> list[float]:
    """A list of non-negative finite numbers."""
    v = _req(d, key, list)
    out = []
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0:
            raise ResultError(f"{key!r} holds a bad timing {x!r}")
        out.append(float(x))
    return out


def query_from_dict(d: dict[str, Any]) -> QueryResult:
    """Validate one query entry."""
    status = _req(d, "status", str)
    if status not in ("ok", "error"):
        raise ResultError(f"bad status {status!r}")
    answer = _req(d, "answer", list)
    if len(answer) > MAX_ANSWER_ROWS or not all(
        isinstance(r, list) and all(isinstance(c, str) for c in r) for r in answer
    ):
        raise ResultError("answer must be at most 1000 rows of strings")
    q = QueryResult(
        id=_req(d, "id", str),
        status=status,
        cold_ms=_timings(d, "cold_ms"),
        hot_ms=_timings(d, "hot_ms"),
        rows=_req(d, "rows", int),
        answer=answer,
        error=_req(d, "error", str),
    )
    if status == "ok" and not q.hot_ms:
        raise ResultError(f"{q.id}: status ok but no hot timings")
    return q


def from_dict(d: dict[str, Any]) -> RunResult:
    """Validate a parsed result document."""
    if not isinstance(d, dict):
        raise ResultError("a result file must hold a JSON object")
    version = _req(d, "schema_version", int)
    if version != SCHEMA_VERSION:
        raise ResultError(f"schema_version {version} is not {SCHEMA_VERSION}")
    queries = [query_from_dict(q) for q in _req(d, "queries", list)]
    if len({q.id for q in queries}) != len(queries):
        raise ResultError("duplicate query ids")
    r = RunResult(
        engine=_req(d, "engine", str),
        engine_version=_req(d, "engine_version", str),
        deployment=_req(d, "deployment", str),
        settings=_str_map(d, "settings", str),
        cold_method=_req(d, "cold_method", str),
        suite=_req(d, "suite", str),
        scale_factor=float(_req(d, "scale_factor", (int, float))),
        seed=_req(d, "seed", int),
        data_digest=_req(d, "data_digest", str),
        machine=_str_map(d, "machine", str),
        started_at=_req(d, "started_at", str),
        cold_runs=_req(d, "cold_runs", int),
        hot_runs=_req(d, "hot_runs", int),
        warmup_runs=_req(d, "warmup_runs", int),
        load_seconds={k: float(v) for k, v in _str_map(d, "load_seconds", (int, float)).items()},
        rows=_str_map(d, "rows", int),
        warnings=[str(w) for w in _req(d, "warnings", list)],
        queries=queries,
    )
    if r.suite not in ("ssb", "tpch"):
        raise ResultError(f"unknown suite {r.suite!r}")
    return r


def save(result: RunResult, path: Path) -> None:
    """Validate by round trip, then write the JSON file."""
    doc = result.to_dict()
    from_dict(json.loads(json.dumps(doc)))
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(doc, indent=1) + "\n")


def load(path: Path) -> RunResult:
    """Read and validate a result file (at most 64 MiB)."""
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ResultError(f"{path} is larger than 64 MiB")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ResultError(f"{path}: not JSON: {e}") from e
    return from_dict(doc)
