#!/bin/sh
# Optional exact-compiler research build; not a device benchmark or publication.
set -eu

: "${CC:?set CC to an existing C compiler executable for a research target}"
BUILD_DIR=${BUILD_DIR:-build/research-toolchain}
SYSROOT=${SYSROOT:-}
CFLAGS=${CFLAGS:-}

if ! command -v "$CC" >/dev/null 2>&1; then
  echo 'RESEARCH_COMPILER_UNAVAILABLE' >&2
  exit 2
fi

set -- -S . -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
set -- "$@" "-DCMAKE_C_COMPILER=$CC" -DAP_BUILD_TESTS=OFF -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF
if [ -n "$SYSROOT" ]; then
  set -- "$@" "-DCMAKE_SYSROOT=$SYSROOT"
fi
if [ -n "$CFLAGS" ]; then
  set -- "$@" "-DCMAKE_C_FLAGS=$CFLAGS"
fi
cmake "$@"
cmake --build "$BUILD_DIR" --parallel
cmake --install "$BUILD_DIR" --prefix "$BUILD_DIR/stage"

printf "research_compiler=%s\n" "$("$CC" --version 2>/dev/null | head -n 1 || true)"
printf "research_sysroot=%s\n" "${SYSROOT:-none}"
if command -v size >/dev/null 2>&1; then
  size "$BUILD_DIR/libaudio_pipeline.a" 2>/dev/null || true
fi
