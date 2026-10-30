.PHONY: setup lint test bench bench-servers report audit ci

PY ?= python
SF ?= 0.1

setup:
	$(PY) -m pip install --upgrade pip && $(PY) -m pip install -e ".[dev]"

# ruff, ruff format and mypy --strict.
lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check . && $(PY) -m mypy

test:
	$(PY) -m pytest -q

# Generate SSB and TPC-H at scale factor $(SF) and time every query on DuckDB (no Docker needed).
bench:
	olapbench gen --suite ssb --sf $(SF) --out .tmp/data/ssb-$(SF)
	olapbench gen --suite tpch --sf $(SF) --out .tmp/data/tpch-$(SF)
	olapbench run --engine duckdb --suite ssb --data .tmp/data/ssb-$(SF) --out results/local/duckdb-ssb-sf$(SF).json
	olapbench run --engine duckdb --suite tpch --data .tmp/data/tpch-$(SF) --out results/local/duckdb-tpch-sf$(SF).json
	olapbench report results/local/duckdb-ssb-sf$(SF).json results/local/duckdb-tpch-sf$(SF).json

# ClickHouse, Doris and StarRocks in Docker, one at a time (Linux; as in the CI engines job).
bench-servers:
	olapbench gen --suite ssb --sf $(SF) --out data/ssb
	olapbench gen --suite tpch --sf $(SF) --out data/tpch
	bash scripts/bench_servers.sh data results/servers

report:
	olapbench report results/*/*.json

# Known vulnerabilities in the installed Python dependencies.
audit:
	$(PY) -m pip_audit --skip-editable --cache-dir .tmp/pip-audit

ci: setup lint test
