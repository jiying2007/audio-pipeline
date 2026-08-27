#!/bin/sh
set -eu

BASE_REF=${1:-origin/main}
REPS=${2:-7}
AUDIO_SECONDS=${3:-20}
ROOT=$(pwd)
TMP=$(mktemp -d)
trap 'git worktree remove --force "$TMP/base" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT INT TERM

if [ "$REPS" -lt 3 ]; then
  echo "repetitions must be >= 3" >&2
  exit 2
fi

git fetch origin main --depth=1
git worktree add --detach "$TMP/base" "$BASE_REF" >/dev/null

# Do not pass version-specific runtime switches here. ap_bench depends only on
# the core library, so base/head remain comparable across build-API hard cuts.
COMMON_FLAGS='-DCMAKE_BUILD_TYPE=Release -DAP_BUILD_TESTS=OFF -DAP_BUILD_EXAMPLES=OFF'
# shellcheck disable=SC2086
cmake -S "$TMP/base" -B "$TMP/base/build-perf" $COMMON_FLAGS >/dev/null
cmake --build "$TMP/base/build-perf" --target ap_bench --parallel >/dev/null
# shellcheck disable=SC2086
cmake -S "$ROOT" -B "$TMP/head-build" $COMMON_FLAGS >/dev/null
cmake --build "$TMP/head-build" --target ap_bench --parallel >/dev/null

extract_avg() {
  "$1" "$AUDIO_SECONDS" 0 0 "$2" | sed -n 's/.* avg_us=\([0-9.]*\).*/\1/p'
}

: > "$TMP/base-active"; : > "$TMP/head-active"; : > "$TMP/base-idle"; : > "$TMP/head-idle"
i=0
while [ "$i" -lt "$REPS" ]; do
  if [ $((i % 2)) -eq 0 ]; then
    extract_avg "$TMP/base/build-perf/ap_bench" active >> "$TMP/base-active"
    extract_avg "$TMP/head-build/ap_bench" active >> "$TMP/head-active"
    extract_avg "$TMP/base/build-perf/ap_bench" idle >> "$TMP/base-idle"
    extract_avg "$TMP/head-build/ap_bench" idle >> "$TMP/head-idle"
  else
    extract_avg "$TMP/head-build/ap_bench" active >> "$TMP/head-active"
    extract_avg "$TMP/base/build-perf/ap_bench" active >> "$TMP/base-active"
    extract_avg "$TMP/head-build/ap_bench" idle >> "$TMP/head-idle"
    extract_avg "$TMP/base/build-perf/ap_bench" idle >> "$TMP/base-idle"
  fi
  i=$((i + 1))
done

median() { sort -n "$1" | awk -v n="$REPS" 'NR == int(n/2)+1 { print; exit }'; }
BASE_ACTIVE=$(median "$TMP/base-active"); HEAD_ACTIVE=$(median "$TMP/head-active")
BASE_IDLE=$(median "$TMP/base-idle"); HEAD_IDLE=$(median "$TMP/head-idle")
ACTIVE_DELTA=$(awk -v b="$BASE_ACTIVE" -v h="$HEAD_ACTIVE" 'BEGIN { printf "%.2f", 100.0*(h-b)/b }')
IDLE_DELTA=$(awk -v b="$BASE_IDLE" -v h="$HEAD_IDLE" 'BEGIN { printf "%.2f", 100.0*(h-b)/b }')

echo "same_runner_perf reps=$REPS audio_seconds=$AUDIO_SECONDS"
echo "active base_median_us=$BASE_ACTIVE head_median_us=$HEAD_ACTIVE delta_pct=$ACTIVE_DELTA"
echo "idle   base_median_us=$BASE_IDLE head_median_us=$HEAD_IDLE delta_pct=$IDLE_DELTA"
if awk -v d="$ACTIVE_DELTA" 'BEGIN { exit !(d > 10.0) }'; then echo "active same-runner regression exceeds 10%" >&2; exit 3; fi
if awk -v d="$IDLE_DELTA" 'BEGIN { exit !(d > 10.0) }'; then echo "idle same-runner regression exceeds 10%" >&2; exit 4; fi
