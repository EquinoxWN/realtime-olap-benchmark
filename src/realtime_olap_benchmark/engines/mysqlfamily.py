"""Apache Doris and StarRocks over the MySQL protocol (PyMySQL), loaded with batched INSERTs."""

from __future__ import annotations

import csv
from collections.abc import Iterator, Sequence
from decimal import Decimal
from pathlib import Path

import pymysql

from realtime_olap_benchmark.engines.base import (
    Cells,
    Engine,
    EngineError,
    cells,
    env,
    port_from_env,
)
from realtime_olap_benchmark.schema import Kind, Table, create_table_sql

DATABASE = "bench"
BATCH_ROWS = 5000


def convert(kind: Kind, text: str) -> object:
    """A CSV field as the Python value PyMySQL should send for a column kind."""
    if kind in (Kind.INT, Kind.BIGINT):
        return int(text)
    if kind is Kind.DECIMAL:
        return Decimal(text)
    return text


def batches(table: Table, path: Path, size: int = BATCH_ROWS) -> Iterator[list[tuple[object, ...]]]:
    """Rows of a pipe-delimited file (header checked) in batches of typed tuples."""
    kinds = [c.kind for c in table.columns]
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="|", quoting=csv.QUOTE_NONE)
        header = next(reader, None)
        if header != table.column_names:
            raise EngineError(f"{path.name}: header does not match table {table.name}")
        batch: list[tuple[object, ...]] = []
        for row in reader:
            if len(row) != len(kinds):
                raise EngineError(f"{path.name}: row with {len(row)} fields")
            batch.append(tuple(convert(k, v) for k, v in zip(kinds, row, strict=True)))
            if len(batch) >= size:
                yield batch
                batch = []
        if batch:
            yield batch


def backends_ready(names: Sequence[str], rows: Sequence[Sequence[object]]) -> bool:
    """A backend can hold tables once it is alive and its disks report capacity."""
    if "alive" not in names:
        return False
    alive = names.index("alive")
    cap = names.index("totalcapacity") if "totalcapacity" in names else None
    for r in rows:
        if str(r[alive]).lower() != "true":
            continue
        if cap is None:
            return True
        parts = str(r[cap]).split()
        try:
            if parts and float(parts[0]) > 0:
                return True
        except ValueError:
            continue
    return False


class MySQLFamilyEngine(Engine):
    """Shared code for Doris and StarRocks; subclasses set names, version query and settings."""

    prefix = ""  # environment variable prefix, e.g. DORIS
    version_sql = "SELECT version()"
    session_settings: tuple[str, ...] = ()
    analyze_sql = ""

    def __init__(self, timeout: int = 600) -> None:
        """Read host, port, user and password from <PREFIX>_HOST/_PORT/_USER/_PASSWORD."""
        self.host = env(f"{self.prefix}_HOST", "127.0.0.1")
        self.port = port_from_env(f"{self.prefix}_PORT", "9030")
        self.user = env(f"{self.prefix}_USER", "root")
        self.password = env(f"{self.prefix}_PASSWORD", "")
        self.timeout = timeout
        self._con: pymysql.connections.Connection[pymysql.cursors.Cursor] | None = None
        self.applied: list[str] = []
        self.rejected: list[str] = []

    def connect(self) -> None:
        """Open the connection and apply the session settings that this version accepts."""
        try:
            self._con = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                autocommit=True,
                connect_timeout=10,
                read_timeout=self.timeout,
                write_timeout=self.timeout,
                charset="utf8mb4",
            )
        except pymysql.MySQLError as e:
            raise EngineError(f"{self.name}: cannot connect to {self.host}:{self.port}: {e}") from e
        self.applied, self.rejected = [], []
        for stmt in self.session_settings:
            try:
                self._exec(stmt)
                self.applied.append(stmt)
            except EngineError:
                self.rejected.append(stmt)

    def close(self) -> None:
        """Close the connection."""
        if self._con is not None:
            self._con.close()
            self._con = None

    def _exec(self, sql: str, args: Sequence[object] | None = None) -> list[tuple[object, ...]]:
        """Run one statement and fetch its rows."""
        if self._con is None:
            raise EngineError(f"{self.name}: not connected")
        try:
            with self._con.cursor() as cur:
                cur.execute(sql, args)
                return list(cur.fetchall())
        except pymysql.MySQLError as e:
            raise EngineError(f"{self.name}: {e}") from e

    def ready(self) -> bool:
        """True when a backend is alive and has reported disk capacity."""
        try:
            if self._con is None:
                self.connect()
            if self._con is None:
                return False
            with self._con.cursor() as cur:
                cur.execute("SHOW BACKENDS")
                names = [d[0].lower() for d in cur.description or ()]
                rows = cur.fetchall()
        except (EngineError, pymysql.MySQLError):
            self.close()
            return False
        return backends_ready(names, rows)

    def version(self) -> str:
        """Version string from the engine."""
        return str(self._exec(self.version_sql)[0][0])

    def settings(self) -> dict[str, str]:
        """Session settings applied or rejected, plus the table layout."""
        return {
            "session_settings_applied": "; ".join(self.applied) or "none",
            "session_settings_rejected": "; ".join(self.rejected) or "none",
            "table_model": "DUPLICATE KEY(first column), HASH buckets: 4 for fact tables, 1 otherwise",
            "replication_num": "1",
            "load": f"INSERT ... VALUES in batches of {BATCH_ROWS} rows over the MySQL protocol",
        }

    @property
    def cold_method(self) -> str:
        """No SQL command clears the backends' page caches; result caches are off for the session."""
        return "session result caches off; backend page caches are not cleared by SQL"

    def recreate(self, tables: Sequence[Table]) -> None:
        """Drop and create the database and its tables."""
        self._exec(f"DROP DATABASE IF EXISTS {DATABASE}")
        self._exec(f"CREATE DATABASE {DATABASE}")
        self._exec(f"USE {DATABASE}")
        for t in tables:
            self._exec(create_table_sql(self.name, t))

    def load(self, table: Table, path: Path) -> None:
        """INSERT the file in batches (PyMySQL folds each batch into multi-row statements)."""
        if self._con is None:
            raise EngineError(f"{self.name}: not connected")
        cols = ", ".join(table.column_names)
        marks = ", ".join(["%s"] * len(table.columns))
        sql = f"INSERT INTO {table.name} ({cols}) VALUES ({marks})"
        try:
            with self._con.cursor() as cur:
                for batch in batches(table, path):
                    cur.executemany(sql, batch)
        except pymysql.MySQLError as e:
            raise EngineError(f"{self.name}: loading {table.name}: {e}") from e

    def count(self, table: str) -> int:
        """Row count."""
        return int(str(self._exec(f"SELECT count(*) FROM {table}")[0][0]))

    def post_load(self, tables: Sequence[Table]) -> list[str]:
        """Collect column statistics for the optimizer; failures become warnings."""
        warnings = []
        for t in tables:
            try:
                self._exec(self.analyze_sql.format(table=t.name))
            except EngineError as e:
                warnings.append(str(e)[:300])
        return warnings

    def cold_reset(self) -> None:
        """Nothing SQL can clear beyond the session settings applied at connect."""

    def query(self, sql: str) -> list[Cells]:
        """Run a SELECT and fetch every row."""
        return cells(self._exec(sql))


class DorisEngine(MySQLFamilyEngine):
    """Apache Doris (FE and BE containers); DORIS_HOST, DORIS_PORT (9030), DORIS_USER, DORIS_PASSWORD."""

    name = "doris"
    deployment = "FE and BE servers in containers (apache/doris fe and be images)"
    prefix = "DORIS"
    version_sql = "SELECT @@version_comment"
    session_settings = ("SET enable_sql_cache = false", "SET enable_query_cache = false")
    analyze_sql = "ANALYZE TABLE {table} WITH SYNC"


class StarRocksEngine(MySQLFamilyEngine):
    """StarRocks (all-in-one container); STARROCKS_HOST, STARROCKS_PORT (9030), _USER, _PASSWORD."""

    name = "starrocks"
    deployment = "FE and BE in one container (starrocks/allin1-ubuntu)"
    prefix = "STARROCKS"
    version_sql = "SELECT current_version()"
    session_settings = ("SET enable_query_cache = false",)
    analyze_sql = "ANALYZE FULL TABLE {table}"
