#!/usr/bin/env python3
"""Bind I004 root-cause differential tooling to the exact diagnostic baseline source."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_TOOL = ROOT / "tests/validation/i004_ns_nonstationary_diagnostic.py"
DIFFERENTIAL_TOOL = ROOT / "tests/validation/i004_ns_root_cause_differential.py"
ALLOWED_RESEARCH_FILES = {
    ".github/workflows/i004-ns-baseline-diagnostic.yml",
    "docs/program/iterations/I004.json",
    "tests/validation/i004_ns_exact_base_entry.py",
    "tests/validation/i004_ns_nonstationary_diagnostic.py",
    ".github/workflows/i004-ns-root-cause-differential.yml",
    "docs/program/iterations/I004-differential.json",
    "tests/validation/i004_ns_root_cause_entry.py",
    "tests/validation/i004_ns_root_cause_differential.py",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def run(argv: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(
        argv, cwd=str(cwd) if cwd else None, check=True, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return result.stdout.strip() if capture else ""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_scope(base_sha: str) -> tuple[str, list[str]]:
    require(re.fullmatch(r"[0-9a-f]{40}", base_sha) is not None, "invalid base SHA")
    head = run(["git", "rev-parse", "HEAD"], ROOT, True)
    merge_base = run(["git", "merge-base", "HEAD", base_sha], ROOT, True)
    require(merge_base == base_sha, f"research history does not descend from exact base: {merge_base}")
    changed = [line for line in run(["git", "diff", "--name-only", f"{base_sha}...HEAD"], ROOT, True).splitlines() if line]
    unexpected = sorted(set(changed) - ALLOWED_RESEARCH_FILES)
    require(not unexpected, "unexpected I004 research scope: " + ", ".join(unexpected))
    forbidden_prefixes = ("src/", "include/", "cmake/", "certification/")
    require(all(not path.startswith(forbidden_prefixes) for path in changed), "shipping source/API/build/certification diff")
    require(all(path not in changed for path in ("CMakeLists.txt", "CHANGELOG.md", "validation/datasets.lock.json")),
            "shipping version/dataset diff")
    return head, sorted(changed)


def refresh_manifest(output: Path, binding: dict) -> None:
    for name in ("build-ema", "build-mcra"):
        path = output / name
        if path.exists():
            shutil.rmtree(path)
    write_json(output / "execution-binding.json", binding)
    files = {
        str(path.relative_to(output)): sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name not in {"SHA256SUMS", "evidence-manifest.json"}
    }
    write_json(output / "evidence-manifest.json", {
        "schema_version": 1,
        "baseline_source_sha": binding["baseline_source_sha"],
        "research_head_sha": binding["research_head_sha"],
        "files": files,
    })
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(files.items()):
            handle.write(f"{digest}  {rel}\n")


def self_test() -> None:
    require(all(not path.startswith(("src/", "include/", "cmake/", "certification/"))
                for path in ALLOWED_RESEARCH_FILES), "allowed scope contains shipping path")
    require(BASELINE_TOOL.name == "i004_ns_nonstationary_diagnostic.py", "baseline tool binding")
    require(DIFFERENTIAL_TOOL.name == "i004_ns_root_cause_differential.py", "differential tool binding")
    print(json.dumps({"result": "PASS", "authority": "exact-base-differential-entry-only"}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.contract is not None and args.output is not None, "contract/output required")
    contract_path = args.contract.resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    require(contract.get("schema_version") == 1 and contract.get("iteration_id") == "I004" and
            contract.get("phase") == "root-cause-differential", "differential contract identity")
    base_sha = contract["base_sha"]
    research_head, changed = validate_scope(base_sha)
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")

    with tempfile.TemporaryDirectory(prefix="ap-i004-diff-base-") as temporary:
        base_root = Path(temporary) / "repo"
        run(["git", "worktree", "add", "--detach", str(base_root), base_sha], ROOT)
        try:
            require(run(["git", "rev-parse", "HEAD"], base_root, True) == base_sha, "worktree base mismatch")
            tools = base_root / "tests/validation"
            tools.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BASELINE_TOOL, tools / BASELINE_TOOL.name)
            shutil.copy2(DIFFERENTIAL_TOOL, tools / DIFFERENTIAL_TOOL.name)
            code = subprocess.run([
                sys.executable, str(tools / DIFFERENTIAL_TOOL.name),
                "--contract", str(contract_path), "--output", str(output),
            ], cwd=base_root).returncode
            require(code == 0, f"differential returned {code}")
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(base_root)], cwd=ROOT, check=False)

    report = json.loads((output / "root-cause-report.json").read_text(encoding="utf-8"))
    binding = {
        "schema_version": 1,
        "authority": "research-counterfactual-over-exact-baseline",
        "baseline_source_sha": base_sha,
        "research_head_sha": research_head,
        "merge_base_sha": base_sha,
        "research_changed_files": changed,
        "shipping_diff_zero": True,
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "processors": report["processors"],
        "baseline_tool_sha256": sha256(BASELINE_TOOL),
        "differential_tool_sha256": sha256(DIFFERENTIAL_TOOL),
    }
    refresh_manifest(output, binding)
    print(json.dumps({
        "decision": report["decision"],
        "evidence_path": report["summary"]["evidence_path"]["conclusion"],
        "estimator": report["summary"]["estimator"]["conclusion"],
        "baseline_source_sha": base_sha,
        "research_head_sha": research_head,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise SystemExit(f"I004 differential entry error: {exc}")
