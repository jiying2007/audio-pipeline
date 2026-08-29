#!/bin/sh
set -eu

: "${CC:?set CC to the shipping C compiler}"
BUILD_DIR=${BUILD_DIR:-build/shipping-toolchain}
SYSROOT=${SYSROOT:-}
CFLAGS=${CFLAGS:-}

args="-S . -B $BUILD_DIR -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=$CC -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF"
if [ -n "$SYSROOT" ]; then
    args="$args -DCMAKE_SYSROOT=$SYSROOT"
fi
if [ -n "$CFLAGS" ]; then
    args="$args -DCMAKE_C_FLAGS=$CFLAGS"
fi
# shellcheck disable=SC2086
cmake $args
cmake --build "$BUILD_DIR" --parallel
cmake --install "$BUILD_DIR" --prefix "$BUILD_DIR/stage"

echo "shipping_toolchain_compiler=$($CC --version 2>/dev/null | head -n1 || true)"
echo "shipping_toolchain_sysroot=${SYSROOT:-none}"
if command -v size >/dev/null 2>&1; then
    size "$BUILD_DIR/libaudio_pipeline.a" 2>/dev/null || true
fi
