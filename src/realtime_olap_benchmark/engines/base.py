"""The engine interface the harness drives, and helpers shared by every engine."""

from __future__ import annotations

import datetime as dt
import os
from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Self

from realtime_olap_benchmark.schema import Table

Cells = tuple[str, ...]


class EngineError(RuntimeError):
    """An engine could not be reached or rejected a statement."""


def cell(value: object) -> str:
    """One result value as text, the same way for every engine (dates ISO, decimals plain)."""
    if value is None:
        return "NULL"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def cells(rows: Sequence[Sequence[object]]) -> list[Cells]:
    """Every row of a result as text cells."""
    return [tuple(cell(v) for v in row) for row in rows]


def env(name: str, default: str) -> str:
    """An environment setting with a default."""
    return os.environ.get(name, default)


def port_from_env(name: str, default: str) -> int:
    """A TCP port from the environment, with a clear error when it is not 1..65535."""
    raw = env(name, default)
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise EngineError(f"{name}={raw!r} is not a TCP port (1..65535)")
    return int(raw)


class Engine(ABC):
    """One analytics engine: connect, create and load tables, reset caches, run a query."""

    name: str = ""
    # How the engine runs (embedded in the harness process, or a server in a container).
    deployment: str = ""

    @abstractmethod
    def connect(self) -> None:
        """Open the connection (or the embedded database)."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection; safe to call twice."""

    @abstractmethod
    def ready(self) -> bool:
        """True when the engine accepts queries (servers: a backend is alive)."""

    @abstractmethod
    def version(self) -> str:
        """The engine's version string, as reported by the engine itself."""

    @abstractmethod
    def settings(self) -> dict[str, str]:
        """Settings that shape the measurement (threads, caches, buckets...)."""

    @property
    @abstractmethod
    def cold_method(self) -> str:
        """What cold_reset() clears, in words, for the results file."""

    @abstractmethod
    def recreate(self, tables: Sequence[Table]) -> None:
        """Drop and create the benchmark database and its tables."""

    @abstractmethod
    def load(self, table: Table, path: Path) -> None:
        """Load one pipe-delimited file with a header row into a table."""

    @abstractmethod
    def count(self, table: str) -> int:
        """Row count of a table."""

    def post_load(self, tables: Sequence[Table]) -> list[str]:
        """Work after loading (statistics); returns warnings that did not stop the run."""
        del tables
        return []

    @abstractmethod
    def cold_reset(self) -> None:
        """Clear the engine's own caches before a cold run."""

    @abstractmethod
    def query(self, sql: str) -> list[Cells]:
        """Run one SELECT and return every row as text cells."""

    def __enter__(self) -> Self:
        """Connect on entry."""
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        """Close on exit."""
        self.close()
