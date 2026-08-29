#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

VERSION = "3.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_digest(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def read_text(path: str | Path, default: str = "unknown") -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").replace("\x00", " ").strip()
    except OSError:
        return default


def command(args: list[str], default: str = "unknown") -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return default


def parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def git_revision() -> str:
    return command(["git", "rev-parse", "HEAD"])


def project_version() -> str:
    pattern = re.compile(r"^project\(audio_pipeline VERSION ([0-9]+\.[0-9]+\.[0-9]+) LANGUAGES C\)$")
    for line in Path("CMakeLists.txt").read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            return match.group(1)
    raise ValueError("cannot resolve project version")


def cpuinfo_field(name: str) -> str | None:
    text = read_text("/proc/cpuinfo", "")
    prefix = name.lower() + ":"
    for line in text.splitlines():
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def collect_governors() -> list[str]:
    values = set()
    for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor"):
        value = read_text(path, "")
        if value:
            values.add(value)
    return sorted(values) or ["unknown"]


def collect_frequencies() -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for cpu in Path("/sys/devices/system/cpu").glob("cpu[0-9]*"):
        freq = cpu / "cpufreq"
        if not freq.is_dir():
            continue
        values: dict[str, int] = {}
        for key in ("scaling_cur_freq", "scaling_max_freq", "cpuinfo_max_freq"):
            try:
                values[key] = int((freq / key).read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pass
        if values:
            result[cpu.name] = values
    return result


def current_cpuset() -> str:
    text = read_text("/proc/self/status", "")
    for line in text.splitlines():
        if line.startswith("Cpus_allowed_list:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def collect_platform() -> dict:
    model = read_text("/proc/device-tree/model", "") or cpuinfo_field("Hardware") or platform.machine()
    compatible = read_text("/proc/device-tree/compatible", "").replace(" ", ",")
    revision = cpuinfo_field("Revision") or read_text("/sys/devices/soc0/revision", "unknown")
    soc_id = read_text("/sys/devices/soc0/soc_id", "") or cpuinfo_field("Hardware") or platform.machine()
    return {
        "soc": soc_id,
        "model": model,
        "compatible": compatible or "unknown",
        "revision": revision,
        "machine": platform.machine(),
        "core_count": os.cpu_count() or 0,
        "kernel": platform.release(),
        "governor": ",".join(collect_governors()),
        "cpuset": current_cpuset(),
        "irq_default_affinity": read_text("/proc/irq/default_smp_affinity"),
        "isolated_cpus": read_text("/sys/devices/system/cpu/isolated", ""),
        "cpu_frequency_khz": collect_frequencies(),
    }


def load_json(path: Path, root: str) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if root not in value or not isinstance(value[root], dict):
        raise ValueError(f"{path}: missing object {root!r}")
    return value


def copy_evidence(source: Path, evidence_dir: Path, name: str) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = evidence_dir / name
    shutil.copy2(source, destination)
    return destination


def build_manifest(items: list[tuple[str, Path]], output_dir: Path, output: Path) -> dict:
    artifacts = []
    for artifact_type, path in items:
        relative = path.relative_to(output_dir)
        artifacts.append({
            "path": relative.as_posix(),
            "type": artifact_type,
            "size": path.stat().st_size,
            "sha256": digest(path),
        })
    manifest = {
        "schema_version": 1,
        "collector_version": VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "artifacts": artifacts,
    }
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def exact_build_info(binary: Path) -> tuple[dict[str, str], str]:
    text = subprocess.check_output([str(binary)], text=True)
    values = parse_key_values(text)
    required = {
        "version", "module_mask", "aec_backend", "ns_estimator", "simd_backend",
        "resampler_mode", "fast_math", "source_revision", "compiler_id",
        "compiler_version", "target_triple", "build_type", "config_digest",
    }
    missing = sorted(required - values.keys())
    if missing:
        raise ValueError(f"build-info output missing: {', '.join(missing)}")
    if not HEX64.fullmatch(values["config_digest"]):
        raise ValueError("build-info config_digest is not SHA-256")
    return values, text


def validate_deployment(provenance: dict, revision: str, binary_hashes: dict[str, str]) -> None:
    required = {"source_revision", "builder_runner", "dut_runner", "binary_sha256", "toolchain", "result"}
    missing = sorted(required - provenance.keys())
    if missing:
        raise ValueError("deployment provenance missing: " + ", ".join(missing))
    if provenance.get("result") != "PASS":
        raise ValueError("deployment provenance is not PASS")
    if provenance.get("source_revision") != revision:
        raise ValueError("deployment provenance revision does not match checkout")
    if provenance.get("builder_runner") == provenance.get("dut_runner"):
        raise ValueError("builder and DUT must be different runners")
    if provenance.get("binary_sha256") != binary_hashes:
        raise ValueError("deployment provenance binary hashes do not match certification binaries")
    toolchain = provenance.get("toolchain")
    if not isinstance(toolchain, dict):
        raise ValueError("deployment provenance has no toolchain object")
    for key in ("compiler_sha256", "sysroot_sha256", "toolchain_root_sha256"):
        if not HEX64.fullmatch(str(toolchain.get(key, ""))):
            raise ValueError(f"deployment toolchain {key} is not SHA-256")


def assemble(args: argparse.Namespace) -> Path:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = args.output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    benchmark = load_json(args.benchmark_json, "performance")
    acoustic = load_json(args.acoustic_json, "acoustic")
    soak_doc = load_json(args.soak_json, "soak")
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    policy_id = policy.get("policy_id")
    if not policy_id:
        raise ValueError("policy_id is required")
    if policy.get("shipping_approved") is not True:
        raise ValueError("product certification requires shipping_approved=true")
    if str(policy.get("sku")) != args.sku:
        raise ValueError("policy sku does not match --sku")
    if str(policy_id).startswith("example-") or "not-for-shipping" in str(policy_id):
        raise ValueError("example/not-for-shipping policy cannot create product certification")

    revision = git_revision()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("certification must run from an exact Git commit")
    build_info, build_info_text = exact_build_info(args.build_info_bin)
    if build_info["source_revision"] != revision:
        raise ValueError(
            f"binary source revision {build_info['source_revision']} != checkout {revision}"
        )
    if build_info["version"] != project_version():
        raise ValueError("binary version does not match CMake project version")

    binary_hashes: dict[str, str] = {}
    binary_items: list[tuple[str, Path]] = []
    binaries = [args.build_info_bin] + list(args.binary or [])
    seen: set[str] = set()
    for binary in binaries:
        resolved = binary.resolve()
        key = binary.name
        if key in seen:
            raise ValueError(f"duplicate certification binary name: {key}")
        seen.add(key)
        binary_hashes[key] = digest(resolved)
        binary_items.append((f"binary:{key}", resolved))

    deployment = json.loads(args.deployment_provenance.read_text(encoding="utf-8"))
    validate_deployment(deployment, revision, binary_hashes)

    build_identity = {
        "source_revision": revision,
        "version": build_info["version"],
        "module_mask": build_info["module_mask"],
        "aec_backend": build_info["aec_backend"],
        "ns_estimator": build_info["ns_estimator"],
        "simd_backend": build_info["simd_backend"],
        "resampler_mode": build_info["resampler_mode"],
        "fast_math": build_info["fast_math"],
        "compiler_id": build_info["compiler_id"],
        "compiler_version": build_info["compiler_version"],
        "target_triple": build_info["target_triple"],
        "build_type": build_info["build_type"],
        "config_digest": build_info["config_digest"],
        "binary_sha256": binary_hashes,
    }
    fingerprint = canonical_digest(build_identity)

    benchmark_perf = dict(benchmark["performance"])
    soak = dict(soak_doc["soak"])
    benchmark_perf.update({
        "xruns": int(soak.get("xruns", 0)),
        "overruns": int(soak.get("overruns", soak.get("deadline_misses", 0))),
        "input_full_events": int(soak.get("input_full_events", 0)),
        "output_drop_events": int(soak.get("output_drop_events", 0)),
    })
    thermal = dict(benchmark.get("thermal_power", {}))
    soak_thermal = soak_doc.get("thermal_power", {})
    required_thermal = ("ambient_c", "max_soc_c", "average_power_w")
    for key in required_thermal:
        if thermal.get(key) is None:
            raise ValueError(f"benchmark thermal_power.{key} is required; no fabricated value allowed")
    if soak_thermal.get("max_soc_c") is not None:
        thermal["max_soc_c"] = max(float(thermal["max_soc_c"]), float(soak_thermal["max_soc_c"]))

    staged: list[tuple[str, Path]] = []
    staged.append(("benchmark", copy_evidence(args.benchmark_json, evidence_dir, "benchmark.json")))
    staged.append(("acoustic", copy_evidence(args.acoustic_json, evidence_dir, "acoustic.json")))
    staged.append(("soak", copy_evidence(args.soak_json, evidence_dir, "soak.json")))
    staged.append(("policy", copy_evidence(args.policy, evidence_dir, "policy.json")))
    staged.append(("corpus-manifest", copy_evidence(args.corpus_manifest, evidence_dir, "corpus-manifest.json")))
    staged.append((
        "deployment-provenance",
        copy_evidence(args.deployment_provenance, evidence_dir, "deployment-provenance.json"),
    ))
    build_info_path = evidence_dir / "build-info.txt"
    build_info_path.write_text(build_info_text, encoding="utf-8")
    staged.append(("build-info", build_info_path))
    if args.cmake_cache:
        staged.append(("cmake-cache", copy_evidence(args.cmake_cache, evidence_dir, "CMakeCache.txt")))
    for artifact_type, binary in binary_items:
        staged.append((artifact_type, copy_evidence(binary, evidence_dir, binary.name)))

    evidence_path = args.output_dir / "evidence-manifest.json"
    build_manifest(staged, args.output_dir, evidence_path)

    record = {
        "schema_version": 4,
        "sku": args.sku,
        "status": "product-certified",
        "policy": policy_id,
        "policy_sha256": digest(args.policy),
        "corpus_manifest_sha256": digest(args.corpus_manifest),
        "evidence_manifest_sha256": digest(evidence_path),
        "collector_version": VERSION,
        "toolchain_digest": canonical_digest(deployment["toolchain"]),
        "build": {
            "commit": revision,
            "version": build_info["version"],
            "fingerprint": fingerprint,
            "compiler": f"{build_info['compiler_id']} {build_info['compiler_version']}",
            "abi": build_info["target_triple"],
            **build_identity,
        },
        "deployment": deployment,
        "platform": collect_platform(),
        "audio_route": {
            "capture_device": args.capture_device,
            "playback_device": args.playback_device,
            "sample_rate_hz": args.sample_rate,
            "mic_channels": args.mic_channels,
        },
        "performance": benchmark_perf,
        "acoustic": acoustic["acoustic"],
        "thermal_power": thermal,
        "soak": soak,
        "artifacts": {
            "result_json": "record.json",
            "benchmark_json": "evidence/benchmark.json",
            "evidence_manifest": "evidence-manifest.json",
            "deployment_provenance": "evidence/deployment-provenance.json",
            "sha256": digest(evidence_path),
            "binary_sha256": binary_hashes,
        },
    }
    output = args.output_dir / "record.json"
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return output


def self_test() -> int:
    assert parse_key_values("a=1\nb=two words\n") == {"a": "1", "b": "two words"}
    identity = {"source_revision": "a" * 40, "config_digest": "b" * 64}
    assert HEX64.fullmatch(identity["config_digest"])
    assert canonical_digest(identity) == canonical_digest(dict(reversed(list(identity.items()))))
    with tempfile.TemporaryDirectory(prefix="ap-certify-selftest-") as temporary:
        root = Path(temporary)
        sample = root / "sample"
        sample.write_bytes(b"audio-pipeline")
        assert digest(sample) == hashlib.sha256(b"audio-pipeline").hexdigest()
        manifest_path = root / "manifest.json"
        manifest = build_manifest([("sample", sample)], root, manifest_path)
        assert manifest["artifacts"][0]["path"] == "sample"
        assert manifest["artifacts"][0]["size"] == len(b"audio-pipeline")
        deployment = {
            "source_revision": "a" * 40,
            "builder_runner": "builder",
            "dut_runner": "dut",
            "binary_sha256": {"sample": digest(sample)},
            "toolchain": {
                "compiler_sha256": "c" * 64,
                "sysroot_sha256": "d" * 64,
                "toolchain_root_sha256": "e" * 64,
            },
            "result": "PASS",
        }
        validate_deployment(deployment, "a" * 40, {"sample": digest(sample)})
    print("audio-pipeline certification collector self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--sku")
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--corpus-manifest", type=Path)
    parser.add_argument("--benchmark-json", type=Path)
    parser.add_argument("--acoustic-json", type=Path)
    parser.add_argument("--soak-json", type=Path)
    parser.add_argument("--deployment-provenance", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--capture-device")
    parser.add_argument("--playback-device")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--mic-channels", type=int, default=2)
    parser.add_argument("--build-info-bin", type=Path)
    parser.add_argument("--binary", action="append", type=Path, default=[])
    parser.add_argument("--cmake-cache", type=Path)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    required = (
        "sku", "policy", "corpus_manifest", "benchmark_json", "acoustic_json",
        "soak_json", "deployment_provenance", "output_dir", "capture_device", "build_info_bin",
    )
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(missing))
    if args.sample_rate not in {8000, 16000, 24000, 32000, 48000}:
        parser.error("unsupported --sample-rate")
    if args.mic_channels not in {1, 2}:
        parser.error("--mic-channels must be 1 or 2")
    assemble(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
