# ADR 0003: A seeded Python generator instead of dbgen

- **Status:** Accepted

## Context

SSB and TPC-H data normally come from `ssb-dbgen` and `dbgen`, C programs built per platform.
DuckDB's `tpch` extension can generate TPC-H, but it downloads the extension into the user's home
folder, and there is no equivalent for SSB. The project rules keep every download and cache inside
the repository, and the tests need to recompute query answers from the raw rows.

## Decision

`datagen.py` generates both schemas in pure Python from a seed: the TPC-H nations and regions,
segments, priorities, ship modes, part types and the retail-price and partsupp formulas; the SSB
brand, category and city formats; the TPC-H rule that a third of customers never order; order
totals and statuses computed from their own line items. Each file's SHA-256 goes into
`manifest.json`; loaders refuse files that changed.

## Consequences

- Same seed and scale give byte-identical files on every machine, so every engine reads the same
  rows, and tests can check DuckDB's answers against plain-Python recomputation.
- The numbers are not comparable with official TPC-H or SSB results; the README says so.
- Pure Python generation is slower than dbgen (about 17 s for TPC-H at scale factor 0.1 on the
  author's laptop); scale factors above 10 are rejected.
- Dimension sizes scale linearly (SSB `part` scales logarithmically in the spec for SF >= 1).
