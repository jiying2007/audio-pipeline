#!/bin/sh
set -eu

BASE_REF=${1:-origin/main}
REPS=${2:-7}
FRAMES=${3:-50000}
ROOT=$(pwd)
TMP=$(mktemp -d)
trap 'git worktree remove --force "$TMP/base" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT INT TERM

if [ "$REPS" -lt 3 ]; then echo "repetitions must be >= 3" >&2; exit 2; fi

git fetch origin main --depth=1
git worktree add --detach "$TMP/base" "$BASE_REF" >/dev/null
COMMON_FLAGS='-DCMAKE_BUILD_TYPE=Release -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF'
# shellcheck disable=SC2086
cmake -S "$TMP/base" -B "$TMP/base/build-ns-perf" $COMMON_FLAGS >/dev/null
cmake --build "$TMP/base/build-ns-perf" --target audio_pipeline --parallel >/dev/null
# shellcheck disable=SC2086
cmake -S "$ROOT" -B "$TMP/head-build" $COMMON_FLAGS >/dev/null
cmake --build "$TMP/head-build" --target audio_pipeline --parallel >/dev/null

compile_harness() {
  build_dir=$1; include_dir=$2; output=$3
  ${CC:-cc} -O3 -std=c11 -I"$include_dir" \
    "$ROOT/bench/bench_ns_path.c" "$build_dir/libaudio_pipeline.a" -lm -o "$output"
}
# Public structs may change across a hard-cut branch. Always compile each
# harness against the matching library's headers.
compile_harness "$TMP/base/build-ns-perf" "$TMP/base/include" "$TMP/base-ns-bench"
compile_harness "$TMP/head-build" "$ROOT/include" "$TMP/head-ns-bench"

extract_us() { "$1" "$FRAMES" "$2" "$3" | sed -n 's/.* us_per_frame=\([0-9.]*\).*/\1/p'; }
median() { sort -n "$1" | awk -v n="$REPS" 'NR == int(n/2)+1 { print; exit }'; }
run_case() {
  rate=$1; res=$2; label="${rate}-${res}"
  : > "$TMP/base-$label"; : > "$TMP/head-$label"; : > "$TMP/ratio-$label"
  i=0
  while [ "$i" -lt "$REPS" ]; do
    if [ $((i % 2)) -eq 0 ]; then
      base_us=$(extract_us "$TMP/base-ns-bench" "$rate" "$res"); head_us=$(extract_us "$TMP/head-ns-bench" "$rate" "$res")
    else
      head_us=$(extract_us "$TMP/head-ns-bench" "$rate" "$res"); base_us=$(extract_us "$TMP/base-ns-bench" "$rate" "$res")
    fi
    test -n "$base_us"; test -n "$head_us"
    echo "$base_us" >> "$TMP/base-$label"; echo "$head_us" >> "$TMP/head-$label"
    awk -v b="$base_us" -v h="$head_us" 'BEGIN { printf "%.6f\n", 100.0*(h-b)/b }' >> "$TMP/ratio-$label"
    i=$((i + 1))
  done
  base_median=$(median "$TMP/base-$label"); head_median=$(median "$TMP/head-$label"); delta=$(median "$TMP/ratio-$label")
  echo "ns_path rate=$rate res=$res base_median_us=$base_median head_median_us=$head_median paired_delta_pct=$delta"
  if awk -v d="$delta" 'BEGIN { exit !(d > 10.0) }'; then echo "NS path same-runner regression exceeds 10% rate=$rate res=$res" >&2; exit 3; fi
}

echo "same_runner_ns_perf reps=$REPS frames=$FRAMES"
run_case 16000 0
run_case 16000 1
run_case 8000 0
run_case 8000 1
