"""Query answers on DuckDB match a plain-Python recomputation from the generated files."""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from realtime_olap_benchmark.answers import answers_equal
from realtime_olap_benchmark.results import RunResult


def rows(path: Path) -> list[dict[str, str]]:
    """A generated table as dicts."""
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="|", quoting=csv.QUOTE_NONE))


def answer(result: RunResult, qid: str) -> list[list[str]]:
    """The answer DuckDB gave for a query."""
    q = next(q for q in result.queries if q.id == qid)
    assert q.status == "ok", q.error
    return q.answer


def test_every_query_ran(ssb_result: RunResult, tpch_result: RunResult) -> None:
    """All 21 queries succeed on DuckDB and most return rows at this scale."""
    for r in (ssb_result, tpch_result):
        assert all(q.status == "ok" for q in r.queries)
    non_empty = [q.id for q in (*ssb_result.queries, *tpch_result.queries) if q.rows > 0]
    assert len(non_empty) >= 17


def test_ssb_flight_1(ssb_dir: Path, ssb_result: RunResult) -> None:
    """Q1.1 to Q1.3 (revenue from discounts) equal a Python scan of lineorder and dates."""
    dates = {r["d_datekey"]: r for r in rows(ssb_dir / "dates.tbl")}
    lo = rows(ssb_dir / "lineorder.tbl")
    filters: dict[str, Callable[[dict[str, str], int, int], bool]] = {
        "Q1.1": lambda d, disc, q: d["d_year"] == "1993" and 1 <= disc <= 3 and q < 25,
        "Q1.2": lambda d, disc, q: (
            d["d_yearmonthnum"] == "199401" and 4 <= disc <= 6 and 26 <= q <= 35
        ),
        "Q1.3": lambda d, disc, q: (
            d["d_weeknuminyear"] == "6"
            and d["d_year"] == "1994"
            and 5 <= disc <= 7
            and 26 <= q <= 35
        ),
    }
    for qid, keep in filters.items():
        total: int = sum(
            int(r["lo_extendedprice"]) * int(r["lo_discount"])
            for r in lo
            if keep(dates[r["lo_orderdate"]], int(r["lo_discount"]), int(r["lo_quantity"]))
        )
        assert answer(ssb_result, qid) == [[str(total)]], qid


def test_ssb_q2_1(ssb_dir: Path, ssb_result: RunResult) -> None:
    """Q2.1 (revenue by year and brand) equals a Python group-by over four joined tables."""
    year = {r["d_datekey"]: r["d_year"] for r in rows(ssb_dir / "dates.tbl")}
    part = {r["p_partkey"]: r for r in rows(ssb_dir / "part.tbl")}
    supp = {r["s_suppkey"]: r for r in rows(ssb_dir / "supplier.tbl")}
    groups: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows(ssb_dir / "lineorder.tbl"):
        p, s = part[r["lo_partkey"]], supp[r["lo_suppkey"]]
        if p["p_category"] == "MFGR#12" and s["s_region"] == "AMERICA":
            groups[(year[r["lo_orderdate"]], p["p_brand1"])] += int(r["lo_revenue"])
    expected = [[str(v), y, b] for (y, b), v in sorted(groups.items())]
    assert expected
    assert answers_equal(answer(ssb_result, "Q2.1"), expected) == ""


def test_tpch_q1(tpch_dir: Path, tpch_result: RunResult) -> None:
    """TPC-H Q1 sums and counts per return flag and status equal a Python scan of lineitem."""
    acc: dict[tuple[str, str], list[Decimal]] = defaultdict(lambda: [Decimal(0)] * 5)
    for r in rows(tpch_dir / "lineitem.tbl"):
        if r["l_shipdate"] > "1998-09-02":
            continue
        q, p, d, t = (
            Decimal(r[k]) for k in ("l_quantity", "l_extendedprice", "l_discount", "l_tax")
        )
        a = acc[(r["l_returnflag"], r["l_linestatus"])]
        a[0] += q
        a[1] += p
        a[2] += p * (1 - d)
        a[3] += p * (1 - d) * (1 + t)
        a[4] += 1
    got = answer(tpch_result, "Q01")
    assert [g[:2] for g in got] == [list(k) for k in sorted(acc)]
    for g, k in zip(got, sorted(acc), strict=True):
        a = acc[k]
        expected = [*k, *(str(x) for x in a[:4])]
        assert answers_equal([g[:6]], [expected]) == ""
        assert g[9] == str(a[4])
        assert answers_equal([[g[6]]], [[str(a[0] / a[4])]]) == ""  # avg_qty


def test_tpch_q6_q14(tpch_dir: Path, tpch_result: RunResult) -> None:
    """Q6 (forecast revenue) and Q14 (promotion share) equal Python recomputations."""
    ptype = {r["p_partkey"]: r["p_type"] for r in rows(tpch_dir / "part.tbl")}
    q6, promo, total = Decimal(0), Decimal(0), Decimal(0)
    for r in rows(tpch_dir / "lineitem.tbl"):
        price, disc = Decimal(r["l_extendedprice"]), Decimal(r["l_discount"])
        if ("1994-01-01" <= r["l_shipdate"] < "1995-01-01" and Decimal("0.05") <= disc <= Decimal("0.07")
                and Decimal(r["l_quantity"]) < 24):  # fmt: skip
            q6 += price * disc
        if "1995-09-01" <= r["l_shipdate"] < "1995-10-01":
            rev = price * (1 - disc)
            total += rev
            if ptype[r["l_partkey"]].startswith("PROMO"):
                promo += rev
    assert answers_equal(answer(tpch_result, "Q06"), [[str(q6)]]) == ""
    assert answers_equal(answer(tpch_result, "Q14"), [[str(100 * promo / total)]]) == ""


def test_tpch_q12(tpch_dir: Path, tpch_result: RunResult) -> None:
    """Q12 high and low priority line counts per ship mode equal a Python join of orders and lineitem."""
    prio = {r["o_orderkey"]: r["o_orderpriority"] for r in rows(tpch_dir / "orders.tbl")}
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows(tpch_dir / "lineitem.tbl"):
        if (r["l_shipmode"] in ("MAIL", "SHIP") and r["l_commitdate"] < r["l_receiptdate"]
                and r["l_shipdate"] < r["l_commitdate"] and "1994-01-01" <= r["l_receiptdate"] < "1995-01-01"):  # fmt: skip
            high = prio[r["l_orderkey"]] in ("1-URGENT", "2-HIGH")
            counts[r["l_shipmode"]][0 if high else 1] += 1
    expected = [[m, str(h), str(lo)] for m, (h, lo) in sorted(counts.items())]
    assert answer(tpch_result, "Q12") == expected
