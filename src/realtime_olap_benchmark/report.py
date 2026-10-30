"""Markdown tables from result files: cold and hot medians per query and engine, plus agreement."""

from __future__ import annotations

from realtime_olap_benchmark.answers import compare
from realtime_olap_benchmark.results import RunResult, geomean


def _ms(v: float | None) -> str:
    """Milliseconds for a table cell."""
    if v is None:
        return "error"
    return f"{v:,.1f}" if v < 100 else f"{v:,.0f}"


def suite_table(runs: list[RunResult]) -> str:
    """One markdown table for the runs of a single suite."""
    ids: list[str] = []
    for r in runs:
        ids += [q.id for q in r.queries if q.id not in ids]
    head = "| Query | " + " | ".join(f"{r.engine} cold | {r.engine} hot" for r in runs) + " |"
    sep = "|---|" + "---:|---:|" * len(runs)
    lines = [head, sep]
    for qid in ids:
        cells = []
        for r in runs:
            q = next((x for x in r.queries if x.id == qid), None)
            cold = q.cold.median_ms if q and q.cold and q.status == "ok" else None
            hot = q.hot.median_ms if q and q.hot and q.status == "ok" else None
            cells.append(f"{_ms(cold) if q and q.cold_ms else '-'} | {_ms(hot)}")
        lines.append(f"| {qid} | " + " | ".join(cells) + " |")
    gm = []
    for r in runs:
        cold_meds = [q.cold.median_ms for q in r.queries if q.cold and q.status == "ok"]
        hot_meds = [q.hot.median_ms for q in r.queries if q.hot and q.status == "ok"]
        gm.append(
            f"**{_ms(geomean(cold_meds)) if cold_meds else '-'}** | **{_ms(geomean(hot_meds))}**"
        )
    lines.append("| geometric mean | " + " | ".join(gm) + " |")
    return "\n".join(lines)


def render(runs: list[RunResult]) -> str:
    """Full markdown report: per suite a timing table, the engines' details and the answer check."""
    out = []
    for suite in sorted({r.suite for r in runs}):
        rs = [r for r in runs if r.suite == suite]
        sf = ", ".join(sorted({f"{r.scale_factor:g}" for r in rs}))
        out.append(f"### {suite.upper()} (scale factor {sf}), median milliseconds\n")
        out.append(suite_table(rs))
        out.append("")
        for r in rs:
            failed = [q.id for q in r.queries if q.status != "ok"]
            out.append(
                f"- **{r.engine}** {r.engine_version} ({r.deployment}); threads "
                f"{r.settings.get('threads') or r.settings.get('max_threads', '?')}; {r.cold_runs} cold, "
                f"{r.warmup_runs} warm-up, {r.hot_runs} hot runs; cold = {r.cold_method}; "
                f"load {sum(r.load_seconds.values()):.1f} s"
                + (f"; failed: {', '.join(failed)}" if failed else "")
            )
        out.append("")
    checked, bad = compare(runs)
    if checked:
        out.append(f"Answer check: {checked - len([b for b in bad if b.query != '*'])} of {checked} "
                   "query results match the first engine of their suite.")  # fmt: skip
    out.extend(
        f"- disagreement {b.suite} {b.query}: {b.engine} vs {b.reference}: {b.detail}" for b in bad
    )
    return "\n".join(out).rstrip() + "\n"
