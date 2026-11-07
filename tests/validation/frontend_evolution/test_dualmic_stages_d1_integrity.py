#!/usr/bin/env python3
"""D1 catalog and three resealed-original negative contracts; no audio execution."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import tempfile
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "tests/validation/frontend_evolution/dualmic_stages_d1.py"


def check(original_a, original_c, receipt):
    started = time.monotonic()
    spec = importlib.util.spec_from_file_location("dualmic_d1_integrity_target", RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    originals = {"A": original_a.resolve(), "C": original_c.resolve()}
    report = {"schema_version": 1, "status": "FAIL", "formal_experiment": False,
              "scope": "read-only catalog and controlled original-member closure fixtures",
              "DSP_executions": 0, "model_executions": 0, "audio_metrics_computed": False,
              "source": runner.descriptor(RUNNER), "checker": runner.descriptor(Path(__file__)),
              "source_lock": runner.descriptor(runner.LOCK), "checks": []}
    try:
        cases = runner.catalog(originals["A"], originals["C"])
        report.update(case_count=len(cases), frames=sum(c["frames"] for c in cases),
                      capture_only_frames=sum(c["frames"] for c in cases if c["capture_only"]),
                      AEC_frames=sum(c["frames"] for c in cases if not c["capture_only"]))
        required = {"A": set(runner.A_METADATA), "C": set(runner.C_METADATA)}
        for case in cases:
            required[case["group"]].update(x for x in case["inputs"].values() if x)
            required[case["group"]].update(case["auxiliary_inputs"])
            required[case["group"]].update(case["original_dir"] + "/" + x for x in runner.ORIGINAL_CASE_FILES)
        archives = {group: root.parent / (group + ".zip") for group, root in originals.items()}
        with ZipFile(archives["C"]) as archive:
            required["C"].update(x for x in archive.namelist() if x.startswith("result/") and not x.endswith("/"))
        with tempfile.TemporaryDirectory(prefix="d1-source-closure-contract-") as directory:
            output = Path(directory)
            selected = {"A": {}, "C": {}}
            for group in ("A", "C"):
                runner.copy_exact(archives[group], output / "original-archives" / (group + ".zip"))
                for name in sorted(required[group]):
                    selected[group][name] = runner.copy_exact(originals[group] / name, output / "originals" / group / name)
            runner.copy_exact(runner.LOCK, output / "origins/source-lock.json")
            # Label this deliberately limited source-closure fixture. It is
            # neither an acquisition receipt nor a valid run/analysis bundle.
            runner.write_json(output / "origins/acquisition.json",
                              {"status": "PASS", "lock_sha256": runner.digest(runner.LOCK),
                               "controlled_contract_fixture": True})
            runner.write_json(output / "origins/selected-members.json", selected)
            checked = runner.verify_origins(output)
            report["checks"].append({"case": "locked_selected_members_positive", "status": "PASS", "counts": checked})

            def reseal_negative(label, expected_reason):
                runner.write_json(output / "origins/selected-members.json", selected)
                runner.write_json(output / "artifact-manifest.json",
                                  {"experiment": runner.EXPERIMENT, "files": runner.payload_inventory(output)})
                try:
                    runner.verify_origins(output)
                except ValueError as error:
                    runner.require(str(error).startswith(expected_reason), "negative rejected for unrelated reason: " + str(error))
                    report["checks"].append({"case": label, "status": "REJECTED_AS_REQUIRED", "reason": str(error)})
                else:
                    raise ValueError("negative accepted: " + label)

            target = "result/replay/pair-0-near-only-call/out.pcm"
            selected["A"].pop(target)
            reseal_negative("deleted_original_binding_then_resealed", "retained original member closure drift: A")
            (output / "originals/A" / target).unlink()
            reseal_negative("deleted_required_file_and_binding_then_resealed", "retained original member closure drift: A")
            raw = bytearray((originals["A"] / target).read_bytes())
            raw[0] ^= 1
            (output / "originals/A" / target).write_bytes(raw)
            selected["A"][target] = runner.descriptor(output / "originals/A" / target)
            reseal_negative("changed_original_byte_updated_hash_then_resealed", "retained original member drift: A/" + target)
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        runner.write_json(receipt, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-a", type=Path, required=True)
    parser.add_argument("--original-c", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("new receipt path required")
    result = check(args.original_a, args.original_c, args.output)
    print("D1 source-integrity contracts: " + result["status"] + "; DSP/model/audio-score executions: 0")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
