#!/bin/sh
set -eu
ROOT=$(pwd)
BASE_REF=${1:-v2.0.0}
TMP=$(mktemp -d)
trap 'git worktree remove --force "$TMP/base" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT INT TERM

git config --global --add safe.directory "$ROOT"

git fetch origin "refs/tags/$BASE_REF:refs/tags/$BASE_REF" --force >/dev/null 2>&1 || {
    echo "public API/ABI contract: unable to fetch required baseline tag $BASE_REF" >&2
    exit 6
}
BASE_SHA=$(git rev-parse -q --verify "refs/tags/$BASE_REF^{commit}") || {
    echo "public API/ABI contract: required baseline tag $BASE_REF does not resolve to a commit" >&2
    exit 6
}

retired_public='ap_build_info_v2_t ap_build_info_v2_get ap_runtime_init_ex ap_runtime_submit_ex ap_runtime_metrics_v2_t ap_runtime_metrics_v3_t ap_runtime_get_metrics_v2 ap_runtime_get_metrics_v3 AP_RUNTIME_METRICS_V3_API_VERSION AP_RUNTIME_CONTROL_API_VERSION'
for token in $retired_public; do
    if grep -R -n -F "$token" include/audio_pipeline; then
        echo "public API contract violation: retired public token reintroduced: $token" >&2
        exit 2
    fi
done

cmake -S "$ROOT" -B "$TMP/head-build" -DCMAKE_BUILD_TYPE=Release \
    -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF >/dev/null
cmake --build "$TMP/head-build" --parallel >/dev/null
cc "$ROOT/tests/abi_probe.c" -I"$ROOT/include" -I"$TMP/head-build/generated" \
    -o "$TMP/head-probe"
"$TMP/head-probe" | sort > "$TMP/head-abi"

nm -g --defined-only "$TMP/head-build/libaudio_pipeline.a" | awk '{print $3}' | grep '^ap_' | sort -u > "$TMP/head-core-symbols"
nm -g --defined-only "$TMP/head-build/libaudio_pipeline_runtime.a" | awk '{print $3}' | grep '^ap_' | sort -u > "$TMP/head-runtime-symbols"

for symbol in ap_build_info; do
    grep -Fxq "$symbol" "$TMP/head-core-symbols" || {
        echo "public ABI contract: missing required core symbol $symbol" >&2; exit 3;
    }
done
for symbol in ap_runtime_open ap_runtime_submit_frame ap_runtime_read_metrics; do
    grep -Fxq "$symbol" "$TMP/head-runtime-symbols" || {
        echo "public ABI contract: missing required runtime symbol $symbol" >&2; exit 3;
    }
done
for symbol in \
    ap_build_info_v2_get \
    ap_runtime_init ap_runtime_init_ex \
    ap_runtime_submit ap_runtime_submit_ex \
    ap_runtime_get_metrics ap_runtime_get_metrics_v2 ap_runtime_get_metrics_v3; do
    if grep -Fxq "$symbol" "$TMP/head-core-symbols" || grep -Fxq "$symbol" "$TMP/head-runtime-symbols"; then
        echo "public API contract violation: retired exported symbol reintroduced: $symbol" >&2
        exit 4
    fi
done

current=$(git rev-parse HEAD)
if [ "$current" != "$BASE_SHA" ]; then
    git worktree add --detach "$TMP/base" "$BASE_SHA" >/dev/null
    cmake -S "$TMP/base" -B "$TMP/base-build" -DCMAKE_BUILD_TYPE=Release \
        -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF >/dev/null
    cmake --build "$TMP/base-build" --parallel >/dev/null
    cc "$ROOT/tests/abi_probe.c" -I"$TMP/base/include" -I"$TMP/base-build/generated" \
        -o "$TMP/base-probe"
    "$TMP/base-probe" | sort > "$TMP/base-abi"
    diff -u "$TMP/base-abi" "$TMP/head-abi"
    nm -g --defined-only "$TMP/base-build/libaudio_pipeline.a" | awk '{print $3}' | grep '^ap_' | sort -u > "$TMP/base-core-symbols"
    nm -g --defined-only "$TMP/base-build/libaudio_pipeline_runtime.a" | awk '{print $3}' | grep '^ap_' | sort -u > "$TMP/base-runtime-symbols"
    comm -23 "$TMP/base-core-symbols" "$TMP/head-core-symbols" > "$TMP/missing-core"
    comm -23 "$TMP/base-runtime-symbols" "$TMP/head-runtime-symbols" > "$TMP/missing-runtime"
    if [ -s "$TMP/missing-core" ] || [ -s "$TMP/missing-runtime" ]; then
        echo "public ABI regression: symbols from required baseline $BASE_REF disappeared" >&2
        cat "$TMP/missing-core" "$TMP/missing-runtime" >&2
        exit 5
    fi
fi

echo "public API/ABI contract OK against required baseline $BASE_REF ($BASE_SHA)"
