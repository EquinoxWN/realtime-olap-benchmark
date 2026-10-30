"""The seeded generator: determinism, sizes, value domains, consistency and the manifest check."""

from __future__ import annotations

import csv
import datetime as dt
import json
import random
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pytest

from realtime_olap_benchmark.datagen import (
    CURRENT,
    DataError,
    check_scale,
    generate,
    load_manifest,
    money,
    retail_cents,
    scaled,
    ssb_city,
    supplier_for,
)


def rows(path: Path) -> list[dict[str, str]]:
    """A generated table as dicts keyed by column name."""
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="|", quoting=csv.QUOTE_NONE))


def test_same_seed_same_files(tmp_path: Path) -> None:
    """The same suite, scale and seed give byte-identical files; another seed does not."""
    a = generate("ssb", 0.002, tmp_path / "a", seed=1)
    b = generate("ssb", 0.002, tmp_path / "b", seed=1)
    c = generate("ssb", 0.002, tmp_path / "c", seed=2)
    assert a.sha256 == b.sha256
    assert a.digest == b.digest
    assert a.sha256["lineorder"] != c.sha256["lineorder"]
    assert a.sha256["dates"] == c.sha256["dates"]  # the calendar does not depend on the seed


def test_tpch_deterministic(tmp_path: Path) -> None:
    """TPC-H generation is deterministic too (orders and lineitem are written together)."""
    a = generate("tpch", 0.002, tmp_path / "a", seed=3)
    b = generate("tpch", 0.002, tmp_path / "b", seed=3)
    assert a.sha256 == b.sha256


def test_ssb_sizes(ssb_dir: Path) -> None:
    """Row counts follow the scale factor: 30,000 customers, 2,000 suppliers, ~6M lines per SF."""
    m = load_manifest(ssb_dir)
    assert m.rows["dates"] == 2557  # 1992-01-01 to 1998-12-31
    assert m.rows["customer"] == scaled(30_000, 0.02) == 600
    assert m.rows["supplier"] == 40
    assert m.rows["part"] == 4000
    assert 4.0 * 30_000 * 0.95 < m.rows["lineorder"] < 4.0 * 30_000 * 1.05


def test_ssb_value_domains(ssb_dir: Path) -> None:
    """Brands, categories, cities and lineorder measures stay inside the SSB domains."""
    for p in rows(ssb_dir / "part.tbl"):
        assert p["p_brand1"].startswith(p["p_category"])
        assert p["p_category"].startswith(p["p_mfgr"])
        assert 1 <= int(p["p_brand1"][7:]) <= 40
    for c in rows(ssb_dir / "customer.tbl"):
        assert len(c["c_city"]) == 10
        assert c["c_city"][:9].rstrip() == c["c_nation"][:9].rstrip()
    lo = rows(ssb_dir / "lineorder.tbl")
    totals: dict[str, int] = defaultdict(int)
    for r in lo:
        assert 1 <= int(r["lo_quantity"]) <= 50
        assert 0 <= int(r["lo_discount"]) <= 10
        assert 0 <= int(r["lo_tax"]) <= 8
        ext = int(r["lo_extendedprice"])
        assert int(r["lo_revenue"]) == ext * (100 - int(r["lo_discount"])) // 100
        assert 19920101 <= int(r["lo_orderdate"]) <= 19980802
        assert int(r["lo_commitdate"]) > int(r["lo_orderdate"])
        totals[r["lo_orderkey"]] += ext
    for r in lo:
        assert int(r["lo_ordtotalprice"]) == totals[r["lo_orderkey"]]


def test_ssb_dates_calendar(ssb_dir: Path) -> None:
    """The date table is a real calendar: Sunday = 1, weeks of 7 days, 'Dec1997' style months."""
    d = {r["d_datekey"]: r for r in rows(ssb_dir / "dates.tbl")}
    assert d["19971207"]["d_dayofweek"] == "Sunday"
    assert d["19971207"]["d_daynuminweek"] == "1"
    assert d["19971231"]["d_yearmonth"] == "Dec1997"
    assert d["19940207"]["d_weeknuminyear"] == "6"
    assert d["19920229"]["d_daynuminmonth"] == "29"


def test_tpch_orders_and_lines_agree(tpch_dir: Path) -> None:
    """Order totals and statuses are computed from their own line items, as in TPC-H."""
    lines: dict[str, list[dict[str, str]]] = defaultdict(list)
    for li in rows(tpch_dir / "lineitem.tbl"):
        lines[li["l_orderkey"]].append(li)
        ship, receipt = (
            dt.date.fromisoformat(li["l_shipdate"]),
            dt.date.fromisoformat(li["l_receiptdate"]),
        )
        assert li["l_linestatus"] == ("O" if ship > CURRENT else "F")
        assert li["l_returnflag"] in (("R", "A") if receipt <= CURRENT else ("N",))
        assert Decimal("0.00") <= Decimal(li["l_discount"]) <= Decimal("0.10")
        assert receipt > ship
    for o in rows(tpch_dir / "orders.tbl"):
        ls = lines[o["o_orderkey"]]
        assert 1 <= len(ls) <= 7
        total = sum(
            int(Decimal(x["l_extendedprice"]) * 100)
            * (100 + int(Decimal(x["l_tax"]) * 100))
            * (100 - int(Decimal(x["l_discount"]) * 100))
            // 10000
            for x in ls
        )
        assert Decimal(o["o_totalprice"]) == Decimal(money(total))
        statuses = {x["l_linestatus"] for x in ls}
        assert o["o_orderstatus"] == (statuses.pop() if len(statuses) == 1 else "P")
        assert int(o["o_custkey"]) % 3 != 0  # a third of customers never order


def test_tpch_prices_and_suppliers(tpch_dir: Path) -> None:
    """Extended price is quantity x the part's retail price; suppliers come from the partsupp formula."""
    m = load_manifest(tpch_dir)
    supps = m.rows["supplier"]
    for li in rows(tpch_dir / "lineitem.tbl")[:5000]:
        pk = int(li["l_partkey"])
        qty = int(Decimal(li["l_quantity"]))
        assert Decimal(li["l_extendedprice"]) == Decimal(money(qty * retail_cents(pk)))
        assert int(li["l_suppkey"]) in {supplier_for(pk, i, supps) for i in range(4)}


def test_supplier_formula_in_range() -> None:
    """Keys are always valid; from 400 suppliers up (20 parts each) a part has four distinct ones."""
    rng = random.Random(0)
    for _ in range(2000):
        s = 4 * rng.randint(100, 2500)
        pk = rng.randint(1, 20 * s)
        keys = {supplier_for(pk, i, s) for i in range(4)}
        assert all(1 <= k <= s for k in keys)
        assert len(keys) == 4
        small = rng.randint(1, 50)
        assert all(1 <= supplier_for(pk, i, small) <= small for i in range(4))


def test_money_exact() -> None:
    """Cents format exactly, including negatives and values below one."""
    assert money(0) == "0.00"
    assert money(5) == "0.05"
    assert money(-5) == "-0.05"
    assert money(123456) == "1234.56"
    rng = random.Random(1)
    for _ in range(1000):
        c = rng.randint(-(10**9), 10**9)
        assert Decimal(money(c)) * 100 == c


def test_ssb_city() -> None:
    """Cities are the nation cut or padded to nine characters plus a digit."""
    assert ssb_city("UNITED KINGDOM", 1) == "UNITED KI1"
    assert ssb_city("PERU", 0) == "PERU     0"


@pytest.mark.parametrize("sf", [0, -1, 10.5, float("nan")])
def test_scale_bounds(sf: float) -> None:
    """Scale factors outside (0, 10] are rejected before anything is written."""
    with pytest.raises(ValueError, match="scale factor"):
        check_scale(sf)


def test_manifest_detects_changed_file(tmp_path: Path) -> None:
    """A file edited after generation fails the digest check."""
    generate("ssb", 0.001, tmp_path, seed=1)
    load_manifest(tmp_path)
    with (tmp_path / "supplier.tbl").open("a", encoding="utf-8") as f:
        f.write("999|x|x|x|x|x|x\n")
    with pytest.raises(DataError, match="differs"):
        load_manifest(tmp_path)
    load_manifest(tmp_path, verify=False)


def test_manifest_malformed(tmp_path: Path) -> None:
    """Missing, non-JSON or incomplete manifests are DataError."""
    with pytest.raises(DataError, match="cannot read"):
        load_manifest(tmp_path)
    (tmp_path / "manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises(DataError, match="cannot read"):
        load_manifest(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"suite": "ssb"}), encoding="utf-8")
    with pytest.raises(DataError, match="malformed"):
        load_manifest(tmp_path)
    doc = {"suite": "ssb", "scale_factor": 1, "seed": 1, "generator_version": 1,
           "rows": {"dates": 1}, "sha256": {"dates": "x"}}  # fmt: skip
    (tmp_path / "manifest.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DataError, match="do not match"):
        load_manifest(tmp_path)
