#!/usr/bin/env python3
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

CANDIDATES = ("0.15", "0.20", "0.25", "0.30")
SEEDS = (1307, 2307, 3307)


def run(cmd, cwd, check=True):
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}")
    return proc


def macro_default(path, name):
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"^#define\s+{re.escape(name)}\s+([0-9]+(?:\.[0-9]+)?)f\s*$", text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"cannot resolve {name} from {path}")
    return f"{float(match.group(1)):.2f}"


def compile_scalar(root, work, alpha):
    binary = work / f"scalar-{alpha.replace('.', '_')}"
    cmd = [
        "cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
        "-DAP_BUILD_STAGE_RES=1",
        f"-DAP_RES_NEAR_PROTECTION_RELEASE_ALPHA={alpha}f",
        "-Isrc",
        "tests/validation/activity_res_handoff_probe.c",
        "src/activity/ap_activity.c",
        "src/enhance/ap_res.c",
        "-lm", "-o", str(binary),
    ]
    run(cmd, root)
    return binary


def compile_frequency(root, work, alpha):
    token = alpha.replace(".", "_")
    build = work / f"freq-build-{token}"
    binary = work / f"freq-{token}"
    run([
        "cmake", "-S", ".", "-B", str(build),
        "-DCMAKE_BUILD_TYPE=Release",
        "-DAP_BUILD_PIPELINE=OFF",
        "-DAP_MODULES=NS,RES",
        "-DAP_BUILD_TESTS=OFF",
        "-DAP_BUILD_BENCH=OFF",
        "-DAP_BUILD_EXAMPLES=OFF",
        "-DAP_ENABLE_LINUX_RUNTIME=OFF",
        "-DAP_NS_ESTIMATOR=EMA",
        "-DAP_STRICT_WARNINGS=ON",
        f"-DCMAKE_C_FLAGS=-DAP_FREQ_RES_NEAR_PROTECTION_RELEASE_ALPHA={alpha}f",
    ], root)
    run(["cmake", "--build", str(build), "--target", "audio_pipeline", "--parallel"], root)
    run([
        "cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
        "-DAP_BUILD_STAGE_RES=1", "-DAP_BUILD_STAGE_NS=1", "-DAP_BUILD_NS_EMA=1",
        f"-I{build / 'generated'}", "-Isrc",
        "tests/validation/frequency_res_handoff_probe.c",
        str(build / "libaudio_pipeline.a"), "-lm", "-o", str(binary),
    ], root)
    return binary


def exercise(binary, root):
    runs = []
    passed = True
    for seed in SEEDS:
        proc = run([str(binary), str(seed)], root, check=False)
        runs.append({"seed": seed, "returncode": proc.returncode, "output": proc.stdout.strip()})
        if proc.returncode != 0:
            passed = False
    return passed, runs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--work-dir", default="build/res-release-sweep")
    args = parser.parse_args()

    root = pathlib.Path(__file__).resolve().parents[2]
    work = root / args.work_dir
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    scalar_default = macro_default(root / "src/enhance/ap_res.c", "AP_RES_NEAR_PROTECTION_RELEASE_ALPHA")
    frequency_default = macro_default(root / "src/enhance/ap_ns.c", "AP_FREQ_RES_NEAR_PROTECTION_RELEASE_ALPHA")

    rows = []
    for alpha in CANDIDATES:
        scalar_bin = compile_scalar(root, work, alpha)
        scalar_pass, scalar_runs = exercise(scalar_bin, root)
        frequency_bin = compile_frequency(root, work, alpha)
        frequency_pass, frequency_runs = exercise(frequency_bin, root)
        rows.append({
            "alpha": alpha,
            "scalar_pass": scalar_pass,
            "frequency_pass": frequency_pass,
            "eligible": scalar_pass and frequency_pass,
            "scalar_runs": scalar_runs,
            "frequency_runs": frequency_runs,
        })

    eligible = [row["alpha"] for row in rows if row["eligible"]]
    selected = eligible[0] if eligible else None
    report = {
        "schema_version": 1,
        "selection_rule": "smallest candidate passing scalar and frequency three-seed recovery/re-entry gates",
        "candidates": list(CANDIDATES),
        "seeds": list(SEEDS),
        "shipping_scalar_alpha": scalar_default,
        "shipping_frequency_alpha": frequency_default,
        "selected_alpha": selected,
        "rows": rows,
    }
    out = root / args.json_output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("RES release bounded sweep")
    print("alpha  scalar  frequency  eligible")
    for row in rows:
        print(f"{row['alpha']:>4}   {str(row['scalar_pass']):>5}      {str(row['frequency_pass']):>5}      {str(row['eligible']):>5}")
    print(f"selected={selected} shipping_scalar={scalar_default} shipping_frequency={frequency_default}")

    if selected is None:
        print("no bounded release candidate passes all gates", file=sys.stderr)
        return 1
    if scalar_default != selected or frequency_default != selected:
        print(
            f"shipping default must equal minimal passing alpha {selected}; "
            f"got scalar={scalar_default} frequency={frequency_default}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
