# ADR 0002: Load Doris and StarRocks with batched SQL INSERTs, not Stream Load

- **Status:** Accepted

## Context

Each engine has a native bulk loader: DuckDB `COPY`, ClickHouse `INSERT ... FORMAT CSVWithNames`
over HTTP, and Stream Load (HTTP PUT to the FE, redirected to a BE) for Doris and StarRocks.
Stream Load's redirect points at the BE's own address. With Doris on host networking and
StarRocks in a single container with published ports, the address the FE hands out is different
in each setup, and a wrong address shows up only as a failed or hanging load in CI.

## Decision

Doris and StarRocks are loaded over the MySQL protocol with PyMySQL: `INSERT INTO t (...) VALUES`
in batches of 5,000 typed rows (PyMySQL folds each batch into multi-row statements). DuckDB and
ClickHouse keep their native loaders. Load time is recorded per table but is not presented as an
ingestion comparison; ingestion speed is measured in M2 with Kafka.

## Consequences

- One loader path for both MySQL-protocol engines, independent of container networking.
- Loading is slower than Stream Load and creates several load transactions per table; at the
  default CI scale (0.1, about 600,000 fact rows) this is a few dozen statements per table.
- Row counts are checked after every load, so a partial load fails the run instead of skewing it.
- If larger scale factors make loading the bottleneck, Stream Load can be added behind the same
  `Engine.load` method without changing the harness.
