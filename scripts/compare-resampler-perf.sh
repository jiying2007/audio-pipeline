#!/bin/sh
set -eu

BASE_REF=${1:-origin/main}
REPS=${2:-7}
FRAMES=${3:-100000}
MAX_ABS_REGRESSION_US=${4:-0.05}
ROOT=$(pwd)
TMP=$(mktemp -d)
trap 'git worktree remove --force "$TMP/base" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT INT TERM
if [ "$REPS" -lt 3 ]; then echo "repetitions must be >= 3" >&2; exit 2; fi

git fetch origin main --depth=1
git worktree add --detach "$TMP/base" "$BASE_REF" >/dev/null
COMMON_FLAGS='-DCMAKE_BUILD_TYPE=Release -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF'
# The regression comparator measures the behavior-equivalent FAST backend.
# BANDLIMITED is a deliberate quality backend change and is covered by its
# anti-alias contracts plus full-graph performance reporting.
#
# This microbenchmark is sub-microsecond. A pure percentage gate becomes noisy
# after the public resampler gained state/lifecycle validation, so fail only
# when a regression is both >10% and >MAX_ABS_REGRESSION_US per 10 ms frame.
# shellcheck disable=SC2086
cmake -S "$TMP/base" -B "$TMP/base/build-resampler-perf" $COMMON_FLAGS >/dev/null
cmake --build "$TMP/base/build-resampler-perf" --target audio_pipeline --parallel >/dev/null
# shellcheck disable=SC2086
cmake -S "$ROOT" -B "$TMP/head-build" $COMMON_FLAGS -DAP_RESAMPLER_MODE=FAST >/dev/null
cmake --build "$TMP/head-build" --target audio_pipeline --parallel >/dev/null

compile_harness() {
  source=$1; build_dir=$2; include_dir=$3; output=$4
  ${CC:-cc} -O3 -std=c11 -I"$include_dir" -I"$build_dir/generated" \
    "$source" "$build_dir/libaudio_pipeline.a" -lm -o "$output"
}
compile_harness "$TMP/base/bench/bench_resampler_path.c" \
    "$TMP/base/build-resampler-perf" "$TMP/base/include" "$TMP/base-resampler-bench"
compile_harness "$ROOT/bench/bench_resampler_path.c" \
    "$TMP/head-build" "$ROOT/include" "$TMP/head-resampler-bench"
extract_us() { "$1" "$2" "$3" "$FRAMES" | sed -n 's/.* us_per_frame=\([0-9.]*\).*/\1/p'; }
median() { sort -n "$1" | awk -v n="$REPS" 'NR == int(n/2)+1 { print; exit }'; }

run_case() {
  io=$1; internal=$2; label="${io}-${internal}"
  : > "$TMP/base-$label"; : > "$TMP/head-$label"; : > "$TMP/ratio-$label"
  i=0
  while [ "$i" -lt "$REPS" ]; do
    if [ $((i % 2)) -eq 0 ]; then
      base_us=$(extract_us "$TMP/base-resampler-bench" "$io" "$internal"); head_us=$(extract_us "$TMP/head-resampler-bench" "$io" "$internal")
    else
      head_us=$(extract_us "$TMP/head-resampler-bench" "$io" "$internal"); base_us=$(extract_us "$TMP/base-resampler-bench" "$io" "$internal")
    fi
    test -n "$base_us"; test -n "$head_us"
    echo "$base_us" >> "$TMP/base-$label"; echo "$head_us" >> "$TMP/head-$label"
    awk -v b="$base_us" -v h="$head_us" 'BEGIN { printf "%.6f\n", 100.0*(h-b)/b }' >> "$TMP/ratio-$label"
    i=$((i + 1))
  done
  base_median=$(median "$TMP/base-$label")
  head_median=$(median "$TMP/head-$label")
  delta=$(median "$TMP/ratio-$label")
  abs_delta=$(awk -v b="$base_median" -v h="$head_median" 'BEGIN { printf "%.6f", h-b }')
  echo "resampler_fast_path io=$io internal=$internal base_median_us=$base_median head_median_us=$head_median paired_delta_pct=$delta abs_delta_us=$abs_delta"
  if awk -v d="$delta" -v a="$abs_delta" -v maxa="$MAX_ABS_REGRESSION_US" 'BEGIN { exit !(d > 10.0 && a > maxa) }'; then
    echo "resampler FAST regression exceeds relative and absolute gates io=$io internal=$internal" >&2
    exit 3
  fi
}

echo "same_runner_resampler_fast_perf reps=$REPS frames=$FRAMES abs_gate_us=$MAX_ABS_REGRESSION_US"
run_case 24000 16000
run_case 32000 16000
run_case 48000 16000
run_case 24000 8000
run_case 32000 8000
run_case 48000 8000
run_case 8000 16000
run_case 16000 8000
