"""ClickHouse over its HTTP interface (standard library only, credentials in headers)."""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from pathlib import Path

from realtime_olap_benchmark.engines.base import Cells, Engine, EngineError, env
from realtime_olap_benchmark.schema import Table, create_table_sql

DATABASE = "bench"
MAX_RESPONSE = 256 * 1024 * 1024
# Caches cleared before a cold run; ones a server version does not know are skipped.
DROP_CACHES = (
    "MARK CACHE",
    "UNCOMPRESSED CACHE",
    "QUERY CACHE",
    "QUERY CONDITION CACHE",
    "PRIMARY INDEX CACHE",
    "COMPILED EXPRESSION CACHE",
)


def unescape_tsv(field: str) -> str:
    """Undo ClickHouse TabSeparated escaping."""
    if "\\" not in field:
        return field
    out, i = [], 0
    table = {"t": "\t", "n": "\n", "r": "\r", "0": "\0", "\\": "\\", "'": "'", "b": "\b", "f": "\f"}
    while i < len(field):
        ch = field[i]
        if ch == "\\" and i + 1 < len(field):
            out.append(table.get(field[i + 1], field[i + 1]))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_tsv(body: str) -> list[Cells]:
    """Rows of a TabSeparated response."""
    return [tuple(unescape_tsv(f) for f in line.split("\t")) for line in body.splitlines() if line]


class ClickHouseEngine(Engine):
    """ClickHouse server; settings come from CLICKHOUSE_URL, CLICKHOUSE_USER, CLICKHOUSE_PASSWORD."""

    name = "clickhouse"
    deployment = "server in a container (clickhouse/clickhouse-server)"

    def __init__(self, url: str | None = None, timeout: float = 600.0) -> None:
        """Validate the URL (http or https only) and read credentials from the environment."""
        self.url = (url or env("CLICKHOUSE_URL", "http://127.0.0.1:8123")).rstrip("/")
        if urllib.parse.urlsplit(self.url).scheme not in ("http", "https"):
            raise ValueError("CLICKHOUSE_URL must be an http:// or https:// URL")
        self.user = env("CLICKHOUSE_USER", "default")
        self.password = env("CLICKHOUSE_PASSWORD", "")
        self.timeout = timeout
        self._drops: list[str] | None = None

    def _request(
        self, sql: str, data: bytes | None = None, database: bool = True, **params: str
    ) -> str:
        """POST one statement; the body is the SQL, or the data when the SQL is in the URL."""
        query = {"use_query_cache": "0", **params}
        if database:
            query["database"] = DATABASE
        body = sql.encode()
        if data is not None:
            query["query"] = sql
            body = data
        req = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
            f"{self.url}/?{urllib.parse.urlencode(query)}",
            data=body,
            method="POST",
            headers={"X-ClickHouse-User": self.user, "X-ClickHouse-Key": self.password},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                raw: bytes = resp.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as e:
            detail = e.read(2000).decode("utf-8", "replace").strip()
            raise EngineError(f"clickhouse: HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, OSError) as e:
            raise EngineError(f"clickhouse: {e}") from e
        if len(raw) > MAX_RESPONSE:
            raise EngineError("clickhouse: response larger than 256 MiB")
        return raw.decode("utf-8")

    def connect(self) -> None:
        """HTTP is stateless: nothing to open."""

    def close(self) -> None:
        """HTTP is stateless: nothing to close."""

    def ready(self) -> bool:
        """True when SELECT 1 answers."""
        try:
            return self._request("SELECT 1", database=False).strip() == "1"
        except EngineError:
            return False

    def version(self) -> str:
        """Server version."""
        return self._request("SELECT version()", database=False).strip()

    def settings(self) -> dict[str, str]:
        """Threads and table engine."""
        threads = self._request("SELECT getSetting('max_threads')", database=False).strip()
        return {
            "max_threads": threads,
            "table_engine": "MergeTree ORDER BY first column",
            "use_query_cache": "0",
        }

    @property
    def cold_method(self) -> str:
        """Which SYSTEM DROP commands run before a cold query."""
        drops = self._drops if self._drops is not None else list(DROP_CACHES)
        return "SYSTEM DROP " + ", ".join(drops)

    def recreate(self, tables: Sequence[Table]) -> None:
        """Drop and create the database and its tables."""
        self._request(f"DROP DATABASE IF EXISTS {DATABASE}", database=False)
        self._request(f"CREATE DATABASE {DATABASE}", database=False)
        for t in tables:
            self._request(create_table_sql("clickhouse", t))

    def load(self, table: Table, path: Path) -> None:
        """INSERT the file as CSVWithNames with a pipe delimiter."""
        self._request(
            f"INSERT INTO {table.name} FORMAT CSVWithNames",
            data=path.read_bytes(),
            format_csv_delimiter="|",
        )

    def count(self, table: str) -> int:
        """Row count."""
        return int(self._request(f"SELECT count() FROM {table}").strip())

    def post_load(self, tables: Sequence[Table]) -> list[str]:
        """Merge parts so every run reads the same layout."""
        for t in tables:
            self._request(f"OPTIMIZE TABLE {t.name} FINAL")
        return []

    def cold_reset(self) -> None:
        """Drop the server's caches (the first call finds which ones this version supports)."""
        if self._drops is None:
            supported = []
            for cache in DROP_CACHES:
                try:
                    self._request(f"SYSTEM DROP {cache}", database=False)
                    supported.append(cache)
                except EngineError:
                    continue
            self._drops = supported
            return
        for cache in self._drops:
            self._request(f"SYSTEM DROP {cache}", database=False)

    def query(self, sql: str) -> list[Cells]:
        """Run a SELECT and parse the TabSeparated answer."""
        return parse_tsv(self._request(f"{sql}\nFORMAT TabSeparated"))
