#!/usr/bin/env python3
"""Reproduce frozen v2.3.60 processor false-success paths using stdio unit inputs.

The historical processor bytes link to the current unchanged core. This is an
I/O regression control, not a reconstruction of the historical release binary.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = "11d575a4ba1969384b3631775ab55283b3f2fc83"
SOURCE_SHA256 = "65b6fcaf028f1e2de72dc95144ed7d03083fa60a272d40420b1d8a057971bf0c"
CASES = (
    "capture-odd", "capture-partial-frame", "capture-partial-channel",
    "render-odd", "capture-read-error", "render-read-error",
    "output-close-error", "metrics-close-error", "input-close-error",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()
    build = args.build_dir.resolve()
    source = subprocess.run(
        ["git", "show", BASE + ":examples/process_pcm.c"],
        cwd=ROOT, check=True, capture_output=True, timeout=20,
    ).stdout
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("frozen predecessor processor identity changed")
    with tempfile.TemporaryDirectory(prefix="pcm-legacy-control-") as directory:
        work = Path(directory)
        frozen = work / "process_pcm_v2360.c"
        frozen.write_bytes(source)
        executable = work / "legacy-stdio-test"
        subprocess.run([
            args.cc, "-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
            "-UNDEBUG", "-O1",
            '-DAP_PROCESS_PCM_SOURCE="' + str(frozen) + '"',
            "-I" + str(ROOT / "include"), "-I" + str(build / "generated"),
            str(ROOT / "tests/test_process_pcm_io.c"),
            str(build / "libaudio_pipeline.a"), "-lm", "-o", str(executable),
        ], cwd=ROOT, check=True, timeout=30)
        for case in CASES:
            subprocess.run([str(executable), "--legacy-detection", case],
                           cwd=work, check=True, timeout=10)
    print("PCM_LEGACY_FALSE_SUCCESS_CONTROLS_REPRODUCED count=9 source=" + BASE)


if __name__ == "__main__":
    main()
