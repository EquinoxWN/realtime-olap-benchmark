"""Seeded data generator for the SSB and TPC-H schemas (value domains follow the specs; not dbgen).

Files are pipe-delimited with a header row, one per table, plus manifest.json with row counts and
SHA-256 digests so a loader can refuse data that changed after generation.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from realtime_olap_benchmark.schema import Table, suite_tables

GENERATOR_VERSION = 1
MAX_SCALE_FACTOR = 10.0
DELIMITER = "|"

REGIONS = ("AFRICA", "AMERICA", "ASIA", "EUROPE", "MIDDLE EAST")
# TPC-H nation table: (name, region key), in key order.
NATIONS = (
    ("ALGERIA", 0), ("ARGENTINA", 1), ("BRAZIL", 1), ("CANADA", 1), ("EGYPT", 4),
    ("ETHIOPIA", 0), ("FRANCE", 3), ("GERMANY", 3), ("INDIA", 2), ("INDONESIA", 2),
    ("IRAN", 4), ("IRAQ", 4), ("JAPAN", 2), ("JORDAN", 4), ("KENYA", 0),
    ("MOROCCO", 0), ("MOZAMBIQUE", 0), ("PERU", 1), ("CHINA", 2), ("ROMANIA", 3),
    ("SAUDI ARABIA", 4), ("VIETNAM", 2), ("RUSSIA", 3), ("UNITED KINGDOM", 3), ("UNITED STATES", 1),
)  # fmt: skip
SEGMENTS = ("AUTOMOBILE", "BUILDING", "FURNITURE", "MACHINERY", "HOUSEHOLD")
PRIORITIES = ("1-URGENT", "2-HIGH", "3-MEDIUM", "4-NOT SPECIFIED", "5-LOW")
SHIPMODES = ("REG AIR", "AIR", "RAIL", "SHIP", "TRUCK", "MAIL", "FOB")
INSTRUCTIONS = ("DELIVER IN PERSON", "COLLECT COD", "NONE", "TAKE BACK RETURN")
TYPE_1 = ("STANDARD", "SMALL", "MEDIUM", "LARGE", "ECONOMY", "PROMO")
TYPE_2 = ("ANODIZED", "BURNISHED", "PLATED", "POLISHED", "BRUSHED")
TYPE_3 = ("TIN", "NICKEL", "BRASS", "STEEL", "COPPER")
CONTAINER_1 = ("SM", "LG", "MED", "JUMBO", "WRAP")
CONTAINER_2 = ("CASE", "BOX", "BAG", "JAR", "PKG", "PACK", "CAN", "DRUM")
COLORS = (
    "almond", "antique", "aquamarine", "azure", "beige", "bisque", "black", "blanched", "blue",
    "blush", "brown", "burlywood", "chartreuse", "chiffon", "chocolate", "coral", "cornflower",
    "cream", "cyan", "dark", "deep", "dim", "dodger", "drab", "firebrick", "forest", "frosted",
    "gainsboro", "ghost", "goldenrod", "green", "grey", "honeydew", "hot", "indian", "ivory",
    "khaki", "lace", "lavender", "lawn", "lemon", "light", "lime", "linen", "magenta", "maroon",
    "medium", "metallic", "midnight", "mint", "misty", "moccasin", "navajo", "navy", "olive",
    "orange", "orchid", "pale", "papaya", "peach", "peru", "pink", "plum", "powder", "puff",
    "purple", "red", "rose", "rosy", "royal", "saddle", "salmon", "sandy", "seashell", "sienna",
    "sky", "slate", "smoke", "snow", "spring", "steel", "tan", "thistle", "tomato", "turquoise",
    "violet", "wheat", "white", "yellow",
)  # fmt: skip
WORDS = (
    "furiously", "quickly", "carefully", "blithely", "slyly", "fluffily", "regular", "final",
    "express", "pending", "ironic", "bold", "even", "special", "unusual", "silent", "deposits",
    "accounts", "packages", "requests", "instructions", "theodolites", "foxes", "ideas", "pinto",
    "beans", "asymptotes", "courts", "dolphins", "platelets", "sleep", "haggle", "nag", "wake",
    "cajole", "boost", "detect", "integrate", "among", "across", "above", "along",
)  # fmt: skip
ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 "
MONTHS = (
    "January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December",
)  # fmt: skip
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

START = dt.date(1992, 1, 1)
END_SSB = dt.date(1998, 12, 31)
# Orders are placed up to 151 days before the end of 1998, as in the TPC-H spec.
LAST_ORDER = dt.date(1998, 8, 2)
CURRENT = dt.date(1995, 6, 17)

Row = list[object]


class DataError(ValueError):
    """Generated data is missing, changed or inconsistent with its manifest."""


@dataclass(frozen=True)
class Manifest:
    """What was generated: suite, scale, seed, row counts and file digests."""

    suite: str
    scale_factor: float
    seed: int
    rows: dict[str, int]
    sha256: dict[str, str]
    generator_version: int = GENERATOR_VERSION

    @property
    def digest(self) -> str:
        """One digest over every file digest, identifying the whole dataset."""
        joined = "".join(f"{t}:{h};" for t, h in sorted(self.sha256.items()))
        return hashlib.sha256(joined.encode()).hexdigest()


def check_scale(sf: float) -> float:
    """Validate a scale factor (0 < sf <= MAX_SCALE_FACTOR)."""
    if not 0 < sf <= MAX_SCALE_FACTOR:
        raise ValueError(f"scale factor must be in (0, {MAX_SCALE_FACTOR}], got {sf}")
    return sf


def scaled(base: int, sf: float) -> int:
    """Rows for a table whose size grows linearly with the scale factor (at least 1)."""
    return max(1, int(base * sf))


def money(cents: int) -> str:
    """Cents as a two-decimal string, exact (no float rounding)."""
    sign = "-" if cents < 0 else ""
    c = abs(cents)
    return f"{sign}{c // 100}.{c % 100:02d}"


def _text(rng: random.Random, lo: int, hi: int) -> str:
    """Random alphanumeric text of length lo..hi."""
    return "".join(rng.choices(ALNUM, k=rng.randint(lo, hi))).strip() or "x"


def _comment(rng: random.Random, max_len: int) -> str:
    """A few filler words, at most max_len characters."""
    return " ".join(rng.choices(WORDS, k=rng.randint(2, 6)))[:max_len].strip()


def _phone(rng: random.Random, nation: int) -> str:
    """Phone number whose country code is nation key + 10, as in TPC-H."""
    return (
        f"{nation + 10}-{rng.randint(100, 999)}-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}"
    )


def retail_cents(partkey: int) -> int:
    """TPC-H retail price formula, in cents."""
    return 90000 + ((partkey // 10) % 20001) + 100 * (partkey % 1000)


def ssb_city(nation: str, digit: int) -> str:
    """SSB city: nation name padded or cut to 9 characters plus one digit ('UNITED KI1')."""
    return f"{nation[:9]:<9}{digit}"


# ---------------------------------------------------------------- SSB


def _ssb_dates() -> Iterator[Row]:
    """One row per day from 1992-01-01 to 1998-12-31."""
    d = START
    while d <= END_SSB:
        doy = d.timetuple().tm_yday
        yield [
            int(d.strftime("%Y%m%d")),
            d.isoformat(),
            DAYS[d.weekday()],
            MONTHS[d.month - 1],
            d.year,
            d.year * 100 + d.month,
            f"{MONTHS[d.month - 1][:3]}{d.year}",
            (d.weekday() + 1) % 7 + 1,  # Sunday = 1
            d.day,
            d.month,
            (doy - 1) // 7 + 1,
        ]
        d += dt.timedelta(days=1)


def _ssb_party(rng: random.Random, n: int, label: str, customer: bool) -> Iterator[Row]:
    """SSB customer or supplier rows."""
    for key in range(1, n + 1):
        nation, region = NATIONS[rng.randrange(25)]
        row: Row = [
            key,
            f"{label}#{key:09d}",
            _text(rng, 10, 25),
            ssb_city(nation, rng.randrange(10)),
            nation,
            REGIONS[region],
            _phone(rng, NATIONS.index((nation, region))),
        ]
        if customer:
            row.append(rng.choice(SEGMENTS))
        yield row


def _ssb_part(rng: random.Random, n: int) -> Iterator[Row]:
    """SSB part rows: 5 manufacturers, 25 categories, 1,000 brands."""
    for key in range(1, n + 1):
        m, c, b = rng.randint(1, 5), rng.randint(1, 5), rng.randint(1, 40)
        yield [
            key,
            " ".join(rng.sample(COLORS, 2)),
            f"MFGR#{m}",
            f"MFGR#{m}{c}",
            f"MFGR#{m}{c}{b:02d}",
            rng.choice(COLORS),
            f"{rng.choice(TYPE_1)} {rng.choice(TYPE_2)} {rng.choice(TYPE_3)}",
            rng.randint(1, 50),
            f"{rng.choice(CONTAINER_1)} {rng.choice(CONTAINER_2)}",
        ]


def _ssb_lineorder(
    rng: random.Random, sf: float, parts: int, custs: int, supps: int
) -> Iterator[Row]:
    """SSB lineorder rows: 1,500,000 x SF orders of 1 to 7 lines each."""
    span = (LAST_ORDER - START).days
    keys = [int((START + dt.timedelta(days=i)).strftime("%Y%m%d")) for i in range(span + 121)]
    for order in range(1, scaled(1_500_000, sf) + 1):
        day = rng.randint(0, span)
        cust, prio = rng.randint(1, custs), rng.choice(PRIORITIES)
        lines: list[Row] = []
        total = 0
        for ln in range(1, rng.randint(1, 7) + 1):
            pk = rng.randint(1, parts)
            price = retail_cents(pk) // 100
            qty, disc = rng.randint(1, 50), rng.randint(0, 10)
            ext = qty * price
            total += ext
            lines.append(
                [
                    order, ln, cust, pk, rng.randint(1, supps), keys[day], prio, 0, qty, ext,
                    0, disc, ext * (100 - disc) // 100, 6 * price // 10, rng.randint(0, 8),
                    keys[day + rng.randint(30, 90)], rng.choice(SHIPMODES),
                ]
            )  # fmt: skip
        for r in lines:
            r[10] = total
            yield r


# ---------------------------------------------------------------- TPC-H


def _tpch_part(rng: random.Random, n: int) -> Iterator[Row]:
    """TPC-H part rows."""
    for key in range(1, n + 1):
        m = rng.randint(1, 5)
        yield [
            key,
            " ".join(rng.sample(COLORS, 5)),
            f"Manufacturer#{m}",
            f"Brand#{m}{rng.randint(1, 5)}",
            f"{rng.choice(TYPE_1)} {rng.choice(TYPE_2)} {rng.choice(TYPE_3)}",
            rng.randint(1, 50),
            f"{rng.choice(CONTAINER_1)} {rng.choice(CONTAINER_2)}",
            money(retail_cents(key)),
            _comment(rng, 23),
        ]


def _tpch_supplier(rng: random.Random, n: int) -> Iterator[Row]:
    """TPC-H supplier rows."""
    for key in range(1, n + 1):
        nation = rng.randrange(25)
        yield [
            key, f"Supplier#{key:09d}", _text(rng, 10, 40), nation, _phone(rng, nation),
            money(rng.randint(-99999, 999999)), _comment(rng, 101),
        ]  # fmt: skip


def _tpch_customer(rng: random.Random, n: int) -> Iterator[Row]:
    """TPC-H customer rows."""
    for key in range(1, n + 1):
        nation = rng.randrange(25)
        yield [
            key, f"Customer#{key:09d}", _text(rng, 10, 40), nation, _phone(rng, nation),
            money(rng.randint(-99999, 999999)), rng.choice(SEGMENTS), _comment(rng, 117),
        ]  # fmt: skip


def supplier_for(partkey: int, i: int, supps: int) -> int:
    """The i-th (0..3) supplier of a part, from the TPC-H partsupp formula."""
    return (partkey + i * (supps // 4 + (partkey - 1) // supps)) % supps + 1


class _TpchOrders:
    """Generates orders and their line items together so totals and statuses agree."""

    def __init__(self, rng: random.Random, sf: float, parts: int, custs: int, supps: int) -> None:
        """Remember sizes; line items go to `sink`, set by the writer before orders() runs."""
        self.rng, self.sf, self.parts, self.custs, self.supps = rng, sf, parts, custs, supps
        self.sink: Callable[[Row], None] = lambda row: None

    def orders(self) -> Iterator[Row]:
        """Order rows; each order's line items are passed to self.sink as they are made."""
        rng, span = self.rng, (LAST_ORDER - START).days
        for okey in range(1, scaled(1_500_000, self.sf) + 1):
            cust = rng.randint(1, self.custs)
            while cust % 3 == 0 and self.custs > 2:  # a third of customers never order (TPC-H)
                cust = rng.randint(1, self.custs)
            odate = START + dt.timedelta(days=rng.randint(0, span))
            total, statuses = 0, set()
            for ln in range(1, rng.randint(1, 7) + 1):
                pk = rng.randint(1, self.parts)
                qty, disc, tax = rng.randint(1, 50), rng.randint(0, 10), rng.randint(0, 8)
                ext = qty * retail_cents(pk)
                ship = odate + dt.timedelta(days=rng.randint(1, 121))
                commit = odate + dt.timedelta(days=rng.randint(30, 90))
                receipt = ship + dt.timedelta(days=rng.randint(1, 30))
                flag = rng.choice("RA") if receipt <= CURRENT else "N"
                status = "O" if ship > CURRENT else "F"
                statuses.add(status)
                total += ext * (100 + tax) * (100 - disc) // 10000
                self.sink(
                    [
                        okey, pk, supplier_for(pk, rng.randrange(4), self.supps), ln,
                        f"{qty}.00", money(ext), money(disc), money(tax), flag, status,
                        ship.isoformat(), commit.isoformat(), receipt.isoformat(),
                        rng.choice(INSTRUCTIONS), rng.choice(SHIPMODES), _comment(rng, 44),
                    ]
                )  # fmt: skip
            ostatus = statuses.pop() if len(statuses) == 1 else "P"
            yield [
                okey, cust, ostatus, money(total), odate.isoformat(), rng.choice(PRIORITIES),
                f"Clerk#{rng.randint(1, max(1, int(1000 * self.sf))):09d}", 0, _comment(rng, 79),
            ]  # fmt: skip


# ---------------------------------------------------------------- writing


class _Writer:
    """Pipe-delimited table file with a header row; checks each row's width."""

    def __init__(self, path: Path, table: Table) -> None:
        """Open the file and write the header."""
        self.table, self.rows = table, 0
        self._f = path.open("w", encoding="utf-8", newline="")
        self._w = csv.writer(
            self._f, delimiter=DELIMITER, lineterminator="\n", quoting=csv.QUOTE_NONE
        )
        self._w.writerow(table.column_names)

    def write(self, row: Row) -> None:
        """Write one row."""
        width = len(self.table.columns)
        if len(row) != width:
            raise DataError(f"{self.table.name}: row has {len(row)} values, expected {width}")
        self._w.writerow(row)
        self.rows += 1

    def __enter__(self) -> _Writer:
        """Context manager entry."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the file."""
        self._f.close()


def _write(path: Path, table: Table, rows: Iterator[Row]) -> tuple[int, str]:
    """Write one table file; return its row count and SHA-256."""
    with _Writer(path, table) as w:
        for row in rows:
            w.write(row)
    return w.rows, sha256_file(path)


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, read in chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


Sources = dict[str, Callable[[], Iterator[Row]]]


def _sources(suite: str, sf: float, rng: random.Random) -> tuple[Sources, _TpchOrders | None]:
    """Row generators per table in a fixed order (same seed, same files), plus the TPC-H orders."""
    if suite == "ssb":
        parts, custs, supps = scaled(200_000, sf), scaled(30_000, sf), scaled(2_000, sf)
        return {
            "dates": _ssb_dates,
            "customer": lambda: _ssb_party(rng, custs, "Customer", True),
            "supplier": lambda: _ssb_party(rng, supps, "Supplier", False),
            "part": lambda: _ssb_part(rng, parts),
            "lineorder": lambda: _ssb_lineorder(rng, sf, parts, custs, supps),
        }, None
    parts, custs, supps = scaled(200_000, sf), scaled(150_000, sf), scaled(10_000, sf)
    gen = _TpchOrders(rng, sf, parts, custs, supps)

    def region() -> Iterator[Row]:
        """The five regions."""
        return iter([[i, r, _comment(rng, 152)] for i, r in enumerate(REGIONS)])

    def nation() -> Iterator[Row]:
        """The 25 nations."""
        return iter([[i, n, r, _comment(rng, 152)] for i, (n, r) in enumerate(NATIONS)])

    return {
        "region": region,
        "nation": nation,
        "supplier": lambda: _tpch_supplier(rng, supps),
        "customer": lambda: _tpch_customer(rng, custs),
        "part": lambda: _tpch_part(rng, parts),
        "orders": gen.orders,
    }, gen


def generate(suite: str, sf: float, out: Path, seed: int = 42) -> Manifest:
    """Generate every table of a suite into out/ and write manifest.json."""
    tables = {t.name: t for t in suite_tables(suite)}
    check_scale(sf)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    rows: dict[str, int] = {}
    digests: dict[str, str] = {}
    sources, orders = _sources(suite, sf, rng)
    for name, source in sources.items():
        if name == "orders" and orders is not None:
            # lineitem rows are written while orders are generated, so nothing is buffered
            with _Writer(out / "lineitem.tbl", tables["lineitem"]) as li:
                orders.sink = li.write
                rows[name], digests[name] = _write(out / f"{name}.tbl", tables[name], source())
            rows["lineitem"], digests["lineitem"] = li.rows, sha256_file(out / "lineitem.tbl")
        else:
            rows[name], digests[name] = _write(out / f"{name}.tbl", tables[name], source())
    manifest = Manifest(suite, sf, seed, rows, digests)
    payload = {
        "suite": suite,
        "scale_factor": sf,
        "seed": seed,
        "generator_version": GENERATOR_VERSION,
        "rows": rows,
        "sha256": digests,
    }
    (out / "manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_manifest(data_dir: Path, verify: bool = True) -> Manifest:
    """Read manifest.json; with verify, check every file's SHA-256 against it."""
    path = data_dir / "manifest.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise DataError(f"cannot read {path}: {e}") from e
    try:
        m = Manifest(
            suite=str(raw["suite"]),
            scale_factor=float(raw["scale_factor"]),
            seed=int(raw["seed"]),
            rows={str(k): int(v) for k, v in raw["rows"].items()},
            sha256={str(k): str(v) for k, v in raw["sha256"].items()},
            generator_version=int(raw["generator_version"]),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise DataError(f"malformed manifest {path}: {e}") from e
    expected = {t.name for t in suite_tables(m.suite)}
    if set(m.rows) != expected or set(m.sha256) != expected:
        raise DataError(f"manifest tables {sorted(m.rows)} do not match suite {m.suite}")
    if verify:
        for table, digest in m.sha256.items():
            f = data_dir / f"{table}.tbl"
            if not f.is_file() or sha256_file(f) != digest:
                raise DataError(f"{f} is missing or differs from the manifest digest")
    return m
