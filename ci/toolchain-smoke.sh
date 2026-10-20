#!/bin/sh
# Execute the repository tests with each compiler shipped by the CI image.
set -eu

repo_root=$(pwd)
evidence=${1:?absolute evidence directory required}
case "$evidence" in /*) ;; *) echo 'evidence path must be absolute' >&2; exit 2 ;; esac
test -n "${SOURCE_SHA:-}"
test "$(git -c "safe.directory=$repo_root" rev-parse HEAD)" = "$SOURCE_SHA"
mkdir -p "$evidence"
test ! -e "$evidence/receipt.json"
build_root=$(mktemp -d /tmp/ap-toolchain-smoke.XXXXXX)
trap 'rm -rf "$build_root"' EXIT INT TERM

{
    gcc --version
    clang --version
    scan-build --help
    cmake --version
    ninja --version
    arm-linux-gnueabihf-gcc --version
    aarch64-linux-gnu-gcc --version
    qemu-arm --version
    qemu-aarch64 --version
    arecord --version
    pkg-config --modversion alsa
    gcovr --version
    ccache --version
    dpkg-query -W
} > "$evidence/tool-versions.log" 2>&1

for profile in gcc clang armhf aarch64; do
    build="$build_root/$profile"
    set -- -S "$repo_root" -B "$build" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release -DAP_STRICT_WARNINGS=ON \
        -DAP_BUILD_TESTS=ON -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF \
        -DAP_ENABLE_LINUX_RUNTIME=ON
    case "$profile" in
        gcc) set -- "$@" -DCMAKE_C_COMPILER=gcc ;;
        clang) set -- "$@" -DCMAKE_C_COMPILER=clang ;;
        armhf)
            set -- "$@" \
                "-DCMAKE_TOOLCHAIN_FILE=$repo_root/cmake/toolchains/arm-linux-gnueabihf.cmake" \
                '-DCMAKE_C_FLAGS=-O2 -mcpu=cortex-a32 -mfpu=neon-fp-armv8 -mfloat-abi=hard' \
                -DAP_SIMD_BACKEND=NEON \
                '-DCMAKE_CROSSCOMPILING_EMULATOR=qemu-arm;-cpu;max;-L;/usr/arm-linux-gnueabihf'
            ;;
        aarch64)
            set -- "$@" \
                "-DCMAKE_TOOLCHAIN_FILE=$repo_root/cmake/toolchains/aarch64-linux-gnu.cmake" \
                '-DCMAKE_C_FLAGS=-O2 -march=armv8-a' -DAP_SIMD_BACKEND=NEON \
                '-DCMAKE_CROSSCOMPILING_EMULATOR=qemu-aarch64;-L;/usr/aarch64-linux-gnu'
            ;;
    esac
    cmake "$@" > "$evidence/$profile-configure.log" 2>&1
    cmake --build "$build" --parallel 4 > "$evidence/$profile-build.log" 2>&1
    ctest --test-dir "$build" --output-on-failure \
        --output-junit "$evidence/$profile-junit.xml" \
        > "$evidence/$profile-ctest.log" 2>&1
    readelf -h "$build/ap_runtime_tests" > "$evidence/$profile-elf.txt"
    (cd "$build" && sha256sum ap_*tests) > "$evidence/$profile-binaries.sha256"
done

python3 - "$repo_root" "$evidence" "$SOURCE_SHA" <<'PY'
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

repo, evidence = map(Path, sys.argv[1:3])
source_sha = sys.argv[3]
if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None:
    raise SystemExit("invalid source identity")
required = {"ap_runtime_tests", "ap_runtime_extended_tests"}
if (repo / "tests/test_runtime_interleavings.c").exists():
    required.add("ap_runtime_interleaving_tests")
profiles = []
for name in ("gcc", "clang", "armhf", "aarch64"):
    cases = list(ET.parse(evidence / f"{name}-junit.xml").getroot().iter("testcase"))
    names = [case.attrib["name"] for case in cases]
    if len(names) != len(set(names)) or not required.issubset(names):
        raise SystemExit(f"{name}: missing or duplicate runtime tests")
    if not cases or any(case.find(x) is not None for case in cases
                        for x in ("failure", "error", "skipped")):
        raise SystemExit(f"{name}: incomplete or unsuccessful execution")
    elf = (evidence / f"{name}-elf.txt").read_text()
    if name == "armhf" and ("ELF32" not in elf or re.search(r"Machine:\s+ARM\s", elf) is None):
        raise SystemExit("armhf execution lacks its expected ELF identity")
    if name == "aarch64" and ("ELF64" not in elf or "AArch64" not in elf):
        raise SystemExit("aarch64 execution lacks its expected ELF identity")
    profiles.append({"name": name, "tests": len(cases), "failed": 0,
                     "skipped": 0, "emulated": name in ("armhf", "aarch64")})
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
receipt = {"schema": 1, "decision": "CI_IMAGE_SOFTWARE_EXECUTION_PASS",
           "source_sha": source_sha, "profiles": profiles,
           "dockerfile_sha256": sha(repo / "ci/Dockerfile"),
           "smoke_script_sha256": sha(repo / "ci/toolchain-smoke.sh"),
           "ssc305_silicon_execution": False, "hil_evidence": False}
(evidence / "receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
files = sorted(p for p in evidence.iterdir() if p.is_file() and p.name != "SHA256SUMS")
(evidence / "SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in files))
PY
