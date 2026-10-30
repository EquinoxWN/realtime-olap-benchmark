"""DuckDB, embedded in the harness process (no server, so no container is needed)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import duckdb

from realtime_olap_benchmark.engines.base import Cells, Engine, EngineError, cells
from realtime_olap_benchmark.schema import Table, create_table_sql


def _quote(path: Path) -> str:
    """A file path as an SQL string literal."""
    return "'" + str(path.resolve()).replace("'", "''") + "'"


class DuckDBEngine(Engine):
    """DuckDB on a database file; a cold run reopens the file so DuckDB's buffer pool is empty."""

    name = "duckdb"
    deployment = "embedded in the harness process (Python package)"

    def __init__(self, db_path: Path, threads: int | None = None) -> None:
        """Remember where the database file lives and how many threads to use (None = DuckDB default)."""
        if threads is not None and not 1 <= threads <= 256:
            raise ValueError("threads must be between 1 and 256")
        self.db_path, self.threads = db_path, threads
        self._con: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> None:
        """Open (or create) the database file."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        config: dict[str, str | bool | int | float | list[str]] = {}
        if self.threads:
            config["threads"] = self.threads
        self._con = duckdb.connect(str(self.db_path), config=config)

    def close(self) -> None:
        """Close the database file."""
        if self._con is not None:
            self._con.close()
            self._con = None

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        """The open connection; EngineError when not connected."""
        if self._con is None:
            raise EngineError("duckdb: not connected")
        return self._con

    def _one(self, sql: str) -> object:
        """First value of a one-row result."""
        row = self.con.execute(sql).fetchone()
        if row is None:
            raise EngineError(f"duckdb: no result for {sql!r}")
        return row[0]

    def ready(self) -> bool:
        """Embedded: ready once connected."""
        return self._one("SELECT 1") == 1

    def version(self) -> str:
        """DuckDB's own version string."""
        return str(self._one("SELECT version()"))

    def settings(self) -> dict[str, str]:
        """Threads and memory limit in effect."""
        return {
            "threads": str(self._one("SELECT current_setting('threads')")),
            "memory_limit": str(self._one("SELECT current_setting('memory_limit')")),
            "storage": "database file, tables loaded with COPY",
        }

    @property
    def cold_method(self) -> str:
        """Reopening drops DuckDB's buffer pool; the OS page cache is separate."""
        return "close and reopen the database file (empties DuckDB's buffer pool)"

    def recreate(self, tables: Sequence[Table]) -> None:
        """Drop and create every table."""
        for t in tables:
            self.con.execute(f"DROP TABLE IF EXISTS {t.name}")
            self.con.execute(create_table_sql("duckdb", t))

    def load(self, table: Table, path: Path) -> None:
        """COPY the file into the table (types come from the table)."""
        self.con.execute(f"COPY {table.name} FROM {_quote(path)} (HEADER, DELIMITER '|', QUOTE '')")

    def count(self, table: str) -> int:
        """Row count."""
        return int(str(self._one(f"SELECT count(*) FROM {table}")))

    def post_load(self, tables: Sequence[Table]) -> list[str]:
        """CHECKPOINT so the data is in the file, not the write-ahead log."""
        del tables
        self.con.execute("CHECKPOINT")
        return []

    def cold_reset(self) -> None:
        """Reopen the database file."""
        self.close()
        self.connect()

    def query(self, sql: str) -> list[Cells]:
        """Run a SELECT and fetch every row."""
        try:
            return cells(self.con.execute(sql).fetchall())
        except duckdb.Error as e:
            raise EngineError(f"duckdb: {e}") from e
