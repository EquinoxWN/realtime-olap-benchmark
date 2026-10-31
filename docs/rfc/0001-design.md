# RFC 0001: realtime-olap-benchmark design

- **Status:** Accepted (M1 built)
- **Author:** EquinoxWN
- **Created:** 2026-10-23

## Problem

Teams choosing an analytics database for dashboards usually compare vendor benchmarks run on
different hardware, data and settings, often hot-cache only, and rarely check that each engine
returned the right answer. The result is a choice based on numbers that cannot be reproduced.
This project runs the same seeded data and the same SQL on ClickHouse, Apache Doris, StarRocks and
DuckDB, on one machine, cold and hot, several times each, and publishes medians, spread, the exact
versions and settings, and whether the engines agreed on the answers.

Users: data and platform engineers shortlisting an OLAP engine, and anyone who wants to rerun the
comparison on their own hardware.

## Goals (M1) and critical-to-quality measures

| CTQ | Target | How it is held |
|---|---|---|
| Same data everywhere | Every engine loads byte-identical files; row counts checked after load | SHA-256 per file in `manifest.json`, checked before loading; `count(*)` per table must equal the manifest |
| Same questions | One SQL file per query, shared by all engines; read-only | Query loader rejects anything but one `SELECT`/`WITH` |
| Correct answers | Every engine's answer equals the first engine's within 0.01 absolute or 1e-6 relative | `olapbench report --strict` fails the CI job on a disagreement; DuckDB answers checked against plain-Python recomputation in tests |
| Repeatable timing | At least 3 cold and 5 hot runs per query; median, min, max, stdev and coefficient of variation recorded | `Plan` validation (1 to 50 runs); result-file schema validation |
| Documented setup | Engine version from the engine itself, settings and cold method in every result file | `RunResult` fields are required by the validator |
| One machine | All four engines on the same runner, servers one at a time | `scripts/bench_servers.sh` and the `engines` CI job |

## Non-goals

- Official TPC-H or SSB results. The generator follows the schemas and value domains but is not
  `dbgen`; numbers are not comparable with published results.
- Tuning each engine (M3), streaming ingestion (M2), cluster deployments, cost per query.
- Running as a hosted service.

## Design

1. **Generator** (`datagen.py`): seeded, pure Python, pipe-delimited files with a header row.
   SSB: 5 tables; TPC-H: the 7 tables the query subset reads (partsupp is not needed). Orders and
   their line items are generated together so totals and statuses agree; line items are streamed
   to disk, so memory stays flat as the scale factor grows.
2. **Schema** (`schema.py`): one logical schema rendered as DDL per engine. No tuning: ClickHouse
   MergeTree ordered by the first column; Doris and StarRocks duplicate-key tables hashed on the
   first column (4 buckets for fact tables, 1 otherwise), one replica; DuckDB plain tables.
3. **Queries** (`queries/`): the 13 SSB queries and 8 TPC-H queries (Q1, Q3, Q5, Q6, Q10, Q12,
   Q14, Q18) that need no correlated subqueries. Date arithmetic is written as literal dates and
   Q6's discount bounds as `>= 0.05 AND <= 0.07`, so the same text runs on every engine. A
   per-engine override folder exists for dialect fixes; none is needed in M1.
4. **Engines** (`engines/`): DuckDB embedded; ClickHouse over HTTP with the standard library
   (credentials in headers); Doris and StarRocks over the MySQL protocol with PyMySQL.
5. **Harness** (`harness.py`): recreate tables, load, verify counts, collect statistics, then per
   query: N cold runs (engine cache reset before each, plus the Linux page cache with
   `--drop-os-cache`), one untimed warm-up, M hot runs. Client wall-clock time includes fetching
   the result. A failing query is recorded with its error; the run continues.
6. **Results** (`results.py`): one validated JSON file per engine and suite; `report.py` renders
   markdown tables and the cross-engine answer check.
7. **Docker** (`docker/compose.yml`): digest-pinned images, one profile per engine, memory limits;
   the CI `engines` job starts one engine at a time on the same runner.

## Alternatives considered

| Option | Why not |
|---|---|
| Official `dbgen`/`ssb-dbgen` binaries | C tools to download and build per platform (Windows included); DuckDB's `tpch` extension downloads into the user's home folder. A seeded Python generator keeps everything inside the repo and makes row-level oracle tests possible; the cost is that numbers are not comparable with official results. |
| Run every engine in parallel containers | Faster, but the engines compete for the same 4 cores and 16 GB; timings would measure contention. Sequential runs on one machine trade wall time for clean numbers. |
| One matrix job per engine | Separate runners may land on different hardware, which breaks "same machine". |
| Load Doris and StarRocks with Stream Load (HTTP) | Much faster for big data, but the FE redirects to the BE by address, which differs between host and container networking. Batched INSERTs over the MySQL protocol work identically for both; load time is therefore not compared (ADR 0002). |
| ClickBench-style single flat table | Easier for every engine, but hides join performance, which is where these engines differ most. SSB and TPC-H keep the joins. |
| Server-side timing (query log) | More precise, but each engine logs differently. Client wall-clock time is uniform and is what a dashboard sees. |

## Measurement plan

- Machine, OS, CPU, Python and engine version recorded in each result file.
- Per query: cold runs after cache reset, warm-up, hot runs; report median (headline), min, max,
  stdev and coefficient of variation; geometric mean of medians per engine and suite.
- Locally (no Docker): DuckDB at scale factor 0.1. CI: all four engines at scale factor 0.1 by
  default (input `scale_factor` up to 10), page cache dropped before each cold run.
- Answer agreement per query across engines; disagreements fail the CI report step.

## Milestones

- **M1:** SSB and TPC-H queries cold and hot, several times, medians reported (built and
  measured on DuckDB). All four engines in Docker or embedded on one machine with versions and
  settings recorded: DuckDB measured locally; ClickHouse, Doris and StarRocks measured in the CI
  `engines` job (first green run 2026-10-31).
- **M2:** Kafka ingestion (rows per second, freshness); join-heavy and single-table queries
  reported separately.
- **M3:** per-engine table tuning, documented; findings on speed, freshness and operating cost.

## Risks and open questions

- Small scale factors measure per-query overhead more than scan speed; larger runs need more
  RAM than a shared laptop has (CI runner: 16 GB).
- "Cold" differs by engine: ClickHouse caches can be dropped by SQL; Doris and StarRocks page
  caches cannot, so only the OS page cache drop makes them cold. Each result file states its
  cold method.
- Shared CI runners add noise; the coefficient of variation is published so noisy queries are
  visible.
