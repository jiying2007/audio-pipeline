#!/usr/bin/env python3
"""Fail-closed blind qualification helper for one frozen source-patch candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA64_RE = re.compile(r"^[0-9a-f]{64}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID16_RE = re.compile(r"^[0-9a-f]{16}$")
EXPECTED_STATUS = "FROZEN_RESEARCH_CANDIDATE"
EXPECTED_NEXT_GATE = "validation-grade-blind"
EXPECTED_AUTHORITY = {
    "shipping_authority": False,
    "source_merge_authority": False,
    "target_execution_authority": False,
    "hil_authority": False,
    "product_certification_authority": False,
    "automatic_main_mutation": False,
    "automatic_promotion": False,
}
VAD_SUMMARY_METRICS = (
    "min_vad_recall",
    "min_vad_f1",
    "max_vad_false_positive_rate",
)
CANDIDATE_QUALITY_MODES = {
    "full-absolute-pass",
    "vad-impact-scoped-v1",
}
VAD_IMPACT_POLICY_METRICS = {
    "pass_rate",
    "min_vad_f1",
}
VAD_IMPACT_DERIVED_SUMMARY_KEYS = {
    "pass_rate",
    "passed_cases",
    "scenario_pass_rate",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def research_candidate_id(hypothesis_id: str, source_base_sha: str,
                          patch_sha256: str) -> str:
    payload = json.dumps({
        "hypothesis_id": hypothesis_id,
        "source_base_sha": source_base_sha,
        "patch_sha256": patch_sha256,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def patch_paths(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for line in text.splitlines():
        if not line.startswith("diff --git a/"):
            continue
        match = re.fullmatch(r"diff --git a/(\S+) b/(\S+)", line)
        if match is None or match.group(1) != match.group(2):
            raise ValueError("source-patch path headers invalid")
        path = match.group(1)
        parts = Path(path).parts
        if Path(path).is_absolute() or ".." in parts:
            raise ValueError("source-patch path traversal")
        found.append(path)
    if not found or len(set(found)) != len(found):
        raise ValueError("source-patch must contain unique diff paths")
    if any(line.startswith(("new file mode ", "deleted file mode ", "GIT binary patch"))
           for line in text.splitlines()):
        raise ValueError("source-patch may only modify existing text files")
    return tuple(found)


def validate_manifest(manifest: dict[str, Any], registry: dict[str, Any],
                      repo_root: Path) -> dict[str, Any]:
    required = {
        "schema_version", "candidate_kind", "status", "next_gate",
        "candidate_id", "research_candidate_id", "hypothesis_id",
        "source_base_sha", "patch", "research_provenance",
        "selection_evidence", "blind_contract", "output_authority",
    }
    if set(manifest) != required or manifest["schema_version"] != 1:
        raise ValueError("source-patch candidate manifest schema invalid")
    if manifest["candidate_kind"] != "source-patch":
        raise ValueError("candidate_kind must be source-patch")
    if manifest["status"] != EXPECTED_STATUS or manifest["next_gate"] != EXPECTED_NEXT_GATE:
        raise ValueError("candidate is not frozen for validation-grade-blind")

    source_sha = str(manifest["source_base_sha"])
    if not SHA40_RE.fullmatch(source_sha):
        raise ValueError("source_base_sha must be lowercase SHA-40")
    candidate_id = str(manifest["candidate_id"])
    hypothesis_id = str(manifest["hypothesis_id"])
    research_id = str(manifest["research_candidate_id"])
    if not candidate_id or not hypothesis_id or not ID16_RE.fullmatch(research_id):
        raise ValueError("candidate identity invalid")

    patch = manifest["patch"]
    if set(patch) != {"path", "sha256", "allowed_paths"}:
        raise ValueError("patch fields invalid")
    patch_path = Path(str(patch["path"]))
    if (patch_path.is_absolute() or ".." in patch_path.parts or
            patch_path.suffix != ".patch" or
            not str(patch_path).startswith(
                ".github/research/continuous-optimization/code-candidates/")):
        raise ValueError("patch path invalid")
    patch_sha = str(patch["sha256"])
    if not SHA64_RE.fullmatch(patch_sha):
        raise ValueError("patch SHA256 invalid")
    allowed = patch["allowed_paths"]
    if not isinstance(allowed, list) or not allowed or len(allowed) != len(set(allowed)):
        raise ValueError("allowed patch paths invalid")
    file_path = repo_root / patch_path
    if not file_path.is_file() or sha256_file(file_path) != patch_sha:
        raise ValueError("patch file/hash mismatch")
    if set(patch_paths(file_path.read_text(encoding="utf-8"))) != set(allowed):
        raise ValueError("patch paths do not match manifest")

    expected_research_id = research_candidate_id(hypothesis_id, source_sha, patch_sha)
    if research_id != expected_research_id:
        raise ValueError("research_candidate_id mismatch")

    provenance = manifest["research_provenance"]
    provenance_keys = {
        "workflow", "run_id", "development_infra_sha", "artifact_id",
        "artifact_name", "artifact_digest", "result_path", "result_sha256",
    }
    if not isinstance(provenance, dict) or set(provenance) != provenance_keys:
        raise ValueError("research provenance invalid")
    if (
        not isinstance(provenance["workflow"], str)
        or not provenance["workflow"].strip()
        or len(provenance["workflow"]) > 160
    ):
        raise ValueError("development workflow identity invalid")
    if type(provenance["run_id"]) is not int or provenance["run_id"] <= 0:
        raise ValueError("development run id invalid")
    if type(provenance["artifact_id"]) is not int or provenance["artifact_id"] <= 0:
        raise ValueError("development artifact id invalid")
    if not SHA40_RE.fullmatch(str(provenance["development_infra_sha"])):
        raise ValueError("development infra SHA invalid")
    if (
        not isinstance(provenance["artifact_name"], str)
        or not provenance["artifact_name"]
        or len(provenance["artifact_name"]) > 200
        or str(provenance["run_id"]) not in provenance["artifact_name"]
    ):
        raise ValueError("artifact name/run mismatch")
    if not SHA256_RE.fullmatch(str(provenance["artifact_digest"])):
        raise ValueError("artifact digest invalid")
    if provenance["result_path"] != "result.json":
        raise ValueError("development result path invalid")
    if not SHA64_RE.fullmatch(str(provenance["result_sha256"])):
        raise ValueError("development result SHA invalid")

    selection = manifest["selection_evidence"]
    selection_keys = {
        "decision", "fresh_development_seeds",
        "shipping_mirror_active_mismatch_frames",
        "shipping_mirror_max_probability_delta",
        "candidate_probability_max_delta",
        "nonstationary_recall_delta", "nonstationary_fpr_delta",
        "nonstationary_noise_active_reduction_frames",
        "nonstationary_noise_active_segment_reduction",
        "stationary_recall_delta", "stationary_fpr_delta",
    }
    if set(selection) != selection_keys:
        raise ValueError("selection evidence fields invalid")
    if selection["decision"] != "FROZEN_RESEARCH_CANDIDATE_REVIEW_REQUIRED":
        raise ValueError("development did not freeze candidate")
    seeds = selection["fresh_development_seeds"]
    if (
        not isinstance(seeds, list)
        or len(seeds) < 3
        or len(seeds) != len(set(seeds))
        or any(type(seed) is not int or seed <= 0 for seed in seeds)
    ):
        raise ValueError("development seed binding invalid")
    for key in (
        "shipping_mirror_max_probability_delta",
        "candidate_probability_max_delta",
        "nonstationary_recall_delta", "nonstationary_fpr_delta",
        "stationary_recall_delta", "stationary_fpr_delta",
    ):
        if not math.isfinite(float(selection[key])):
            raise ValueError(f"non-finite selection evidence: {key}")
    if int(selection["shipping_mirror_active_mismatch_frames"]) != 0:
        raise ValueError("shipping mirror active mismatch")
    if float(selection["shipping_mirror_max_probability_delta"]) > 1e-6:
        raise ValueError("shipping mirror probability drift")
    if float(selection["candidate_probability_max_delta"]) > 1e-6:
        raise ValueError("candidate probability drift")
    if int(selection["nonstationary_noise_active_reduction_frames"]) < 1:
        raise ValueError("candidate did not reduce nonstationary noise-active frames")
    if int(selection["nonstationary_noise_active_segment_reduction"]) < 1:
        raise ValueError("candidate did not reduce nonstationary noise-active segments")
    if float(selection["nonstationary_recall_delta"]) < -0.03:
        raise ValueError("development recall gate no longer passes")
    if float(selection["nonstationary_fpr_delta"]) > 0.0:
        raise ValueError("development FPR gate no longer passes")
    if float(selection["stationary_recall_delta"]) < -0.03:
        raise ValueError("stationary recall gate no longer passes")
    if float(selection["stationary_fpr_delta"]) > 0.0:
        raise ValueError("stationary FPR gate no longer passes")

    blind = manifest["blind_contract"]
    required_blind_fields = {
        "visible_policy", "blind_policy", "holdout_percent",
        "require_baseline_absolute_pass", "require_candidate_absolute_pass",
        "require_visible_candidate_behavior_exercised",
        "max_vad_recall_regression", "max_vad_f1_regression",
        "max_vad_false_positive_rate_regression",
    }
    optional_blind_fields = {
        "baseline_reference_mode",
        "candidate_quality_mode",
    }
    if (
        not isinstance(blind, dict)
        or not required_blind_fields.issubset(blind)
        or set(blind) - required_blind_fields - optional_blind_fields
    ):
        raise ValueError("blind contract fields invalid")
    if blind["visible_policy"] != "validation/policies/validation-full-partition.json":
        raise ValueError("visible policy drift")
    if blind["blind_policy"] != "validation/policies/validation-full-blind.json":
        raise ValueError("blind policy drift")
    if int(blind["holdout_percent"]) not in (20, 30):
        raise ValueError("blind holdout percent invalid")
    baseline_reference_mode = blind.get(
        "baseline_reference_mode", "absolute-pass"
    )
    if baseline_reference_mode not in {"absolute-pass", "valid-report"}:
        raise ValueError("baseline_reference_mode invalid")
    expected_baseline_absolute_pass = baseline_reference_mode == "absolute-pass"
    if blind["require_baseline_absolute_pass"] is not expected_baseline_absolute_pass:
        raise ValueError(
            "require_baseline_absolute_pass inconsistent with baseline_reference_mode"
        )
    candidate_quality_mode = blind.get(
        "candidate_quality_mode", "full-absolute-pass"
    )
    if candidate_quality_mode not in CANDIDATE_QUALITY_MODES:
        raise ValueError("candidate_quality_mode invalid")
    expected_candidate_absolute_pass = (
        candidate_quality_mode == "full-absolute-pass"
    )
    if (
        blind["require_candidate_absolute_pass"]
        is not expected_candidate_absolute_pass
    ):
        raise ValueError(
            "require_candidate_absolute_pass inconsistent with candidate_quality_mode"
        )
    if candidate_quality_mode == "vad-impact-scoped-v1":
        if baseline_reference_mode != "valid-report":
            raise ValueError(
                "vad-impact-scoped-v1 requires valid-report baseline reference mode"
            )
        if allowed != ["src/enhance/ap_vad.c"]:
            raise ValueError(
                "vad-impact-scoped-v1 requires the single canonical VAD source path"
            )
    if blind["require_visible_candidate_behavior_exercised"] is not True:
        raise ValueError(
            "blind requirement weakened: require_visible_candidate_behavior_exercised"
        )
    for key in (
        "max_vad_recall_regression", "max_vad_f1_regression",
        "max_vad_false_positive_rate_regression",
    ):
        value = float(blind[key])
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"blind regression bound invalid: {key}")

    if manifest["output_authority"] != EXPECTED_AUTHORITY:
        raise ValueError("source-patch candidate gained forbidden authority")
    registry_terminal = {
        str(item["candidate_id"]) for item in registry.get("terminal_candidates", [])
    }
    if candidate_id in registry_terminal:
        raise ValueError("terminal candidate cannot enter blind qualification")
    shipping = registry.get("shipping_baseline", {})
    if shipping.get("frozen") is not True or shipping.get("source_sha") != source_sha:
        raise ValueError("source-patch candidate must bind frozen shipping baseline")
    if EXPECTED_NEXT_GATE not in set(registry.get("forbidden_optimizer_tiers", [])):
        raise ValueError("blind data is no longer excluded from optimizer feedback")

    return {
        "candidate_id": candidate_id,
        "research_candidate_id": research_id,
        "source_base_sha": source_sha,
        "patch_path": str(patch_path),
        "patch_sha256": patch_sha,
        "artifact_id": provenance["artifact_id"],
        "artifact_digest": provenance["artifact_digest"],
        "research_run_id": provenance["run_id"],
        "development_infra_sha": provenance["development_infra_sha"],
        "baseline_reference_mode": baseline_reference_mode,
        "candidate_quality_mode": candidate_quality_mode,
    }


def verify_development_result(manifest: dict[str, Any], result: dict[str, Any]) -> None:
    if result.get("schema_version") != 1:
        raise ValueError("development result schema invalid")
    if result.get("investigation_id") != manifest["hypothesis_id"]:
        raise ValueError("development hypothesis mismatch")
    if result.get("source_base_sha") != manifest["source_base_sha"]:
        raise ValueError("development source mismatch")
    if result.get("candidate_id") != manifest["candidate_id"]:
        raise ValueError("development candidate mismatch")
    if result.get("decision") != "FROZEN_RESEARCH_CANDIDATE_REVIEW_REQUIRED":
        raise ValueError("development result did not freeze candidate")
    if result.get("failed_gates") != []:
        raise ValueError("frozen candidate carries failed development gates")
    if (
        result.get("fresh_development_seeds")
        != manifest["selection_evidence"]["fresh_development_seeds"]
    ):
        raise ValueError("development seed provenance mismatch")
    if int(result.get("candidate_budget_consumed", -1)) != 1:
        raise ValueError("development candidate budget mismatch")
    if int(result.get("confirmation_budget_consumed", -1)) != 0:
        raise ValueError("development consumed confirmation authority")
    if result.get("shipping_mirror") != {
        "active_mismatch_frames": 0, "max_probability_delta": 0.0
    }:
        raise ValueError("development shipping mirror mismatch")
    if result.get("candidate_probability_identity") != {"max_probability_delta": 0.0}:
        raise ValueError("development candidate probability identity mismatch")


def seal_identity(manifest: dict[str, Any], baseline_processor: Path,
                  candidate_processor: Path, output: Path) -> dict[str, Any]:
    if not baseline_processor.is_file() or not candidate_processor.is_file():
        raise ValueError("qualification processor missing")
    result = {
        "schema_version": 1,
        "authority": "non-shipping-source-patch-blind-qualification",
        "status": EXPECTED_STATUS,
        "next_gate": EXPECTED_NEXT_GATE,
        "candidate_id": manifest["candidate_id"],
        "research_candidate_id": manifest["research_candidate_id"],
        "hypothesis_id": manifest["hypothesis_id"],
        "source_base_sha": manifest["source_base_sha"],
        "patch": manifest["patch"],
        "baseline_processor_sha256": sha256_file(baseline_processor),
        "candidate_processor_sha256": sha256_file(candidate_processor),
        "research_provenance": manifest["research_provenance"],
        "blind_contract": manifest["blind_contract"],
        "output_authority": EXPECTED_AUTHORITY,
        "rule": (
            "This identity may only compare the exact frozen source-patch candidate "
            "with its exact shipping baseline on one visible+blind public partition. "
            "It cannot rank, retune, mutate main, ship, run target/HIL, or certify product."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def _report_pair(baseline: dict[str, Any], candidate: dict[str, Any],
                 expected_tier: str) -> None:
    for report in (baseline, candidate):
        if report.get("schema_version") != 1 or report.get("tier") != expected_tier:
            raise ValueError("validation report identity/tier invalid")
        if report.get("validation_result") not in {"PASS", "FAIL"}:
            raise ValueError("validation report incomplete")
        if not isinstance(report.get("summary"), dict):
            raise ValueError("validation summary missing")
    if baseline.get("corpus_id") != candidate.get("corpus_id"):
        raise ValueError("baseline/candidate corpus mismatch")
    if baseline.get("policy_id") != candidate.get("policy_id"):
        raise ValueError("baseline/candidate policy mismatch")
    b = baseline.get("bindings", {})
    c = candidate.get("bindings", {})
    for key in (
        "authority_sha256", "dataset_lock_sha256", "corpus_sha256",
        "policy_sha256", "evaluation_semantics_sha256",
    ):
        if key in b or key in c:
            if b.get(key) != c.get(key):
                raise ValueError(f"baseline/candidate binding mismatch: {key}")


def _metric(summary: dict[str, Any], key: str) -> float:
    value = summary.get(key)
    if value is None or not math.isfinite(float(value)):
        raise ValueError(f"VAD summary metric missing/non-finite: {key}")
    return float(value)


def _visible_behavior_exercised(baseline: dict[str, Any],
                                candidate: dict[str, Any]) -> bool:
    base_cases = {
        case.get("case_id"): case for case in baseline.get("cases", [])
        if isinstance(case, dict)
    }
    cand_cases = {
        case.get("case_id"): case for case in candidate.get("cases", [])
        if isinstance(case, dict)
    }
    if set(base_cases) != set(cand_cases) or not base_cases:
        raise ValueError("visible case identity mismatch")
    for case_id in sorted(base_cases):
        bm = base_cases[case_id].get("metrics", {})
        cm = cand_cases[case_id].get("metrics", {})
        for key in ("vad_recall", "vad_f1", "vad_false_positive_rate"):
            bv, cv = bm.get(key), cm.get(key)
            if bv is None and cv is None:
                continue
            if bv is None or cv is None:
                raise ValueError(f"visible VAD metric applicability drift: {case_id}/{key}")
            if abs(float(bv) - float(cv)) > 1e-12:
                return True
    return False


def _relative_violations(manifest: dict[str, Any],
                         baseline: dict[str, Any],
                         candidate: dict[str, Any],
                         stage: str) -> list[dict[str, Any]]:
    contract = manifest["blind_contract"]
    bs = baseline["summary"]
    cs = candidate["summary"]
    pairs = (
        ("min_vad_recall", float(contract["max_vad_recall_regression"]), "min"),
        ("min_vad_f1", float(contract["max_vad_f1_regression"]), "min"),
        ("max_vad_false_positive_rate",
         float(contract["max_vad_false_positive_rate_regression"]), "max"),
    )
    violations: list[dict[str, Any]] = []
    for metric, allowed, direction in pairs:
        base = _metric(bs, metric)
        cand = _metric(cs, metric)
        if direction == "min":
            regression = base - cand
            failed = regression > allowed + 1e-12
        else:
            regression = cand - base
            failed = regression > allowed + 1e-12
        if failed:
            violations.append({
                "stage": stage, "metric": metric, "baseline": base,
                "candidate": cand, "regression": regression,
                "allowed_regression": allowed,
            })
    return violations


def _without_vad_impact_metrics(value: Any) -> Any:
    """Project a report fragment onto metrics a VAD-only source patch cannot own."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if (
                key in VAD_SUMMARY_METRICS
                or key in VAD_IMPACT_DERIVED_SUMMARY_KEYS
                or key.startswith("vad_")
            ):
                continue
            result[key] = _without_vad_impact_metrics(item)
        return result
    if isinstance(value, list):
        return [_without_vad_impact_metrics(item) for item in value]
    return value


def _non_vad_case_metrics(report: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for case in report.get("cases", []):
        if not isinstance(case, dict):
            raise ValueError("validation case must be an object")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in result:
            raise ValueError("validation case identity invalid")
        metrics = case.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError(f"validation case metrics missing: {case_id}")
        result[case_id] = _without_vad_impact_metrics(metrics)
    if not result:
        raise ValueError("validation cases missing")
    return result


def _normalized_violations(report: dict[str, Any],
                           impacted: bool) -> list[dict[str, Any]]:
    raw = report.get("violations", [])
    if not isinstance(raw, list):
        raise ValueError("validation violations must be a list")
    result = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("validation violation must be an object")
        metric = item.get("metric")
        if not isinstance(metric, str) or not metric:
            raise ValueError("validation violation metric missing")
        is_impacted = metric in VAD_IMPACT_POLICY_METRICS
        if is_impacted == impacted:
            result.append(item)
    return sorted(
        result,
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
    )


def _vad_impact_scoped_quality_violations(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    stage: str,
) -> list[dict[str, Any]]:
    """Require absolute VAD policy quality and byte-equivalent non-VAD behavior."""
    if (
        _without_vad_impact_metrics(baseline["summary"])
        != _without_vad_impact_metrics(candidate["summary"])
    ):
        raise ValueError(f"{stage} non-VAD summary drift under VAD impact scope")
    if _non_vad_case_metrics(baseline) != _non_vad_case_metrics(candidate):
        raise ValueError(f"{stage} non-VAD case-metric drift under VAD impact scope")

    baseline_unaffected = _normalized_violations(baseline, impacted=False)
    candidate_unaffected = _normalized_violations(candidate, impacted=False)
    if baseline_unaffected != candidate_unaffected:
        raise ValueError(f"{stage} non-VAD policy violation drift under VAD impact scope")

    violations = []
    for item in _normalized_violations(candidate, impacted=True):
        violations.append({
            "stage": stage,
            "metric": item["metric"],
            "gate": item.get("gate"),
            "actual": item.get("actual"),
            "expected_min": item.get("expected_min"),
            "expected_max": item.get("expected_max"),
            "kind": "impact-scoped-candidate-absolute-policy",
        })
    return violations


def classify(manifest: dict[str, Any], identity: dict[str, Any],
             baseline_visible: dict[str, Any] | None,
             candidate_visible: dict[str, Any] | None,
             baseline_blind: dict[str, Any] | None,
             candidate_blind: dict[str, Any] | None,
             output: Path) -> tuple[dict[str, Any], int]:
    if identity.get("authority") != "non-shipping-source-patch-blind-qualification":
        raise ValueError("invalid source-patch qualification identity")
    reports = (baseline_visible, candidate_visible, baseline_blind, candidate_blind)
    if any(report is None for report in reports):
        decision = "BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING"
        failed_stage = "evidence-incomplete"
        terminal = False
        next_gate = EXPECTED_NEXT_GATE
        violations: list[dict[str, Any]] = []
        rc = 2
    else:
        assert baseline_visible is not None and candidate_visible is not None
        assert baseline_blind is not None and candidate_blind is not None
        _report_pair(baseline_visible, candidate_visible, "validation-grade")
        _report_pair(baseline_blind, candidate_blind, "validation-grade-blind")
        baseline_results = {
            "visible": baseline_visible["validation_result"],
            "blind": baseline_blind["validation_result"],
        }
        candidate_results = {
            "visible": candidate_visible["validation_result"],
            "blind": candidate_blind["validation_result"],
        }
        baseline_reference_mode = manifest["blind_contract"].get(
            "baseline_reference_mode", "absolute-pass"
        )
        candidate_quality_mode = manifest["blind_contract"].get(
            "candidate_quality_mode", "full-absolute-pass"
        )
        if (
            baseline_reference_mode == "absolute-pass"
            and any(value != "PASS" for value in baseline_results.values())
        ):
            decision = "BLIND_BASELINE_INVALID_REVIEW_REQUIRED"
            failed_stage = "shipping-baseline"
            terminal = False
            next_gate = EXPECTED_NEXT_GATE
            violations = []
            rc = 2
        elif (
            candidate_quality_mode == "full-absolute-pass"
            and any(value != "PASS" for value in candidate_results.values())
        ):
            decision = "BLIND_REJECTED_NON_SHIPPING"
            failed_stage = (
                "visible-validation" if candidate_results["visible"] != "PASS"
                else "blind-holdout"
            )
            terminal = True
            next_gate = None
            violations = []
            rc = 1
        elif candidate_quality_mode == "vad-impact-scoped-v1":
            violations = (
                _vad_impact_scoped_quality_violations(
                    baseline_visible, candidate_visible, "visible"
                )
                + _vad_impact_scoped_quality_violations(
                    baseline_blind, candidate_blind, "blind"
                )
            )
            if violations:
                decision = "BLIND_REJECTED_NON_SHIPPING"
                failed_stage = "impact-scoped-candidate-quality"
                terminal = True
                next_gate = None
                rc = 1
            elif (manifest["blind_contract"]["require_visible_candidate_behavior_exercised"]
                  and not _visible_behavior_exercised(
                      baseline_visible, candidate_visible)):
                decision = "BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING"
                failed_stage = "visible-candidate-behavior-not-exercised"
                terminal = False
                next_gate = EXPECTED_NEXT_GATE
                rc = 2
            else:
                violations = (
                    _relative_violations(
                        manifest, baseline_visible, candidate_visible, "visible")
                    + _relative_violations(
                        manifest, baseline_blind, candidate_blind, "blind")
                )
                if violations:
                    decision = "BLIND_REJECTED_NON_SHIPPING"
                    failed_stage = "paired-relative-vad-gates"
                    terminal = True
                    next_gate = None
                    rc = 1
                else:
                    decision = "BLIND_QUALIFIED_NON_SHIPPING"
                    failed_stage = None
                    terminal = False
                    next_gate = "source-change-review"
                    rc = 0
        elif (manifest["blind_contract"]["require_visible_candidate_behavior_exercised"]
              and not _visible_behavior_exercised(
                  baseline_visible, candidate_visible)):
            decision = "BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING"
            failed_stage = "visible-candidate-behavior-not-exercised"
            terminal = False
            next_gate = EXPECTED_NEXT_GATE
            violations = []
            rc = 2
        else:
            violations = (
                _relative_violations(
                    manifest, baseline_visible, candidate_visible, "visible")
                + _relative_violations(
                    manifest, baseline_blind, candidate_blind, "blind")
            )
            if violations:
                decision = "BLIND_REJECTED_NON_SHIPPING"
                failed_stage = "paired-relative-vad-gates"
                terminal = True
                next_gate = None
                rc = 1
            else:
                decision = "BLIND_QUALIFIED_NON_SHIPPING"
                failed_stage = None
                terminal = False
                next_gate = "source-change-review"
                rc = 0

    result = {
        "schema_version": 1,
        "authority": "non-shipping-source-patch-blind-qualification",
        "decision": decision,
        "candidate_id": manifest["candidate_id"],
        "research_candidate_id": manifest["research_candidate_id"],
        "source_base_sha": manifest["source_base_sha"],
        "patch_sha256": manifest["patch"]["sha256"],
        "terminal_candidate": terminal,
        "failed_stage": failed_stage,
        "baseline_reference_mode": manifest["blind_contract"].get(
            "baseline_reference_mode", "absolute-pass"
        ),
        "candidate_quality_mode": manifest["blind_contract"].get(
            "candidate_quality_mode", "full-absolute-pass"
        ),
        "baseline_results": (
            None if baseline_visible is None or baseline_blind is None else {
                "visible": baseline_visible.get("validation_result"),
                "blind": baseline_blind.get("validation_result"),
            }
        ),
        "candidate_results": (
            None if candidate_visible is None or candidate_blind is None else {
                "visible": candidate_visible.get("validation_result"),
                "blind": candidate_blind.get("validation_result"),
            }
        ),
        "relative_vad_violations": violations,
        "next_gate": next_gate,
        "shipping_authority": False,
        "source_merge_authority": False,
        "target_execution_authority": False,
        "hil_authority": False,
        "product_certification_authority": False,
        "automatic_main_mutation": False,
        "automatic_promotion": False,
        "rule": (
            "Legacy full-absolute-pass mode requires candidate visible+blind absolute "
            "PASS. Future vad-impact-scoped-v1 mode may retain an overall FAIL only "
            "when every non-VAD summary/case metric and non-VAD policy violation is "
            "identical to baseline, while candidate VAD-impact absolute policy gates "
            "and preregistered paired VAD regression bounds pass. Legacy absolute-pass "
            "baseline mode also requires baseline visible+blind PASS; valid-report "
            "mode accepts a complete identity-bound baseline PASS|FAIL report. "
            "No outcome changes shipping automatically."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result, rc


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-code-blind-") as tmp:
        root = Path(tmp)
        patch = root / ".github/research/continuous-optimization/code-candidates/f.patch"
        patch.parent.mkdir(parents=True)
        patch.write_text(
            "diff --git a/src/x.c b/src/x.c\n"
            "--- a/src/x.c\n+++ b/src/x.c\n"
            "@@ -1 +1 @@\n-a\n+b\n",
            encoding="utf-8",
        )
        patch_sha = sha256_file(patch)
        source = "a" * 40
        hypothesis = "fixture"
        research_id = research_candidate_id(hypothesis, source, patch_sha)
        manifest = {
            "schema_version": 1, "candidate_kind": "source-patch",
            "status": EXPECTED_STATUS, "next_gate": EXPECTED_NEXT_GATE,
            "candidate_id": "fixture-candidate", "research_candidate_id": research_id,
            "hypothesis_id": hypothesis, "source_base_sha": source,
            "patch": {
                "path": str(patch.relative_to(root)), "sha256": patch_sha,
                "allowed_paths": ["src/x.c"],
            },
            "research_provenance": {
                "workflow": "Research I020 VAD Weak Start Requires Blend v1",
                "run_id": 1, "development_infra_sha": "b" * 40,
                "artifact_id": 2,
                "artifact_name": "i020-vad-weak-start-requires-blend-1",
                "artifact_digest": "sha256:" + "c" * 64,
                "result_path": "result.json", "result_sha256": "d" * 64,
            },
            "selection_evidence": {
                "decision": "FROZEN_RESEARCH_CANDIDATE_REVIEW_REQUIRED",
                "fresh_development_seeds": [461123, 471123, 481123],
                "shipping_mirror_active_mismatch_frames": 0,
                "shipping_mirror_max_probability_delta": 0.0,
                "candidate_probability_max_delta": 0.0,
                "nonstationary_recall_delta": -0.01,
                "nonstationary_fpr_delta": -0.05,
                "nonstationary_noise_active_reduction_frames": 5,
                "nonstationary_noise_active_segment_reduction": 1,
                "stationary_recall_delta": 0.0, "stationary_fpr_delta": 0.0,
            },
            "blind_contract": {
                "visible_policy": "validation/policies/validation-full-partition.json",
                "blind_policy": "validation/policies/validation-full-blind.json",
                "holdout_percent": 20,
                "require_baseline_absolute_pass": True,
                "require_candidate_absolute_pass": True,
                "require_visible_candidate_behavior_exercised": True,
                "max_vad_recall_regression": 0.03,
                "max_vad_f1_regression": 0.03,
                "max_vad_false_positive_rate_regression": 0.0,
            },
            "output_authority": dict(EXPECTED_AUTHORITY),
        }
        registry = {
            "shipping_baseline": {"frozen": True, "source_sha": source},
            "forbidden_optimizer_tiers": ["validation-grade-blind"],
            "terminal_candidates": [],
        }
        validate_manifest(manifest, registry, root)
        baseline_processor = root / "baseline"
        candidate_processor = root / "candidate"
        baseline_processor.write_bytes(b"baseline")
        candidate_processor.write_bytes(b"candidate")
        identity = seal_identity(
            manifest, baseline_processor, candidate_processor, root / "identity.json")

        def report(tier: str, result: str, recall: float, f1: float,
                   fpr: float, processor: str, delta_case: bool = False) -> dict[str, Any]:
            metrics = {
                "vad_recall": recall, "vad_f1": f1,
                "vad_false_positive_rate": fpr,
            }
            return {
                "schema_version": 1, "validation_result": result, "tier": tier,
                "corpus_id": "same", "policy_id": "p",
                "source_revision": source,
                "bindings": {
                    "authority_sha256": "1", "dataset_lock_sha256": "2",
                    "corpus_sha256": "3", "policy_sha256": "4",
                    "processor_sha256": processor,
                },
                "summary": {
                    "min_vad_recall": recall, "min_vad_f1": f1,
                    "max_vad_false_positive_rate": fpr,
                },
                "cases": [{
                    "case_id": "c1", "metrics": {
                        **metrics,
                        **({"vad_recall": recall - 0.01} if delta_case else {}),
                    }
                }],
            }

        bv = report("validation-grade", "PASS", 0.90, 0.88, 0.10, "b")
        cv = report("validation-grade", "PASS", 0.89, 0.88, 0.08, "c", True)
        bb = report("validation-grade-blind", "PASS", 0.88, 0.86, 0.12, "b")
        cb = report("validation-grade-blind", "PASS", 0.87, 0.85, 0.11, "c")
        qualified, rc = classify(
            manifest, identity, bv, cv, bb, cb, root / "qualified.json")
        assert rc == 0 and qualified["decision"] == "BLIND_QUALIFIED_NON_SHIPPING"

        bad = json.loads(json.dumps(cb))
        bad["summary"]["min_vad_recall"] = 0.80
        rejected, rc = classify(
            manifest, identity, bv, cv, bb, bad, root / "rejected.json")
        assert rc == 1 and rejected["decision"] == "BLIND_REJECTED_NON_SHIPPING"

        baseline_fail = json.loads(json.dumps(bb))
        baseline_fail["validation_result"] = "FAIL"
        review, rc = classify(
            manifest, identity, bv, cv, baseline_fail, cb, root / "baseline.json")
        assert rc == 2 and review["decision"] == "BLIND_BASELINE_INVALID_REVIEW_REQUIRED"
        assert review["baseline_reference_mode"] == "absolute-pass"

        future_manifest = json.loads(json.dumps(manifest))
        future_manifest["blind_contract"]["baseline_reference_mode"] = "valid-report"
        future_manifest["blind_contract"]["require_baseline_absolute_pass"] = False
        summary = validate_manifest(future_manifest, registry, root)
        assert summary["baseline_reference_mode"] == "valid-report"
        future_identity = seal_identity(
            future_manifest, baseline_processor, candidate_processor,
            root / "future-identity.json")
        visible_baseline_fail = json.loads(json.dumps(bv))
        visible_baseline_fail["validation_result"] = "FAIL"
        blind_baseline_fail = json.loads(json.dumps(bb))
        blind_baseline_fail["validation_result"] = "FAIL"
        future_qualified, rc = classify(
            future_manifest, future_identity,
            visible_baseline_fail, cv, blind_baseline_fail, cb,
            root / "future-qualified.json")
        assert rc == 0
        assert future_qualified["decision"] == "BLIND_QUALIFIED_NON_SHIPPING"
        assert future_qualified["baseline_reference_mode"] == "valid-report"
        assert future_qualified["baseline_results"] == {
            "visible": "FAIL", "blind": "FAIL"
        }

        future_bad_candidate = json.loads(json.dumps(cb))
        future_bad_candidate["validation_result"] = "FAIL"
        future_rejected, rc = classify(
            future_manifest, future_identity,
            visible_baseline_fail, cv, blind_baseline_fail,
            future_bad_candidate, root / "future-rejected.json")
        assert rc == 1
        assert future_rejected["decision"] == "BLIND_REJECTED_NON_SHIPPING"


        impact_manifest = json.loads(json.dumps(future_manifest))
        impact_manifest["research_provenance"]["workflow"] = (
            "Research Future VAD State Candidate Fixture"
        )
        impact_manifest["research_provenance"]["artifact_name"] = (
            "future-vad-state-candidate-1"
        )
        impact_manifest["selection_evidence"]["fresh_development_seeds"] = [
            501123, 511123, 521123
        ]
        impact_manifest["blind_contract"]["candidate_quality_mode"] = (
            "vad-impact-scoped-v1"
        )
        impact_manifest["blind_contract"]["require_candidate_absolute_pass"] = False
        impact_summary = validate_manifest(impact_manifest, registry, root)
        assert impact_summary["candidate_quality_mode"] == "vad-impact-scoped-v1"
        impact_identity = seal_identity(
            impact_manifest, baseline_processor, candidate_processor,
            root / "impact-identity.json")

        def unrelated_fail(report_value: dict[str, Any]) -> dict[str, Any]:
            value = json.loads(json.dumps(report_value))
            value["validation_result"] = "FAIL"
            value["summary"]["median_output_render_corr_reduction"] = 0.01
            value["violations"] = [{
                "gate": "min_median_output_render_corr_reduction",
                "metric": "median_output_render_corr_reduction",
                "actual": 0.01,
                "expected_min": 0.05,
            }]
            return value

        impact_bv = unrelated_fail(bv)
        impact_cv = unrelated_fail(cv)
        impact_bb = unrelated_fail(bb)
        impact_cb = unrelated_fail(cb)
        impact_qualified, rc = classify(
            impact_manifest, impact_identity,
            impact_bv, impact_cv, impact_bb, impact_cb,
            root / "impact-qualified.json")
        assert rc == 0
        assert impact_qualified["decision"] == "BLIND_QUALIFIED_NON_SHIPPING"
        assert impact_qualified["candidate_results"] == {
            "visible": "FAIL", "blind": "FAIL"
        }

        impact_bad = unrelated_fail(cb)
        impact_bad["summary"]["min_vad_f1"] = 0.70
        impact_bad["violations"].append({
            "gate": "min_vad_f1",
            "metric": "min_vad_f1",
            "actual": 0.70,
            "expected_min": 0.80,
        })
        impact_rejected, rc = classify(
            impact_manifest, impact_identity,
            impact_bv, impact_cv, impact_bb, impact_bad,
            root / "impact-rejected.json")
        assert rc == 1
        assert impact_rejected["failed_stage"] == "impact-scoped-candidate-quality"

        impact_drift = unrelated_fail(cb)
        impact_drift["summary"]["median_output_render_corr_reduction"] = 0.02
        try:
            classify(
                impact_manifest, impact_identity,
                impact_bv, impact_cv, impact_bb, impact_drift,
                root / "impact-drift.json")
        except ValueError as exc:
            assert "non-VAD summary drift" in str(exc)
        else:
            raise AssertionError("non-VAD drift was accepted by impact scope")
    print("source-patch blind helper self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--development-result", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--seal-identity", action="store_true")
    parser.add_argument("--baseline-processor", type=Path)
    parser.add_argument("--candidate-processor", type=Path)
    parser.add_argument("--identity-output", type=Path)
    parser.add_argument("--classify", action="store_true")
    parser.add_argument("--identity", type=Path)
    parser.add_argument("--baseline-visible", type=Path)
    parser.add_argument("--candidate-visible", type=Path)
    parser.add_argument("--baseline-blind", type=Path)
    parser.add_argument("--candidate-blind", type=Path)
    parser.add_argument("--qualification-output", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.manifest is None or args.registry is None:
        parser.error("--manifest and --registry are required")
    manifest = load_json(args.manifest)
    registry = load_json(args.registry)
    summary = validate_manifest(manifest, registry, args.repo_root.resolve())

    if args.check:
        if args.development_result is not None:
            verify_development_result(manifest, load_json(args.development_result))
        print(json.dumps({"result": "PASS", **summary}, sort_keys=True))

    if args.seal_identity:
        if (args.baseline_processor is None or args.candidate_processor is None
                or args.identity_output is None):
            parser.error("--seal-identity requires both processors and identity output")
        result = seal_identity(
            manifest, args.baseline_processor, args.candidate_processor,
            args.identity_output)
        print(json.dumps(result, sort_keys=True))

    if args.classify:
        if args.identity is None or args.qualification_output is None:
            parser.error("--classify requires --identity and --qualification-output")
        reports = []
        for path in (
            args.baseline_visible, args.candidate_visible,
            args.baseline_blind, args.candidate_blind,
        ):
            reports.append(load_json(path) if path and path.is_file() else None)
        result, rc = classify(
            manifest, load_json(args.identity),
            reports[0], reports[1], reports[2], reports[3],
            args.qualification_output)
        print(json.dumps(result, sort_keys=True))
        return rc

    if not args.check and not args.seal_identity and not args.classify:
        parser.error("choose --check, --seal-identity and/or --classify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
