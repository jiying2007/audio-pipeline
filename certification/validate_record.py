#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

PRODUCT_PERF_REQUIRED = {
    "active_cpu_percent", "p95_us", "p99_us", "deadline_misses", "rss_kib",
    "xruns", "overruns", "input_full_events", "output_drop_events",
}
PRODUCT_ACOUSTIC_REQUIRED = {
    "corpus_revision", "cases_total", "cases_passed", "far_end_erle_db",
    "aec_convergence_ms", "double_talk_near_si_sdr_db",
    "noise_si_sdr_improvement_db", "vad_f1", "threshold_report",
}
POLICY_REQUIRED = {
    "policy_id", "max_active_cpu_percent", "max_rss_kib", "max_p95_us",
    "max_p99_us", "max_soc_c", "max_average_power_w", "min_far_end_erle_db",
    "max_aec_convergence_ms", "min_double_talk_near_si_sdr_db",
    "min_noise_si_sdr_improvement_db", "min_vad_f1", "min_soak_hours",
}
POLICY_V4_REQUIRED = POLICY_REQUIRED | {"sku", "shipping_approved"}
V3_BUILD_REQUIRED = {
    "source_revision", "config_digest", "compiler_id", "compiler_version",
    "target_triple", "build_type", "binary_sha256",
}
V3_SOAK_REQUIRED = {
    "xruns", "deadline_misses", "overruns", "input_full_events",
    "output_drop_events", "failed_frames", "p95_us", "p99_us",
}
V4_DEPLOYMENT_REQUIRED = {
    "source_revision", "builder_runner", "dut_runner", "binary_sha256",
    "toolchain", "result",
}
V4_TOOLCHAIN_REQUIRED = {
    "compiler_path", "compiler_sha256", "compiler_version",
    "sysroot_path", "sysroot_sha256", "toolchain_root_path",
    "toolchain_root_sha256", "cflags", "cmake_args", "cmake_args_sha256",
}
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def require_keys(obj: dict, keys: set[str], where: str, errors: list[str]) -> None:
    missing = sorted(k for k in keys if k not in obj)
    if missing:
        errors.append(f"{where}: missing {', '.join(missing)}")


def validate_manifest(manifest: dict, errors: list[str]) -> None:
    require_keys(
        manifest,
        {"schema_version", "collector_version", "generated_at", "artifacts"},
        "evidence_manifest",
        errors,
    )
    if errors:
        return
    if manifest["schema_version"] != 1:
        errors.append("evidence_manifest.schema_version: expected 1")
    if not isinstance(manifest.get("artifacts"), list) or not manifest["artifacts"]:
        errors.append("evidence_manifest.artifacts: must be a non-empty array")
        return
    for i, item in enumerate(manifest["artifacts"]):
        if not isinstance(item, dict):
            errors.append(f"evidence_manifest.artifacts[{i}]: must be an object")
            continue
        require_keys(
            item,
            {"path", "type", "size", "sha256"},
            f"evidence_manifest.artifacts[{i}]",
            errors,
        )
        if not HEX64.fullmatch(str(item.get("sha256", ""))):
            errors.append(f"evidence_manifest.artifacts[{i}].sha256: invalid")


def validate_materialized_manifest(manifest: dict, root: Path, errors: list[str]) -> None:
    seen: set[str] = set()
    for i, item in enumerate(manifest.get("artifacts", [])):
        if not isinstance(item, dict) or "path" not in item:
            continue
        raw = str(item["path"])
        relative = Path(raw)
        if relative.is_absolute() or ".." in relative.parts or raw in seen:
            errors.append(f"evidence_manifest.artifacts[{i}].path: unsafe or duplicate")
            continue
        seen.add(raw)
        path = root / relative
        if not path.is_file():
            errors.append(f"evidence_manifest.artifacts[{i}].path: missing {raw}")
            continue
        if int(item.get("size", -1)) != path.stat().st_size:
            errors.append(f"evidence_manifest.artifacts[{i}].size: does not match file")
        expected = str(item.get("sha256", "")).lower()
        if HEX64.fullmatch(expected) and sha256(path) != expected:
            errors.append(f"evidence_manifest.artifacts[{i}].sha256: does not match file")


def validate_v3_build(record: dict, evidence: dict, errors: list[str]) -> None:
    build = record["build"]
    require_keys(build, V3_BUILD_REQUIRED, "build(v3+)", errors)
    if errors:
        return
    source_revision = str(build["source_revision"])
    if not HEX40.fullmatch(source_revision):
        errors.append("build.source_revision: v3+ requires exact 40-hex Git revision")
    if str(build.get("commit")) != source_revision:
        errors.append("build.commit: must equal build.source_revision in v3+")
    if not HEX64.fullmatch(str(build["config_digest"])):
        errors.append("build.config_digest: v3+ requires SHA-256")
    if not HEX64.fullmatch(str(build.get("fingerprint", ""))):
        errors.append("build.fingerprint: v3+ requires SHA-256")
    for key in ("compiler_id", "compiler_version", "target_triple", "build_type"):
        if not str(build.get(key, "")).strip():
            errors.append(f"build.{key}: v3+ requires non-empty value")
    binaries = build.get("binary_sha256")
    if not isinstance(binaries, dict) or not binaries:
        errors.append("build.binary_sha256: v3+ requires at least one binary")
        return
    for name, value in binaries.items():
        if not name or not HEX64.fullmatch(str(value)):
            errors.append(f"build.binary_sha256[{name!r}]: invalid SHA-256")
    manifest_binaries = {
        str(item.get("type", ""))[7:]: str(item.get("sha256", "")).lower()
        for item in evidence.get("artifacts", [])
        if str(item.get("type", "")).startswith("binary:")
    }
    if {k: str(v).lower() for k, v in binaries.items()} != manifest_binaries:
        errors.append("build.binary_sha256: does not match binary evidence artifacts")


def validate_v4_deployment(record: dict, evidence: dict, errors: list[str]) -> None:
    deployment = record.get("deployment")
    if not isinstance(deployment, dict):
        errors.append("deployment(v4): required object")
        return
    require_keys(deployment, V4_DEPLOYMENT_REQUIRED, "deployment(v4)", errors)
    if errors:
        return
    if deployment.get("result") != "PASS":
        errors.append("deployment.result: v4 requires PASS")
    if deployment.get("source_revision") != record["build"].get("source_revision"):
        errors.append("deployment.source_revision: must equal build.source_revision")
    if deployment.get("builder_runner") == deployment.get("dut_runner"):
        errors.append("deployment: builder and DUT runners must be different")
    if deployment.get("binary_sha256") != record["build"].get("binary_sha256"):
        errors.append("deployment.binary_sha256: must equal certified build binaries")
    toolchain = deployment.get("toolchain")
    if not isinstance(toolchain, dict):
        errors.append("deployment.toolchain: required object")
    else:
        require_keys(toolchain, V4_TOOLCHAIN_REQUIRED, "deployment.toolchain", errors)
        for key in ("compiler_sha256", "sysroot_sha256", "toolchain_root_sha256", "cmake_args_sha256"):
            if not HEX64.fullmatch(str(toolchain.get(key, ""))):
                errors.append(f"deployment.toolchain.{key}: invalid SHA-256")
        cmake_args = toolchain.get("cmake_args")
        if not isinstance(cmake_args, list) or not cmake_args or not all(isinstance(item, str) and item for item in cmake_args):
            errors.append("deployment.toolchain.cmake_args: must be a non-empty string array")
        else:
            payload = json.dumps(cmake_args, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            expected = hashlib.sha256(payload).hexdigest()
            if toolchain.get("cmake_args_sha256") != expected:
                errors.append("deployment.toolchain.cmake_args_sha256: does not match exact CMake arguments")
    if not any(item.get("type") == "deployment-provenance" for item in evidence.get("artifacts", [])):
        errors.append("evidence_manifest: v4 requires deployment-provenance artifact")


def validate(
    record: dict,
    policy: dict | None = None,
    policy_hash: str | None = None,
    evidence: dict | None = None,
    evidence_hash: str | None = None,
    corpus_hash: str | None = None,
    evidence_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    require_keys(
        record,
        {"sku", "status", "build", "platform", "audio_route", "performance",
         "acoustic", "soak", "artifacts"},
        "record",
        errors,
    )
    if errors:
        return errors
    status = record["status"]
    if status not in {"pending", "board-validated", "product-certified", "failed"}:
        errors.append(f"status: unsupported value {status!r}")
    require_keys(
        record["build"],
        {"commit", "version", "fingerprint", "compiler", "abi"},
        "build",
        errors,
    )
    require_keys(record["platform"], {"soc", "kernel", "governor", "cpuset"}, "platform", errors)
    require_keys(
        record["audio_route"],
        {"capture_device", "playback_device", "sample_rate_hz", "mic_channels"},
        "audio_route",
        errors,
    )
    require_keys(record["soak"], {"hours", "passed"}, "soak", errors)
    if record["audio_route"].get("sample_rate_hz") not in {8000, 16000, 24000, 32000, 48000}:
        errors.append("audio_route.sample_rate_hz: unsupported rate")
    if record["audio_route"].get("mic_channels") not in {1, 2}:
        errors.append("audio_route.mic_channels: must be 1 or 2")
    if status != "product-certified":
        return errors

    require_keys(
        record,
        {"schema_version", "policy", "policy_sha256", "corpus_manifest_sha256",
         "evidence_manifest_sha256", "collector_version", "toolchain_digest",
         "thermal_power"},
        "record",
        errors,
    )
    schema_version = record.get("schema_version")
    if schema_version not in {2, 3, 4}:
        errors.append("schema_version: product-certified records require v2, v3 or v4")
    for key in ("policy_sha256", "corpus_manifest_sha256", "evidence_manifest_sha256", "toolchain_digest"):
        if not HEX64.fullmatch(str(record.get(key, ""))):
            errors.append(f"{key}: must be 64 hexadecimal characters")
    if policy is None:
        errors.append("policy: product-certified requires --policy")
        return errors
    require_keys(policy, POLICY_V4_REQUIRED if schema_version == 4 else POLICY_REQUIRED, "policy", errors)
    if schema_version == 4:
        if policy.get("shipping_approved") is not True:
            errors.append("policy.shipping_approved: v4 product certification requires true")
        if str(policy.get("sku")) != str(record.get("sku")):
            errors.append("policy.sku: must match certification record SKU")
        if "not-for-shipping" in str(policy.get("policy_id", "")) or str(policy.get("policy_id", "")).startswith("example-"):
            errors.append("policy.policy_id: example/not-for-shipping policy cannot certify v4")
    if policy_hash and record.get("policy_sha256") != policy_hash:
        errors.append("policy_sha256: does not match supplied policy bytes")
    if corpus_hash and record.get("corpus_manifest_sha256") != corpus_hash:
        errors.append("corpus_manifest_sha256: does not match supplied corpus manifest")
    if evidence is None:
        errors.append("evidence_manifest: product-certified requires --evidence-manifest")
    else:
        validate_manifest(evidence, errors)
        if evidence_hash and record.get("evidence_manifest_sha256") != evidence_hash:
            errors.append("evidence_manifest_sha256: does not match supplied manifest")
        if schema_version in {3, 4}:
            if evidence_root is None:
                errors.append("evidence_manifest: v3+ requires materialized evidence root")
            else:
                validate_materialized_manifest(evidence, evidence_root, errors)
            validate_v3_build(record, evidence, errors)
        if schema_version == 4:
            validate_v4_deployment(record, evidence, errors)
    if errors:
        return errors
    if record.get("policy") != policy.get("policy_id"):
        errors.append("policy: record policy id must match supplied policy")

    perf = record["performance"]
    acoustic = record["acoustic"]
    soak = record["soak"]
    artifacts = record["artifacts"]
    thermal = record["thermal_power"]
    require_keys(perf, PRODUCT_PERF_REQUIRED, "performance", errors)
    require_keys(acoustic, PRODUCT_ACOUSTIC_REQUIRED, "acoustic", errors)
    require_keys(thermal, {"ambient_c", "max_soc_c", "average_power_w"}, "thermal_power", errors)
    require_keys(soak, {"hours", "passed", "xruns", "deadline_misses", "output_drop_events"}, "soak", errors)
    require_keys(artifacts, {"result_json", "benchmark_json", "evidence_manifest", "sha256"}, "artifacts", errors)
    if schema_version in {3, 4}:
        require_keys(soak, V3_SOAK_REQUIRED, "soak(v3+)", errors)
        require_keys(artifacts, {"binary_sha256"}, "artifacts(v3+)", errors)
    if schema_version == 4:
        require_keys(artifacts, {"deployment_provenance"}, "artifacts(v4)", errors)
    if errors:
        return errors

    for key in {"deadline_misses", "xruns", "overruns", "input_full_events", "output_drop_events"}:
        if int(perf[key]) != 0:
            errors.append(f"performance.{key}: nominal gate requires 0")
    for key in {"xruns", "deadline_misses", "output_drop_events"}:
        if int(soak[key]) != 0:
            errors.append(f"soak.{key}: nominal gate requires 0")
    if schema_version in {3, 4}:
        for key in {"overruns", "input_full_events", "failed_frames"}:
            if int(soak[key]) != 0:
                errors.append(f"soak.{key}: v3+ nominal gate requires 0")

    checks = [
        (float(perf["active_cpu_percent"]) <= float(policy["max_active_cpu_percent"]), "performance.active_cpu_percent"),
        (int(perf["rss_kib"]) <= int(policy["max_rss_kib"]), "performance.rss_kib"),
        (float(perf["p95_us"]) <= float(policy["max_p95_us"]), "performance.p95_us"),
        (float(perf["p99_us"]) <= float(policy["max_p99_us"]), "performance.p99_us"),
        (float(thermal["max_soc_c"]) <= float(policy["max_soc_c"]), "thermal_power.max_soc_c"),
        (float(thermal["average_power_w"]) <= float(policy["max_average_power_w"]), "thermal_power.average_power_w"),
        (float(acoustic["far_end_erle_db"]) >= float(policy["min_far_end_erle_db"]), "acoustic.far_end_erle_db"),
        (float(acoustic["aec_convergence_ms"]) <= float(policy["max_aec_convergence_ms"]), "acoustic.aec_convergence_ms"),
        (float(acoustic["double_talk_near_si_sdr_db"]) >= float(policy["min_double_talk_near_si_sdr_db"]), "acoustic.double_talk_near_si_sdr_db"),
        (float(acoustic["noise_si_sdr_improvement_db"]) >= float(policy["min_noise_si_sdr_improvement_db"]), "acoustic.noise_si_sdr_improvement_db"),
        (float(acoustic["vad_f1"]) >= float(policy["min_vad_f1"]), "acoustic.vad_f1"),
        (float(soak["hours"]) >= float(policy["min_soak_hours"]), "soak.hours"),
    ]
    for passed, name in checks:
        if not passed:
            errors.append(f"{name}: violates certification policy")
    if soak.get("passed") is not True:
        errors.append("soak.passed: product-certified requires true")
    if int(acoustic["cases_passed"]) != int(acoustic["cases_total"]):
        errors.append("acoustic: every certification corpus case must pass")
    return errors


def fixture(policy_hash: str, corpus_hash: str, evidence_hash: str) -> dict:
    return {
        "schema_version": 2,
        "sku": "test",
        "status": "product-certified",
        "policy": "test-policy",
        "policy_sha256": policy_hash,
        "corpus_manifest_sha256": corpus_hash,
        "evidence_manifest_sha256": evidence_hash,
        "collector_version": "1",
        "toolchain_digest": "5" * 64,
        "build": {
            "commit": "abcdef0", "version": "1.2.0", "fingerprint": "x",
            "compiler": "gcc", "abi": "armv7",
        },
        "platform": {"soc": "test", "kernel": "6.6", "governor": "performance", "cpuset": "1"},
        "audio_route": {
            "capture_device": "hw:0,0", "playback_device": "hw:0,0",
            "sample_rate_hz": 16000, "mic_channels": 2,
        },
        "performance": {
            "active_cpu_percent": 20, "p95_us": 3000, "p99_us": 5000,
            "deadline_misses": 0, "rss_kib": 512, "xruns": 0, "overruns": 0,
            "input_full_events": 0, "output_drop_events": 0,
        },
        "acoustic": {
            "corpus_revision": "r1", "cases_total": 10, "cases_passed": 10,
            "far_end_erle_db": 20, "aec_convergence_ms": 500,
            "double_talk_near_si_sdr_db": 8, "noise_si_sdr_improvement_db": 4,
            "vad_f1": 0.9, "threshold_report": "result.json",
        },
        "thermal_power": {"ambient_c": 25, "max_soc_c": 60, "average_power_w": 1},
        "soak": {"hours": 8, "passed": True, "xruns": 0, "deadline_misses": 0, "output_drop_events": 0},
        "artifacts": {
            "result_json": "result.json", "benchmark_json": "bench.json",
            "evidence_manifest": "evidence.json", "sha256": "0" * 64,
        },
    }


def self_test() -> None:
    policy = {
        "policy_id": "test-policy", "max_active_cpu_percent": 40,
        "max_rss_kib": 4096, "max_p95_us": 7000, "max_p99_us": 9000,
        "max_soc_c": 85, "max_average_power_w": 2, "min_far_end_erle_db": 15,
        "max_aec_convergence_ms": 1000, "min_double_talk_near_si_sdr_db": 5,
        "min_noise_si_sdr_improvement_db": 3, "min_vad_f1": 0.85,
        "min_soak_hours": 8,
    }
    ph, ch, eh = "1" * 64, "2" * 64, "3" * 64
    evidence = {
        "schema_version": 1, "collector_version": "1", "generated_at": "now",
        "artifacts": [{"path": "x", "type": "benchmark", "size": 1, "sha256": "4" * 64}],
    }
    record = fixture(ph, ch, eh)
    assert validate(record, policy, ph, evidence, eh, ch) == []
    bad = json.loads(json.dumps(record))
    bad["policy_sha256"] = "0" * 64
    assert validate(bad, policy, ph, evidence, eh, ch)

    with tempfile.TemporaryDirectory(prefix="ap-cert-validator-") as temporary:
        root = Path(temporary)
        binary = root / "ap_bench"
        binary.write_bytes(b"x")
        binary_hash = sha256(binary)
        provenance = root / "deployment-provenance.json"
        provenance.write_text("{}\n", encoding="utf-8")
        evidence_v3 = {
            "schema_version": 1, "collector_version": "2", "generated_at": "now",
            "artifacts": [{
                "path": "ap_bench", "type": "binary:ap_bench", "size": 1,
                "sha256": binary_hash,
            }],
        }
        v3 = fixture(ph, ch, eh)
        v3["schema_version"] = 3
        v3["build"].update({
            "commit": "a" * 40, "source_revision": "a" * 40,
            "fingerprint": "6" * 64, "config_digest": "7" * 64,
            "compiler_id": "GNU", "compiler_version": "13.3",
            "target_triple": "arm-linux-gnueabihf", "build_type": "Release",
            "binary_sha256": {"ap_bench": binary_hash},
        })
        v3["soak"].update({
            "overruns": 0, "input_full_events": 0, "failed_frames": 0,
            "p95_us": 1000, "p99_us": 2000,
        })
        v3["artifacts"]["binary_sha256"] = {"ap_bench": binary_hash}
        assert validate(v3, policy, ph, evidence_v3, eh, ch, root) == []

        policy_v4 = {**policy, "sku": "test", "shipping_approved": True, "min_soak_hours": 72}
        v4 = json.loads(json.dumps(v3))
        v4["schema_version"] = 4
        v4["soak"]["hours"] = 72
        cmake_args = ["-DCMAKE_TOOLCHAIN_FILE=/opt/tc/toolchain.cmake", "-DAP_BUILD_PIPELINE=ON"]
        cmake_args_hash = hashlib.sha256(json.dumps(
            cmake_args, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        v4["deployment"] = {
            "schema_version": 1,
            "source_revision": "a" * 40,
            "builder_runner": "builder-1",
            "dut_runner": "dut-1",
            "binary_sha256": {"ap_bench": binary_hash},
            "result": "PASS",
            "toolchain": {
                "compiler_path": "/opt/tc/bin/cc",
                "compiler_sha256": "8" * 64,
                "compiler_version": "GNU 13.3",
                "sysroot_path": "/opt/tc/sysroot",
                "sysroot_sha256": "9" * 64,
                "toolchain_root_path": "/opt/tc",
                "toolchain_root_sha256": "a" * 64,
                "cflags": "-O2 -mcpu=cortex-a32",
                "cmake_args": cmake_args,
                "cmake_args_sha256": cmake_args_hash,
            },
        }
        v4["artifacts"]["deployment_provenance"] = "evidence/deployment-provenance.json"
        evidence_v4 = json.loads(json.dumps(evidence_v3))
        evidence_v4["artifacts"].append({
            "path": "deployment-provenance.json", "type": "deployment-provenance",
            "size": provenance.stat().st_size, "sha256": sha256(provenance),
        })
        assert validate(v4, policy_v4, ph, evidence_v4, eh, ch, root) == []
        bad_v4 = json.loads(json.dumps(v4))
        bad_v4["deployment"]["toolchain"]["cmake_args_sha256"] = "0" * 64
        assert validate(bad_v4, policy_v4, ph, evidence_v4, eh, ch, root)

        binary.write_bytes(b"tampered")
        assert validate(v3, policy, ph, evidence_v3, eh, ch, root)
    print("audio-pipeline certification validator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path, nargs="?")
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--evidence-manifest", type=Path)
    parser.add_argument("--corpus-manifest", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.record is None:
        parser.error("record is required unless --self-test is used")
    record = json.loads(args.record.read_text(encoding="utf-8"))
    policy = json.loads(args.policy.read_text(encoding="utf-8")) if args.policy else None
    evidence = (
        json.loads(args.evidence_manifest.read_text(encoding="utf-8"))
        if args.evidence_manifest else None
    )
    errors = validate(
        record,
        policy,
        sha256(args.policy) if args.policy else None,
        evidence,
        sha256(args.evidence_manifest) if args.evidence_manifest else None,
        sha256(args.corpus_manifest) if args.corpus_manifest else None,
        args.evidence_manifest.parent if args.evidence_manifest else None,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"certification record OK: {args.record}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
