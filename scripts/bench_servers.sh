#!/usr/bin/env bash
# Benchmark the server engines one after another on this machine (Linux with Docker):
# start one compose profile, wait until it accepts queries, run SSB and TPC-H, tear it down.
# usage: scripts/bench_servers.sh <data dir with ssb/ and tpch/> <results dir> [engine ...]
set -euo pipefail

DATA=${1:?data dir}
OUT=${2:?results dir}
shift 2
ENGINES=("$@")
[ ${#ENGINES[@]} -eq 0 ] && ENGINES=(clickhouse doris starrocks)
COMPOSE=(docker compose -f "$(dirname "$0")/../docker/compose.yml")
RUNS=(--cold-runs "${COLD_RUNS:-3}" --warmup-runs 1 --hot-runs "${HOT_RUNS:-5}" --drop-os-cache)
mkdir -p "$OUT"

for engine in "${ENGINES[@]}"; do
  case "$engine" in clickhouse|doris|starrocks) ;; *) echo "unknown engine $engine" >&2; exit 2 ;; esac
  echo "::group::$engine"
  "${COMPOSE[@]}" --profile "$engine" up -d
  status=0
  if olapbench wait --engine "$engine" --timeout 600; then
    for suite in ssb tpch; do
      olapbench run --engine "$engine" --suite "$suite" --data "$DATA/$suite" \
        --out "$OUT/$engine-$suite.json" "${RUNS[@]}" || status=1
    done
  else
    "${COMPOSE[@]}" --profile "$engine" logs --tail 80 || true
    status=1
  fi
  "${COMPOSE[@]}" --profile "$engine" down -v
  echo "::endgroup::"
  if [ "$status" -ne 0 ]; then
    echo "::error title=$engine::benchmark failed (see the $engine group in the log)"
    FAILED=1
  fi
done
exit "${FAILED:-0}"
