"""Engine adapters: value formatting, DuckDB cold reset, ClickHouse over a fake HTTP server,
and the Doris/StarRocks loader (batches, types) without a server."""

from __future__ import annotations

import datetime as dt
import threading
import urllib.parse
from collections.abc import Iterator
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from realtime_olap_benchmark.engines import ENGINES, make_engine
from realtime_olap_benchmark.engines.base import EngineError, cell
from realtime_olap_benchmark.engines.clickhouse import ClickHouseEngine, parse_tsv, unescape_tsv
from realtime_olap_benchmark.engines.duck import DuckDBEngine
from realtime_olap_benchmark.engines.mysqlfamily import (
    DorisEngine,
    StarRocksEngine,
    batches,
    convert,
)
from realtime_olap_benchmark.schema import SSB, TPCH, Kind


def test_cell_formatting() -> None:
    """Every driver's value types become the same text."""
    assert cell(None) == "NULL"
    assert cell(Decimal("1.50")) == "1.50"
    assert cell(Decimal("1E+2")) == "100"
    assert cell(dt.date(1995, 3, 15)) == "1995-03-15"
    assert cell(2.5) == "2.5"
    assert cell(10**20) == "100000000000000000000"
    assert cell(b"abc") == "abc"


def test_registry() -> None:
    """Every listed engine can be built; unknown names fail."""
    for name in ENGINES:
        assert make_engine(name).name == name
    with pytest.raises(ValueError, match="unknown engine"):
        make_engine("pinot")


def test_duckdb_cold_reset_reopens(tmp_path: Path, ssb_dir: Path) -> None:
    """Data survives a cold reset (the file is reopened) and settings are reported."""
    with DuckDBEngine(tmp_path / "d.duckdb", threads=1) as e:
        e.recreate(SSB)
        e.load(SSB[0], ssb_dir / "dates.tbl")
        e.post_load(SSB)
        before = e.con
        e.cold_reset()
        assert e.con is not before
        assert e.count("dates") == 2557
        assert e.settings()["threads"] == "1"
        assert e.version().startswith("v")
        assert e.ready()
    with pytest.raises(EngineError, match="not connected"):
        _ = e.con


def test_duckdb_query_error(tmp_path: Path) -> None:
    """A bad query becomes EngineError; thread counts are bounded."""
    with DuckDBEngine(tmp_path / "e.duckdb") as e, pytest.raises(EngineError):
        e.query("SELECT * FROM missing_table")
    with pytest.raises(ValueError, match="threads"):
        DuckDBEngine(tmp_path / "f.duckdb", threads=0)


def test_tsv_unescape() -> None:
    """ClickHouse TabSeparated escapes are undone."""
    assert unescape_tsv(r"a\tb\\c\nd") == "a\tb\\c\nd"
    assert parse_tsv("1\tx\n2\ty\n") == [("1", "x"), ("2", "y")]


class _Fake(BaseHTTPRequestHandler):
    """A ClickHouse-like HTTP endpoint that records requests."""

    seen: ClassVar[list[tuple[dict[str, list[str]], str, str, str]]] = []

    def do_POST(self) -> None:
        """Answer a few statements; SYSTEM DROP of one cache fails like an older server."""
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        sql = params.get("query", [body])[0]
        _Fake.seen.append(
            (params, body, self.headers["X-ClickHouse-User"], self.headers["X-ClickHouse-Key"])
        )
        status, out = 200, ""
        if sql.startswith("SELECT 1"):
            out = "1\n"
        elif "version()" in sql:
            out = "26.3.60.2\n"
        elif "count()" in sql:
            out = "42\n"
        elif "PRIMARY INDEX CACHE" in sql:
            status, out = 400, "Code: 62. Syntax error"
        elif "FORMAT TabSeparated" in sql:
            out = "JAPAN\t1.50\n"
        self.send_response(status)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out.encode())

    def log_message(self, format: str, *args: object) -> None:
        """Silence the default request log."""


@pytest.fixture
def fake_clickhouse(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A fake server on a free local port, with credentials in the environment."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("CLICKHOUSE_USER", "bench")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "s3cret")
    _Fake.seen = []
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_clickhouse_protocol(fake_clickhouse: str, tmp_path: Path) -> None:
    """Credentials travel in headers (never the URL), queries use database bench and TSV,
    loads stream the file with the pipe delimiter, and unsupported cache drops are skipped."""
    e = ClickHouseEngine(fake_clickhouse)
    assert e.ready()
    assert e.version() == "26.3.60.2"
    assert e.query("SELECT n_name, x FROM nation") == [("JAPAN", "1.50")]
    data = tmp_path / "region.tbl"
    data.write_text("r_regionkey|r_name|r_comment\n0|AFRICA|x\n", encoding="utf-8")
    e.load(TPCH[0], data)
    assert e.count("region") == 42
    e.cold_reset()
    assert "PRIMARY INDEX CACHE" not in e.cold_method
    assert "MARK CACHE" in e.cold_method
    for params, _, user, key in _Fake.seen:
        assert (user, key) == ("bench", "s3cret")
        assert "s3cret" not in str(params)
        assert params["use_query_cache"] == ["0"]
    load = next(s for s in _Fake.seen if "INSERT" in s[0].get("query", [""])[0])
    assert load[0]["format_csv_delimiter"] == ["|"]
    assert load[0]["database"] == ["bench"]
    assert load[1].startswith("r_regionkey|")
    tsv = next(s for s in _Fake.seen if "FORMAT TabSeparated" in s[1])
    assert tsv[1].endswith("FORMAT TabSeparated")


def test_clickhouse_errors(fake_clickhouse: str) -> None:
    """HTTP errors carry the server message; an unreachable server is not ready."""
    e = ClickHouseEngine(fake_clickhouse)
    with pytest.raises(EngineError, match="HTTP 400"):
        e._request("SYSTEM DROP PRIMARY INDEX CACHE")
    assert not ClickHouseEngine("http://127.0.0.1:9", timeout=2).ready()
    with pytest.raises(ValueError, match="http"):
        ClickHouseEngine("file:///etc/passwd")


def test_convert_and_batches(tmp_path: Path) -> None:
    """CSV fields become ints and Decimals; files are read in bounded batches with the header checked."""
    assert convert(Kind.INT, "7") == 7
    assert convert(Kind.DECIMAL, "-0.05") == Decimal("-0.05")
    assert convert(Kind.DATE, "1995-03-15") == "1995-03-15"
    region = TPCH[0]
    p = tmp_path / "region.tbl"
    p.write_text(
        "r_regionkey|r_name|r_comment\n" + "".join(f"{i}|R{i}|c\n" for i in range(7)),
        encoding="utf-8",
    )
    got = list(batches(region, p, size=3))
    assert [len(b) for b in got] == [3, 3, 1]
    assert got[0][0] == (0, "R0", "c")
    p.write_text("a|b|c\n", encoding="utf-8")
    with pytest.raises(EngineError, match="header"):
        list(batches(region, p))
    p.write_text("r_regionkey|r_name|r_comment\n1|x\n", encoding="utf-8")
    with pytest.raises(EngineError, match="fields"):
        list(batches(region, p))


def test_mysql_family_without_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connection settings come from the environment; an absent server is reported, not hung on."""
    monkeypatch.setenv("DORIS_PORT", "9")
    d = DorisEngine()
    assert (d.host, d.port, d.user) == ("127.0.0.1", 9, "root")
    assert not d.ready()
    with pytest.raises(EngineError, match="cannot connect"):
        d.connect()
    with pytest.raises(EngineError, match="not connected"):
        d.query("SELECT 1")
    s = StarRocksEngine()
    assert s.version_sql == "SELECT current_version()"
    assert "ANALYZE" in s.analyze_sql
    assert "page caches are not cleared" in s.cold_method
    assert s.settings()["replication_num"] == "1"
