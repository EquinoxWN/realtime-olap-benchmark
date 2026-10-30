# Contributing

Thanks for helping. This is a Python project; issues and pull requests are welcome.

## Set up and check your change

Needs Python 3.11+. ClickHouse, Doris and StarRocks run in Docker on Linux (the CI `engines` job);
everything else, including DuckDB, runs without Docker. Caches and virtual environments stay in
git-ignored folders inside the repo.

```bash
make setup           # install dependencies
make lint            # ruff, ruff format, mypy --strict
make test            # full test suite
make audit           # known-vulnerability check (as in CI)
make bench SF=0.1    # SSB and TPC-H on DuckDB
make bench-servers   # Linux with Docker: ClickHouse, Doris, StarRocks one at a time
```

A pull request is ready when `make lint` and `make test` pass and CI is green.

## Guidelines

- Keep each change focused; explain the problem it solves in the pull request.
- Add or update a test for every behaviour change, and update `docs/results/` when numbers change.
- A query that needs a different dialect on one engine goes in
  `src/realtime_olap_benchmark/queries/<suite>/<engine>/<file>.sql`; the answer check must still pass.
- Significant design changes need an ADR in `docs/adr/` (copy `0001` for the format).
- Keep function comments to one short phrase; let names and tests explain the rest.
- Report security problems privately, as described in [SECURITY.md](SECURITY.md).

By contributing you agree that your work is released under the [MIT License](LICENSE).
