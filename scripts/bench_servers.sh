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

# Print the last lines of a log as one ::error annotation (annotations are readable without a login).
annotate() {
  local msg
  msg=$(tail -n "${3:-15}" "$2" | sed -e 's/%/%25/g' -e 's/\r/%0D/g' | awk '{printf "%s%%0A", $0}')
  echo "::error title=$1::$msg"
}

for engine in "${ENGINES[@]}"; do
  case "$engine" in clickhouse|doris|starrocks) ;; *) echo "unknown engine $engine" >&2; exit 2 ;; esac
  echo "::group::$engine"
  "${COMPOSE[@]}" --profile "$engine" up -d
  status=0
  if olapbench wait --engine "$engine" --timeout 600; then
    for suite in ssb tpch; do
      rc=0
      olapbench run --engine "$engine" --suite "$suite" --data "$DATA/$suite" \
        --out "$OUT/$engine-$suite.json" "${RUNS[@]}" > "$OUT/$engine-$suite.log" 2>&1 || rc=$?
      cat "$OUT/$engine-$suite.log"
      if [ "$rc" -ne 0 ]; then status=1; annotate "$engine $suite run" "$OUT/$engine-$suite.log"; fi
    done
  else
    status=1
  fi
  if [ "$status" -ne 0 ]; then
    "${COMPOSE[@]}" --profile "$engine" logs --tail 80 > "$OUT/$engine-containers.log" 2>&1 || true
    cat "$OUT/$engine-containers.log"
    annotate "$engine container logs" "$OUT/$engine-containers.log" 20
    df -h / > "$OUT/$engine-disk.log" 2>&1 || true
    annotate "$engine disk" "$OUT/$engine-disk.log" 2
    # Exit code and OOM flag of each container, to tell a crash from a memory kill.
    docker ps -aq --filter "label=com.docker.compose.project" | xargs -r docker inspect       -f '{{.Name}} exit={{.State.ExitCode}} oomkilled={{.State.OOMKilled}}' > "$OUT/$engine-state.log" 2>&1 || true
    annotate "$engine container state" "$OUT/$engine-state.log" 10
  fi
  "${COMPOSE[@]}" --profile "$engine" down -v
  echo "::endgroup::"
  if [ "$status" -ne 0 ]; then
    echo "::error title=$engine::benchmark failed (see the $engine group in the log)"
    FAILED=1
  fi
done
exit "${FAILED:-0}"
