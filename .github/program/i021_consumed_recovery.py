#!/usr/bin/env python3
"""Recover the already-consumed I021 diagnostic after a pre-result framing failure."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / (
    ".github/research/continuous-optimization/development-v4/"
    "i021-consumed-diagnostic-tail-frame-recovery-v1.json"
)
WORKFLOW_FILE = "i021-consumed-diagnostic-recovery.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def encoded(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob(ref: str, path: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", f"{ref}:{path}"], cwd=ROOT, text=True
    ).strip()


def current_blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", path], cwd=ROOT, text=True
    ).strip()


def validate_contract(manifest: dict[str, Any]) -> dict[str, Any]:
    require(manifest["schema_version"] == 1, "recovery schema drift")
    require(manifest["status"] == "FROZEN_RECOVERY_CONTRACT", "recovery contract is not frozen")
    failed = manifest["failed_execution"]
    frozen = manifest["frozen_inputs"]
    repair = manifest["repair"]
    boundary = manifest["authority_boundary"]

    require(failed["run_id"] == 36417062971, "failed run identity drift")
    require(failed["run_attempt"] == 1, "failed run attempt drift")
    require(failed["diagnose_job_id"] == 108910684840, "failed job identity drift")
    require(failed["head_sha"] == "d6e8c145d66aef119c0e9d166e52de9af1f54202",
            "failed head drift")
    require(failed["event"] == "workflow_dispatch" and failed["conclusion"] == "failure",
            "failed run state drift")
    require(failed["artifact_count"] == 0, "failed run unexpectedly had artifacts")
    require(failed["reviewed_failure_signature"] == {
        "case_id": "public-dev-mix-009",
        "probe_exit_code": 5,
        "meaning": (
            "The probe rejected a final partial 160-sample frame before any "
            "result.json was written. Corpus materialization completed successfully."
        ),
    }, "failure signature drift")

    require(frozen["seeds"] == [501307, 511307, 521307], "recovery seeds drift")
    require(
        [frozen["mix_limit_per_seed"], frozen["noise_limit_per_seed"],
         frozen["clean_limit_per_seed"]] == [28, 14, 14],
        "recovery case limits drift",
    )
    contract = load_json(ROOT / frozen["contract_path"])
    require(contract["investigation_id"] == frozen["investigation_id"], "I021 contract identity drift")
    require(contract["fresh_diagnostic_authority"]["seeds"] == frozen["seeds"],
            "I021 contract seed drift")
    require(contract["fresh_diagnostic_authority"]["diagnostic_execution_limit"] == 1,
            "I021 diagnostic limit drift")
    require(contract["fresh_diagnostic_authority"]["candidate_limit"] == 0,
            "I021 candidate budget drift")
    require(contract["fresh_diagnostic_authority"]["confirmation_limit"] == 0,
            "I021 confirmation budget drift")
    require(all(value is False for value in contract["authority_boundary"].values()),
            "I021 authority boundary drift")

    frozen_blobs = {
        frozen["contract_path"]: frozen["contract_blob_sha"],
        frozen["dataset_lock_path"]: frozen["dataset_lock_blob_sha"],
        frozen["builder_path"]: frozen["builder_blob_sha"],
        frozen["materializer_path"]: frozen["materializer_blob_sha"],
        frozen["evaluator_path"]: frozen["evaluator_blob_sha"],
        failed["workflow_path"]: frozen["failed_workflow_blob_sha"],
    }
    for path, expected in frozen_blobs.items():
        require(current_blob(path) == expected, "current frozen input blob drift: " + path)
        require(git_blob(failed["head_sha"], path) == expected,
                "failed-head frozen input blob drift: " + path)

    probe_path = frozen["failed_probe_path"]
    require(git_blob(failed["head_sha"], probe_path) == frozen["failed_probe_blob_sha"],
            "failed probe blob drift")
    require(current_blob(probe_path) == repair["repaired_probe_blob_sha"],
            "repaired probe blob drift")
    probe_text = (ROOT / probe_path).read_text(encoding="utf-8")
    require("if (got != FRAME) break;" in probe_text, "partial-frame repair missing")
    require("return 5;" not in probe_text, "partial-frame hard failure remains")
    require(repair["class"] == "MECHANICAL_INPUT_FRAMING_ONLY", "repair class drift")
    for key in (
        "shipping_source_changed", "dataset_changed", "seed_changed",
        "evaluator_changed", "candidate_selected", "threshold_changed", "hold_changed",
    ):
        require(repair[key] is False, "repair authority drift: " + key)

    require(manifest["recovery_execution"]["required_parent_sha"] == failed["head_sha"],
            "recovery parent binding drift")
    require(manifest["recovery_execution"]["maximum_successful_recoveries"] == 1,
            "recovery multiplicity drift")
    require(manifest["recovery_execution"]["rebuild_same_consumed_inputs_only"] is True,
            "recovery input boundary drift")
    require(all(value is False for value in boundary.values()),
            "recovery authority escalation")
    return contract


def gh_json(endpoint: str) -> Any:
    raw = subprocess.check_output(
        ["gh", "api", "--hostname", "github.com", endpoint],
        text=True,
        timeout=120,
    )
    return json.loads(raw)


def validate_failed_execution(manifest: dict[str, Any]) -> None:
    repo = os.environ.get("GITHUB_REPOSITORY")
    require(repo == "jiying2007/audio-pipeline", "foreign executing repository")
    failed = manifest["failed_execution"]
    run = gh_json(f"repos/{repo}/actions/runs/{failed['run_id']}")
    require(run["id"] == failed["run_id"], "failed run id mismatch")
    require(run["run_attempt"] == failed["run_attempt"], "failed run attempt mismatch")
    require(run["head_sha"] == failed["head_sha"], "failed run head mismatch")
    require(run["event"] == failed["event"], "failed run event mismatch")
    require(run["status"] == "completed" and run["conclusion"] == failed["conclusion"],
            "failed run is not terminal failure")

    jobs = gh_json(f"repos/{repo}/actions/runs/{failed['run_id']}/jobs?per_page=100")
    matches = [job for job in jobs.get("jobs", []) if job["id"] == failed["diagnose_job_id"]]
    require(len(matches) == 1, "failed diagnose job missing")
    job = matches[0]
    require(job["conclusion"] == "failure", "failed diagnose job conclusion drift")
    steps = {step["name"]: step.get("conclusion") for step in job.get("steps", [])}
    for name, expected in failed["required_step_state"].items():
        require(steps.get(name) == expected, f"failed run step drift: {name}")

    artifacts = gh_json(f"repos/{repo}/actions/runs/{failed['run_id']}/artifacts?per_page=100")
    require(artifacts.get("total_count") == failed["artifact_count"],
            "failed run artifact count drift")


def validate_trusted_push(manifest: dict[str, Any]) -> tuple[str, str]:
    require(os.environ.get("GITHUB_EVENT_NAME") == "push", "recovery requires trusted main push")
    require(os.environ.get("GITHUB_REF") == "refs/heads/main", "recovery requires main")
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "recovery rerun is forbidden")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    parent = subprocess.check_output(["git", "rev-parse", "HEAD^1"], cwd=ROOT, text=True).strip()
    require(head == os.environ.get("GITHUB_SHA"), "checkout/head mismatch")
    require(parent == manifest["recovery_execution"]["required_parent_sha"],
            "main moved before deterministic recovery")
    return head, parent


def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, check=True, **kwargs)


def file_manifest(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        files.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return {"root": str(root), "files": files}


def reconstruct_and_evaluate(
    manifest: dict[str, Any], contract: dict[str, Any], probe: Path, output: Path
) -> dict[str, Any]:
    frozen = manifest["frozen_inputs"]
    work = Path("/tmp/i021-consumed-recovery")
    data_root = work / "development-v3"
    materialization = work / "materialization.json"
    corpora_root = work / "corpora"
    output.mkdir(parents=True, exist_ok=True)

    run([
        sys.executable, frozen["materializer_path"],
        "--lock", frozen["dataset_lock_path"],
        "--root", str(data_root),
        "--output", str(materialization),
    ])

    corpus_paths: list[Path] = []
    identities: dict[str, Any] = {}
    for seed in frozen["seeds"]:
        corpus_dir = corpora_root / str(seed)
        run([
            sys.executable, frozen["builder_path"],
            "--lock", frozen["dataset_lock_path"],
            "--materialization", str(materialization),
            "--data-root", str(data_root),
            "--output", str(corpus_dir),
            "--seed", str(seed),
            "--mix-limit", str(frozen["mix_limit_per_seed"]),
            "--noise-limit", str(frozen["noise_limit_per_seed"]),
            "--clean-limit", str(frozen["clean_limit_per_seed"]),
        ])
        corpus = corpus_dir / "corpus.json"
        corpus_paths.append(corpus)
        identities[str(seed)] = file_manifest(corpus_dir)
        (output / f"corpus-{seed}.json").write_bytes(corpus.read_bytes())

    (output / "corpus-reconstruction.json").write_bytes(encoded({
        "schema_version": 1,
        "authority": "RECOVERY_OF_CONSUMED_DIAGNOSTIC_ONLY",
        "failed_run_id": manifest["failed_execution"]["run_id"],
        "seeds": frozen["seeds"],
        "dataset_lock_blob_sha": frozen["dataset_lock_blob_sha"],
        "builder_blob_sha": frozen["builder_blob_sha"],
        "materializer_blob_sha": frozen["materializer_blob_sha"],
        "corpora": identities,
    }))

    result_path = output / "result.json"
    command = [
        sys.executable, frozen["evaluator_path"],
        "--probe", str(probe),
        "--contract", frozen["contract_path"],
    ]
    for corpus in corpus_paths:
        command += ["--corpus", str(corpus)]
    command += ["--output", str(result_path)]
    process = subprocess.run(command, cwd=ROOT, text=True, check=False)
    require(result_path.is_file(), "recovery evaluator did not produce result.json")
    result = load_json(result_path)

    require(result["investigation_id"] == frozen["investigation_id"], "recovery result identity drift")
    require(result["source_base_sha"] == frozen["source_base_sha"], "recovery source drift")
    require(result["fresh_diagnostic_seeds"] == frozen["seeds"], "recovery result seed drift")
    require(result["candidate_budget_consumed"] == 0, "recovery gained candidate authority")
    require(result["confirmation_budget_consumed"] == 0, "recovery gained confirmation authority")
    require(all(value is False for value in result["authority_boundary"].values()),
            "recovery result authority escalation")
    require(result["shipping_mirror"]["active_mismatch_frames"] == 0,
            "shipping mirror active mismatch")
    require(
        float(result["shipping_mirror"]["max_probability_delta"])
        <= float(contract["diagnostic_gates"]["max_shipping_mirror_probability_delta"]),
        "shipping mirror probability mismatch",
    )
    require(result["invalid_reasons"] == [], "recovered I021 input is invalid")
    require(result["decision"] in {
        "PUBLIC_DEVELOPMENT_VAD_TRANSFER_GAP_DECOMPOSED_REVIEW_REQUIRED",
        "PUBLIC_DEVELOPMENT_VAD_BASELINE_ADEQUATE_REVIEW_REQUIRED",
    }, "unexpected recovery decision")
    require(process.returncode == 0, "recovery evaluator returned non-zero after valid result")

    (output / "contract.json").write_bytes((ROOT / frozen["contract_path"]).read_bytes())
    (output / "materialization.json").write_bytes(materialization.read_bytes())
    (output / "probe.sha256").write_text(sha256_file(probe) + "\n", encoding="utf-8")
    summary = {
        "decision": result["decision"],
        "invalid_reasons": result["invalid_reasons"],
        "fresh_diagnostic_seeds": result["fresh_diagnostic_seeds"],
        "global": result["global"],
        "reference_absolute_min_vad_f1": result["reference_absolute_min_vad_f1"],
        "below_reference_slice_count": len(result["below_reference_slices"]),
        "worst_development_slices": result["worst_development_slices"],
        "shipping_mirror": result["shipping_mirror"],
    }
    (output / "summary.json").write_bytes(encoded(summary))
    return result


def write_receipt(
    manifest: dict[str, Any], result: dict[str, Any], head: str, output: Path
) -> None:
    receipt = {
        "schema_version": 1,
        "authority": "RECOVERY_OF_CONSUMED_DIAGNOSTIC_ONLY",
        "failed_run_id": manifest["failed_execution"]["run_id"],
        "failed_job_id": manifest["failed_execution"]["diagnose_job_id"],
        "authority_owner_run_id": manifest["failed_execution"]["run_id"],
        "recovery_run_id": int(os.environ["GITHUB_RUN_ID"]),
        "recovery_run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "recovery_head_sha": head,
        "same_consumed_seeds": manifest["frozen_inputs"]["seeds"],
        "repair_class": manifest["repair"]["class"],
        "decision": result["decision"],
        "new_diagnostic_authority": False,
        "new_candidate_authority": False,
        "new_confirmation_authority": False,
        "shipping_authority": False,
        "source_merge_authority": False,
        "hil_authority": False,
        "product_certification_authority": False,
        "release_authority": False,
    }
    (output / "recovery-receipt.json").write_bytes(encoded(receipt))
    members = sorted(p for p in output.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in members),
        encoding="utf-8",
    )


def check() -> dict[str, Any]:
    manifest = load_json(MANIFEST)
    contract = validate_contract(manifest)
    return {
        "status": "RECOVERY_CONTRACT_VALID",
        "investigation_id": contract["investigation_id"],
        "failed_run_id": manifest["failed_execution"]["run_id"],
        "seeds": manifest["frozen_inputs"]["seeds"],
        "repaired_probe_blob_sha": manifest["repair"]["repaired_probe_blob_sha"],
    }


def recover(probe: Path, output: Path) -> dict[str, Any]:
    manifest = load_json(MANIFEST)
    contract = validate_contract(manifest)
    head, parent = validate_trusted_push(manifest)
    validate_failed_execution(manifest)
    require(probe.is_file(), "recovery probe missing")
    require(current_blob(manifest["frozen_inputs"]["failed_probe_path"])
            == manifest["repair"]["repaired_probe_blob_sha"],
            "recovery probe identity changed")
    result = reconstruct_and_evaluate(manifest, contract, probe, output)
    write_receipt(manifest, result, head, output)
    return {
        "status": "RECOVERED_CONSUMED_I021_DIAGNOSTIC",
        "failed_run_id": manifest["failed_execution"]["run_id"],
        "recovery_run_id": int(os.environ["GITHUB_RUN_ID"]),
        "recovery_head_sha": head,
        "required_parent_sha": parent,
        "decision": result["decision"],
        "global_f1": result["global"]["f1"],
        "below_reference_slices": len(result["below_reference_slices"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--output", type=Path, default=Path("i021-recovery-out"))
    args = parser.parse_args()
    require(args.check != args.recover, "choose exactly one of --check/--recover")
    if args.check:
        print(json.dumps(check(), sort_keys=True))
        return 0
    require(args.probe is not None, "--recover requires --probe")
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        result = recover(args.probe, args.output)
        rc = 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
        result = {"status": "BLOCKED", "error": str(exc)}
        rc = 1
    (args.output / "status.json").write_bytes(encoded(result))
    print(json.dumps(result, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
