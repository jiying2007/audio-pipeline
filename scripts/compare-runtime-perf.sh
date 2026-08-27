#!/bin/sh
set -eu

BASE_REF=${1:-origin/main}
REPS=${2:-7}
MINIMAL_FRAMES=${3:-10000}
FULL_FRAMES=${4:-5000}
ROOT=$(pwd)
TMP=$(mktemp -d)
trap 'git worktree remove --force "$TMP/base" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT INT TERM

if [ "$REPS" -lt 3 ]; then
  echo "repetitions must be >= 3" >&2
  exit 2
fi

git fetch origin main --depth=1
git worktree add --detach "$TMP/base" "$BASE_REF" >/dev/null

COMMON_FLAGS='-DCMAKE_BUILD_TYPE=Release -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF -DAP_ENABLE_RUNTIME=ON'
# shellcheck disable=SC2086
cmake -S "$TMP/base" -B "$TMP/base/build-runtime-perf" $COMMON_FLAGS >/dev/null
cmake --build "$TMP/base/build-runtime-perf" --target audio_pipeline_runtime --parallel >/dev/null
# shellcheck disable=SC2086
cmake -S "$ROOT" -B "$TMP/head-build" $COMMON_FLAGS >/dev/null
cmake --build "$TMP/head-build" --target audio_pipeline_runtime --parallel >/dev/null

compile_harness() {
  build_dir=$1
  output=$2
  ${CC:-cc} -O3 -std=c11 -pthread \
    -I"$ROOT/include" \
    "$ROOT/bench/bench_runtime_throughput.c" \
    "$build_dir/libaudio_pipeline_runtime.a" \
    "$build_dir/libaudio_pipeline.a" -lm -o "$output"
}

compile_harness "$TMP/base/build-runtime-perf" "$TMP/base-runtime-bench"
compile_harness "$TMP/head-build" "$TMP/head-runtime-bench"

extract_us() {
  "$1" "$2" "$3" | sed -n 's/.* us_per_frame=\([0-9.]*\).*/\1/p'
}

for name in base-minimal head-minimal base-full head-full; do
  : > "$TMP/$name"
done

i=0
while [ "$i" -lt "$REPS" ]; do
  if [ $((i % 2)) -eq 0 ]; then
    extract_us "$TMP/base-runtime-bench" "$MINIMAL_FRAMES" minimal >> "$TMP/base-minimal"
    extract_us "$TMP/head-runtime-bench" "$MINIMAL_FRAMES" minimal >> "$TMP/head-minimal"
    extract_us "$TMP/base-runtime-bench" "$FULL_FRAMES" full >> "$TMP/base-full"
    extract_us "$TMP/head-runtime-bench" "$FULL_FRAMES" full >> "$TMP/head-full"
  else
    extract_us "$TMP/head-runtime-bench" "$MINIMAL_FRAMES" minimal >> "$TMP/head-minimal"
    extract_us "$TMP/base-runtime-bench" "$MINIMAL_FRAMES" minimal >> "$TMP/base-minimal"
    extract_us "$TMP/head-runtime-bench" "$FULL_FRAMES" full >> "$TMP/head-full"
    extract_us "$TMP/base-runtime-bench" "$FULL_FRAMES" full >> "$TMP/base-full"
  fi
  i=$((i + 1))
done

median() {
  sort -n "$1" | awk -v n="$REPS" 'NR == int(n/2)+1 { print; exit }'
}

BASE_MINIMAL=$(median "$TMP/base-minimal")
HEAD_MINIMAL=$(median "$TMP/head-minimal")
BASE_FULL=$(median "$TMP/base-full")
HEAD_FULL=$(median "$TMP/head-full")
MINIMAL_DELTA=$(awk -v b="$BASE_MINIMAL" -v h="$HEAD_MINIMAL" 'BEGIN { printf "%.2f", 100.0*(h-b)/b }')
FULL_DELTA=$(awk -v b="$BASE_FULL" -v h="$HEAD_FULL" 'BEGIN { printf "%.2f", 100.0*(h-b)/b }')

echo "same_runner_runtime_perf reps=$REPS minimal_frames=$MINIMAL_FRAMES full_frames=$FULL_FRAMES"
echo "minimal base_median_us=$BASE_MINIMAL head_median_us=$HEAD_MINIMAL delta_pct=$MINIMAL_DELTA"
echo "full    base_median_us=$BASE_FULL head_median_us=$HEAD_FULL delta_pct=$FULL_DELTA"

if awk -v d="$MINIMAL_DELTA" 'BEGIN { exit !(d > 10.0) }'; then
  echo "minimal runtime same-runner regression exceeds 10%" >&2
  exit 3
fi
if awk -v d="$FULL_DELTA" 'BEGIN { exit !(d > 10.0) }'; then
  echo "full runtime same-runner regression exceeds 10%" >&2
  exit 4
fi
