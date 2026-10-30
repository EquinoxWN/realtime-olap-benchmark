"""The query set: SQL files shipped with the package, with optional per-engine overrides."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from importlib.resources.abc import Traversable

from realtime_olap_benchmark.schema import suite_tables

_NAME = re.compile(r"^q\d+(_\d+)?\.sql$")
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|truncate|grant|revoke|attach|copy|set|system|kill)\b",
    re.IGNORECASE,
)


class QueryError(ValueError):
    """A query file is missing or is not a single read-only SELECT."""


@dataclass(frozen=True)
class Query:
    """One benchmark query: id (Q1.1, Q01...), description and SQL without the trailing semicolon."""

    id: str
    title: str
    sql: str


def query_id(filename: str) -> str:
    """Display id from a file name: q1_1.sql -> Q1.1, q06.sql -> Q06."""
    return "Q" + filename.removesuffix(".sql")[1:].replace("_", ".")


def check_sql(sql: str) -> str:
    """Return the statement without comments or trailing semicolon; reject anything not read-only."""
    body = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    ).strip()
    body = body.removesuffix(";").strip()
    if ";" in body:
        raise QueryError("a query file must hold exactly one statement")
    if not re.match(r"(?is)^(select|with)\b", body):
        raise QueryError("a query must start with SELECT or WITH")
    if m := _FORBIDDEN.search(body):
        raise QueryError(f"a benchmark query must be read-only; found {m.group(0)!r}")
    return body


def _title(sql: str) -> str:
    """First comment line, used as the query's description."""
    for line in sql.splitlines():
        if line.startswith("--"):
            return line.removeprefix("--").strip()
    return ""


def load_queries(
    suite: str, engine: str | None = None, root: Traversable | None = None
) -> list[Query]:
    """All queries of a suite in id order; <root>/<suite>/<engine>/<file> overrides the shared file."""
    suite_tables(suite)  # validates the suite name
    root = root or resources.files("realtime_olap_benchmark").joinpath("queries")
    base = root.joinpath(suite)
    names = sorted(p.name for p in base.iterdir() if p.is_file() and _NAME.match(p.name))
    if not names:
        raise QueryError(f"no queries found for suite {suite}")
    out = []
    for name in names:
        src = base.joinpath(name)
        if engine is not None:
            override = base.joinpath(engine, name)
            if override.is_file():
                src = override
        text = src.read_text(encoding="utf-8")
        out.append(Query(query_id(name), _title(text), check_sql(text)))
    return out


def select_queries(queries: list[Query], wanted: str | None) -> list[Query]:
    """Keep the queries named in a comma-separated list (all when wanted is empty)."""
    if not wanted:
        return queries
    ids = [w.strip() for w in wanted.split(",") if w.strip()]
    known = {q.id for q in queries}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise QueryError(f"unknown query ids {unknown}; known: {sorted(known)}")
    return [q for q in queries if q.id in ids]
