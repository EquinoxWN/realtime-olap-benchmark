"""Cross-engine answer check: the same query on the same data must give the same rows."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from realtime_olap_benchmark.results import RunResult

ABS_TOL = 0.01  # engines differ in the scale they keep for avg() of DECIMAL(15,2)
REL_TOL = 1e-6


def _number(text: str) -> Decimal | None:
    """The cell as a number, or None when it is text."""
    try:
        d = Decimal(text.strip())
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def cells_equal(a: str, b: str) -> bool:
    """Numbers equal within tolerance, anything else equal as trimmed text."""
    x, y = _number(a), _number(b)
    if x is None or y is None:
        return a.strip() == b.strip()
    diff = abs(x - y)
    return diff <= Decimal(str(ABS_TOL)) or diff <= Decimal(str(REL_TOL)) * max(abs(x), abs(y))


def answers_equal(a: list[list[str]], b: list[list[str]]) -> str:
    """Empty string when two ordered answers agree, else the first difference."""
    if len(a) != len(b):
        return f"{len(a)} rows vs {len(b)} rows"
    for i, (ra, rb) in enumerate(zip(a, b, strict=True)):
        if len(ra) != len(rb):
            return f"row {i}: {len(ra)} columns vs {len(rb)}"
        for j, (ca, cb) in enumerate(zip(ra, rb, strict=True)):
            if not cells_equal(ca, cb):
                return f"row {i} column {j}: {ca!r} vs {cb!r}"
    return ""


@dataclass(frozen=True)
class Disagreement:
    """One query whose answer differs between the reference engine and another engine."""

    suite: str
    query: str
    reference: str
    engine: str
    detail: str


def compare(results: list[RunResult]) -> tuple[int, list[Disagreement]]:
    """Compare answers per suite against the first engine on the same data.

    Returns the number of (query, engine) pairs compared and every disagreement. Runs on a
    different dataset (digest) than the suite's first run are a disagreement of their own.
    """
    checked, out = 0, []
    first: dict[str, RunResult] = {}
    for r in results:
        ref = first.setdefault(r.suite, r)
        if ref is r:
            continue
        if r.data_digest != ref.data_digest:
            out.append(Disagreement(r.suite, "*", ref.engine, r.engine, "different dataset"))
            continue
        ref_q = {q.id: q for q in ref.queries}
        for q in r.queries:
            rq = ref_q.get(q.id)
            if rq is None or rq.status != "ok" or q.status != "ok":
                continue
            checked += 1
            if detail := answers_equal(rq.answer, q.answer):
                out.append(Disagreement(r.suite, q.id, ref.engine, r.engine, detail))
    return checked, out
