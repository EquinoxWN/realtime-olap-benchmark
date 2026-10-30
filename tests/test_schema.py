"""DDL rendering per engine and the logical schemas."""

from __future__ import annotations

import pytest

from realtime_olap_benchmark.schema import (
    FACT_TABLES,
    SSB,
    TPCH,
    Kind,
    create_table_sql,
    suite_tables,
)

DIALECTS = ("duckdb", "clickhouse", "doris", "starrocks")


def test_suites_have_expected_tables() -> None:
    """SSB has its five tables; TPC-H has the seven its query subset reads."""
    assert [t.name for t in SSB] == ["dates", "customer", "supplier", "part", "lineorder"]
    assert [t.name for t in TPCH] == [
        "region", "nation", "supplier", "customer", "part", "orders", "lineitem",
    ]  # fmt: skip


def test_unknown_suite_rejected() -> None:
    """An unknown suite name is an error, not an empty list."""
    with pytest.raises(ValueError, match="unknown suite"):
        suite_tables("tpcds")


def test_text_columns_have_lengths() -> None:
    """Every text column carries a length, needed for VARCHAR(n) in Doris and StarRocks."""
    for t in (*SSB, *TPCH):
        for c in t.columns:
            assert (c.length > 0) == (c.kind is Kind.TEXT), (t.name, c.name)


@pytest.mark.parametrize("dialect", DIALECTS)
def test_every_column_rendered(dialect: str) -> None:
    """Each dialect's DDL names every column, NOT NULL."""
    for t in (*SSB, *TPCH):
        sql = create_table_sql(dialect, t)
        assert sql.startswith(f"CREATE TABLE {t.name} (")
        for c in t.columns:
            assert f"  {c.name} " in sql
        assert sql.count("NOT NULL") == len(t.columns)


def test_dialect_specific_clauses() -> None:
    """ClickHouse gets MergeTree ordered by the key; Doris and StarRocks a duplicate-key table."""
    lineitem = TPCH[-1]
    ch = create_table_sql("clickhouse", lineitem)
    assert "ENGINE = MergeTree ORDER BY (l_orderkey)" in ch
    assert "Decimal(15, 2)" in ch
    assert "String" in ch
    for d in ("doris", "starrocks"):
        sql = create_table_sql(d, lineitem)
        assert "DUPLICATE KEY(l_orderkey) DISTRIBUTED BY HASH(l_orderkey) BUCKETS 4" in sql
        assert '"replication_num" = "1"' in sql
        assert "VARCHAR(44)" in sql
    assert "BUCKETS 1" in create_table_sql("doris", TPCH[0])
    assert "ENGINE" not in create_table_sql("duckdb", lineitem)


def test_fact_tables_exist() -> None:
    """Every fact table named for bucketing is a real table."""
    names = {t.name for t in (*SSB, *TPCH)}
    assert names >= FACT_TABLES


def test_unknown_dialect_rejected() -> None:
    """A typo in a dialect name fails loudly."""
    with pytest.raises(ValueError, match="unknown dialect"):
        create_table_sql("postgres", SSB[0])
