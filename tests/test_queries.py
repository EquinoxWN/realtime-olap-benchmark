"""The query set: what ships, the read-only check, ids and per-engine overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from realtime_olap_benchmark.queries import (
    QueryError,
    check_sql,
    load_queries,
    query_id,
    select_queries,
)

SSB_IDS = ["Q1.1", "Q1.2", "Q1.3", "Q2.1", "Q2.2", "Q2.3", "Q3.1", "Q3.2", "Q3.3", "Q3.4",
           "Q4.1", "Q4.2", "Q4.3"]  # fmt: skip
TPCH_IDS = ["Q01", "Q03", "Q05", "Q06", "Q10", "Q12", "Q14", "Q18"]


def test_shipped_query_sets() -> None:
    """All 13 SSB queries and the 8-query TPC-H subset ship, in id order, each with a title."""
    ssb, tpch = load_queries("ssb"), load_queries("tpch")
    assert [q.id for q in ssb] == SSB_IDS
    assert [q.id for q in tpch] == TPCH_IDS
    for q in (*ssb, *tpch):
        assert q.title
        assert q.sql.upper().startswith("SELECT")
        assert not q.sql.endswith(";")


def test_query_ids() -> None:
    """File names map to display ids."""
    assert query_id("q1_1.sql") == "Q1.1"
    assert query_id("q06.sql") == "Q06"


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE lineitem",
        "SELECT 1; SELECT 2",
        "SELECT 1; DROP TABLE x",
        "WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x",
        "SELECT * FROM t; -- trailing",
        "update t set a = 1",
        "  ",
    ],
)
def test_check_sql_rejects(sql: str) -> None:
    """Anything but one read-only SELECT is refused."""
    with pytest.raises(QueryError):
        check_sql(sql)


def test_check_sql_strips_comments() -> None:
    """Leading comment lines and the final semicolon are removed."""
    assert check_sql("-- title\nSELECT 1;\n") == "SELECT 1"


def test_override_per_engine(tmp_path: Path) -> None:
    """queries/<suite>/<engine>/<file> replaces the shared file for that engine only."""
    (tmp_path / "ssb" / "clickhouse").mkdir(parents=True)
    (tmp_path / "ssb" / "q1_1.sql").write_text("-- shared\nSELECT 1;\n", encoding="utf-8")
    (tmp_path / "ssb" / "q1_2.sql").write_text("-- two\nSELECT 2;\n", encoding="utf-8")
    (tmp_path / "ssb" / "clickhouse" / "q1_1.sql").write_text(
        "-- ch\nSELECT 11;\n", encoding="utf-8"
    )
    (tmp_path / "ssb" / "notes.txt").write_text("ignored", encoding="utf-8")
    shared = load_queries("ssb", "duckdb", root=tmp_path)
    ch = load_queries("ssb", "clickhouse", root=tmp_path)
    assert [q.sql for q in shared] == ["SELECT 1", "SELECT 2"]
    assert [q.sql for q in ch] == ["SELECT 11", "SELECT 2"]
    assert ch[0].title == "ch"


def test_empty_suite_dir(tmp_path: Path) -> None:
    """A suite without query files is an error."""
    (tmp_path / "tpch").mkdir()
    with pytest.raises(QueryError, match="no queries"):
        load_queries("tpch", root=tmp_path)


def test_select_queries() -> None:
    """A comma list keeps those queries; unknown ids are an error; empty keeps all."""
    qs = load_queries("tpch")
    assert [q.id for q in select_queries(qs, "Q06, Q01")] == ["Q01", "Q06"]
    assert select_queries(qs, None) == qs
    with pytest.raises(QueryError, match="unknown query ids"):
        select_queries(qs, "Q02")
