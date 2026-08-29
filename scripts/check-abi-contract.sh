#!/bin/sh
set -eu
BASE_REF=${1:-v1.1.1}
ROOT=$(pwd)
TMP=$(mktemp -d)
trap 'git worktree remove --force "$TMP/base" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT INT TERM
git fetch origin "refs/tags/$BASE_REF:refs/tags/$BASE_REF" --force >/dev/null 2>&1 || true
git worktree add --detach "$TMP/base" "$BASE_REF" >/dev/null
for side in base head; do
  src="$ROOT"; [ "$side" = base ] && src="$TMP/base"
  cmake -S "$src" -B "$TMP/$side-build" -DCMAKE_BUILD_TYPE=Release -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF >/dev/null
  cmake --build "$TMP/$side-build" --parallel >/dev/null
  cc "$ROOT/tests/abi_probe.c" -I"$src/include" -I"$TMP/$side-build/generated" -o "$TMP/$side-probe"
  "$TMP/$side-probe" | sort > "$TMP/$side-abi"
  nm -g --defined-only "$TMP/$side-build/libaudio_pipeline.a" | awk '{print $3}' | grep '^ap_' | sort -u > "$TMP/$side-core-symbols"
  nm -g --defined-only "$TMP/$side-build/libaudio_pipeline_runtime.a" | awk '{print $3}' | grep '^ap_' | sort -u > "$TMP/$side-runtime-symbols"
done
diff -u "$TMP/base-abi" "$TMP/head-abi"
comm -23 "$TMP/base-core-symbols" "$TMP/head-core-symbols" > "$TMP/missing-core"
comm -23 "$TMP/base-runtime-symbols" "$TMP/head-runtime-symbols" > "$TMP/missing-runtime"
if [ -s "$TMP/missing-core" ] || [ -s "$TMP/missing-runtime" ]; then
  echo 'ABI/API regression: released symbols disappeared' >&2
  cat "$TMP/missing-core" "$TMP/missing-runtime" >&2
  exit 3
fi
echo "ABI/API additive contract OK against $BASE_REF"
