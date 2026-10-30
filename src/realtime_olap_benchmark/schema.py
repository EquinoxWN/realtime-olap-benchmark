"""Logical table schemas for the Star Schema Benchmark and TPC-H, rendered as DDL per engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    """Logical column types every engine can represent."""

    INT = "int"
    BIGINT = "bigint"
    DECIMAL = "decimal"  # DECIMAL(15,2), money and quantities
    DATE = "date"
    TEXT = "text"


@dataclass(frozen=True)
class Column:
    """One column: name, logical type and, for text, the longest value the generator writes."""

    name: str
    kind: Kind
    length: int = 0


@dataclass(frozen=True)
class Table:
    """One table: name, columns and the sort/distribution key (its first column)."""

    name: str
    columns: tuple[Column, ...]

    @property
    def key(self) -> str:
        """The first column, used as sort key (ClickHouse) and hash key (Doris, StarRocks)."""
        return self.columns[0].name

    @property
    def column_names(self) -> list[str]:
        """Column names in order."""
        return [c.name for c in self.columns]


def _i(name: str) -> Column:
    """INT column."""
    return Column(name, Kind.INT)


def _b(name: str) -> Column:
    """BIGINT column."""
    return Column(name, Kind.BIGINT)


def _d(name: str) -> Column:
    """DECIMAL(15,2) column."""
    return Column(name, Kind.DECIMAL)


def _dt(name: str) -> Column:
    """DATE column."""
    return Column(name, Kind.DATE)


def _t(name: str, length: int) -> Column:
    """Text column with a maximum length."""
    return Column(name, Kind.TEXT, length)


SSB: tuple[Table, ...] = (
    Table(
        "dates",
        (
            _i("d_datekey"),
            _dt("d_date"),
            _t("d_dayofweek", 9),
            _t("d_month", 9),
            _i("d_year"),
            _i("d_yearmonthnum"),
            _t("d_yearmonth", 7),
            _i("d_daynuminweek"),
            _i("d_daynuminmonth"),
            _i("d_monthnuminyear"),
            _i("d_weeknuminyear"),
        ),
    ),
    Table(
        "customer",
        (
            _i("c_custkey"),
            _t("c_name", 25),
            _t("c_address", 25),
            _t("c_city", 10),
            _t("c_nation", 15),
            _t("c_region", 12),
            _t("c_phone", 15),
            _t("c_mktsegment", 10),
        ),
    ),
    Table(
        "supplier",
        (
            _i("s_suppkey"),
            _t("s_name", 25),
            _t("s_address", 25),
            _t("s_city", 10),
            _t("s_nation", 15),
            _t("s_region", 12),
            _t("s_phone", 15),
        ),
    ),
    Table(
        "part",
        (
            _i("p_partkey"),
            _t("p_name", 22),
            _t("p_mfgr", 6),
            _t("p_category", 7),
            _t("p_brand1", 9),
            _t("p_color", 11),
            _t("p_type", 25),
            _i("p_size"),
            _t("p_container", 10),
        ),
    ),
    Table(
        "lineorder",
        (
            _b("lo_orderkey"),
            _i("lo_linenumber"),
            _i("lo_custkey"),
            _i("lo_partkey"),
            _i("lo_suppkey"),
            _i("lo_orderdate"),
            _t("lo_orderpriority", 15),
            _i("lo_shippriority"),
            _i("lo_quantity"),
            _i("lo_extendedprice"),
            _i("lo_ordtotalprice"),
            _i("lo_discount"),
            _i("lo_revenue"),
            _i("lo_supplycost"),
            _i("lo_tax"),
            _i("lo_commitdate"),
            _t("lo_shipmode", 10),
        ),
    ),
)

# TPC-H tables read by the M1 query subset; partsupp is not generated because no query reads it.
TPCH: tuple[Table, ...] = (
    Table("region", (_i("r_regionkey"), _t("r_name", 25), _t("r_comment", 152))),
    Table(
        "nation",
        (_i("n_nationkey"), _t("n_name", 25), _i("n_regionkey"), _t("n_comment", 152)),
    ),
    Table(
        "supplier",
        (
            _i("s_suppkey"),
            _t("s_name", 25),
            _t("s_address", 40),
            _i("s_nationkey"),
            _t("s_phone", 15),
            _d("s_acctbal"),
            _t("s_comment", 101),
        ),
    ),
    Table(
        "customer",
        (
            _i("c_custkey"),
            _t("c_name", 25),
            _t("c_address", 40),
            _i("c_nationkey"),
            _t("c_phone", 15),
            _d("c_acctbal"),
            _t("c_mktsegment", 10),
            _t("c_comment", 117),
        ),
    ),
    Table(
        "part",
        (
            _i("p_partkey"),
            _t("p_name", 55),
            _t("p_mfgr", 25),
            _t("p_brand", 10),
            _t("p_type", 25),
            _i("p_size"),
            _t("p_container", 10),
            _d("p_retailprice"),
            _t("p_comment", 23),
        ),
    ),
    Table(
        "orders",
        (
            _b("o_orderkey"),
            _i("o_custkey"),
            _t("o_orderstatus", 1),
            _d("o_totalprice"),
            _dt("o_orderdate"),
            _t("o_orderpriority", 15),
            _t("o_clerk", 15),
            _i("o_shippriority"),
            _t("o_comment", 79),
        ),
    ),
    Table(
        "lineitem",
        (
            _b("l_orderkey"),
            _i("l_partkey"),
            _i("l_suppkey"),
            _i("l_linenumber"),
            _d("l_quantity"),
            _d("l_extendedprice"),
            _d("l_discount"),
            _d("l_tax"),
            _t("l_returnflag", 1),
            _t("l_linestatus", 1),
            _dt("l_shipdate"),
            _dt("l_commitdate"),
            _dt("l_receiptdate"),
            _t("l_shipinstruct", 25),
            _t("l_shipmode", 10),
            _t("l_comment", 44),
        ),
    ),
)

SUITES: dict[str, tuple[Table, ...]] = {"ssb": SSB, "tpch": TPCH}


def suite_tables(suite: str) -> tuple[Table, ...]:
    """Tables of a suite; ValueError for an unknown suite."""
    try:
        return SUITES[suite]
    except KeyError:
        raise ValueError(f"unknown suite {suite!r}; choose one of {sorted(SUITES)}") from None


# Fact tables get several buckets in Doris and StarRocks so scans can use more than one core.
FACT_TABLES = frozenset({"lineorder", "orders", "lineitem"})
FACT_BUCKETS = 4

_DUCKDB = {
    Kind.INT: "INTEGER",
    Kind.BIGINT: "BIGINT",
    Kind.DECIMAL: "DECIMAL(15,2)",
    Kind.DATE: "DATE",
}
_CLICKHOUSE = {
    Kind.INT: "Int32",
    Kind.BIGINT: "Int64",
    Kind.DECIMAL: "Decimal(15, 2)",
    Kind.DATE: "Date",
}
_MYSQL = {Kind.INT: "INT", Kind.BIGINT: "BIGINT", Kind.DECIMAL: "DECIMAL(15,2)", Kind.DATE: "DATE"}


def _type(dialect: str, col: Column) -> str:
    """Physical type of a column in one dialect."""
    if dialect == "duckdb":
        return "VARCHAR" if col.kind is Kind.TEXT else _DUCKDB[col.kind]
    if dialect == "clickhouse":
        return "String" if col.kind is Kind.TEXT else _CLICKHOUSE[col.kind]
    if dialect in ("doris", "starrocks"):
        return f"VARCHAR({col.length})" if col.kind is Kind.TEXT else _MYSQL[col.kind]
    raise ValueError(f"unknown dialect {dialect!r}")


def create_table_sql(dialect: str, table: Table) -> str:
    """CREATE TABLE statement for one table in one engine's dialect (single replica, no tuning)."""
    cols = ",\n  ".join(f"{c.name} {_type(dialect, c)} NOT NULL" for c in table.columns)
    head = f"CREATE TABLE {table.name} (\n  {cols}\n)"
    if dialect == "duckdb":
        return head
    if dialect == "clickhouse":
        return f"{head} ENGINE = MergeTree ORDER BY ({table.key})"
    if dialect in ("doris", "starrocks"):
        buckets = FACT_BUCKETS if table.name in FACT_TABLES else 1
        return (
            f"{head} DUPLICATE KEY({table.key}) DISTRIBUTED BY HASH({table.key}) BUCKETS {buckets} "
            'PROPERTIES ("replication_num" = "1")'
        )
    raise ValueError(f"unknown dialect {dialect!r}")
