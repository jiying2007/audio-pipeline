#!/usr/bin/env python3
"""Fixed-product measurement-model audit; not a shipping corpus or optimizer.

Reuse the canonical PCM primitives and evaluator from an exact base worktree.
Compare legacy excitation/path assumptions with an explicit first-order image
fixture. Different corpora are not a before/after DSP improvement experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RATE = 16000
FRAME = 160


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def check_model(model: dict) -> None:
    room = model["room_dimensions_m"]
    require(len(room) == 3 and all(math.isfinite(v) and v >= 2.0 for v in room), "room geometry")
    d = model["speaker_mic_distance_m"]
    c = model["speed_of_sound_m_s"]
    total = model["direct_total_delay_ms"]
    nominal = model["nominal_reference_delay_ms"]
    require(all(math.isfinite(v) for v in [d, c, total, nominal]) and
            0.01 <= d <= 0.2 and 300 <= c <= 370 and 0 <= nominal < total < 100,
            "invalid geometry/causal margin")
    require(total / 1000 > d / c, "I/O latency must be nonnegative")
    require(model["sample_rate_hz"] == RATE and
            model["excitation"] == ["colored-broadband", "speech-envelope-broadband"] and
            model["motion"] == ["stationary", "translation", "rotation"] and
            model["direct_gain"] == [0.30, 0.03], "unsupported diagnostic design")


def excitation(count: int, seed: int, kind: str) -> list[int]:
    require(kind in {"colored-broadband", "speech-envelope-broadband"}, "excitation kind")
    rng = random.Random(seed)
    value = 0.0
    phase = rng.random() * math.tau
    out = []
    for n in range(count):
        value = 0.65 * value + 0.35 * rng.uniform(-1.0, 1.0)
        envelope = 1.0
        if kind == "speech-envelope-broadband":
            # An amplitude-modulated stochastic probe, not human speech or VAD gold.
            envelope = 0.12 + 0.88 * (0.5 + 0.5 * math.sin(math.tau * 2.7 * n / RATE + phase)) ** 2
        out.append(round(11000.0 * value * envelope))
    return out


def paths(model: dict, time_s: float, motion: str, seed: int, direct_gain: float) -> tuple[list[float], list[float]]:
    room = model["room_dimensions_m"]
    phase = (seed % 997) / 997.0 * math.tau
    x, y, z = room[0] / 2, room[1] / 2, 0.7
    yaw = phase
    if motion == "translation":
        x += 0.65 * math.sin(math.tau * 0.11 * time_s + phase)
        y += 0.45 * math.sin(math.tau * 0.13 * time_s + phase)
    elif motion == "rotation":
        yaw += 2.0 * time_s
    else:
        require(motion == "stationary", "motion kind")
    d = model["speaker_mic_distance_m"]
    dx, dy = d * math.cos(yaw) / 2, d * math.sin(yaw) / 2
    speaker, mic = [x + dx, y + dy, z], [x - dx, y - dy, z]
    require(all(0 < speaker[i] < room[i] and 0 < mic[i] < room[i] for i in range(3)), "outside room")
    images = [speaker]
    for axis, length in enumerate(room):
        low, high = speaker.copy(), speaker.copy()
        low[axis], high[axis] = -speaker[axis], 2 * length - speaker[axis]
        images.extend([low, high])
    distances = [math.dist(mic, image) for image in images]
    io_s = model["direct_total_delay_ms"] / 1000 - d / model["speed_of_sound_m_s"]
    delays = [(io_s + distance / model["speed_of_sound_m_s"]) * RATE for distance in distances]
    # Fixed direct damping models different enclosures. Reflections use bounded
    # inverse-distance spreading and wall pressure coefficients, not moving I/O.
    beta = [0.75, 0.64, 0.60, 0.52, 0.45, 0.35]
    gains = [direct_gain] + [0.10 * b / distance for b, distance in zip(beta, distances[1:])]
    return delays, gains


def sidelobe(signal: list[int]) -> dict:
    # Excitation diagnostic only, not the product render-correlation metric.
    # Fixed segment, stride and mean-free cosine definition are recorded below.
    indices = list(range(2048, min(len(signal), 10240), 4))
    require(len(indices) >= 1024, "insufficient excitation support")
    scores = []
    for lag in range(32, 1921):
        a = [signal[i] for i in indices]
        b = [signal[i - lag] for i in indices]
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        aa = sum((v - ma) ** 2 for v in a)
        bb = sum((v - mb) ** 2 for v in b)
        cross = sum((u - ma) * (v - mb) for u, v in zip(a, b))
        score = abs(cross) / math.sqrt(max(1.0, aa * bb))
        scores.append((score, lag))
    score, lag = max(scores)
    return {"definition": "absolute mean-free cosine, indices 2048:10240:4, lags 32..1920",
            "peak": score, "lag_samples": lag, "samples_compared": len(indices)}


def build_fixture(output: Path, seed: int, seconds: float, model: dict, legacy: object, expected: dict) -> dict:
    check_model(model)
    require(not output.exists() or not any(output.iterdir()), "fixture output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    count = int(seconds * RATE)
    cases, geometry = [], []
    for kind in model["excitation"]:
        render = excitation(count, seed, kind)
        for motion in model["motion"]:
            for direct_gain in model["direct_gain"]:
                case_id = f"geometry-{kind}-{motion}-direct-{direct_gain:.2f}"
                folder = output / "cases" / case_id
                folder.mkdir(parents=True)
                echo, truth = [], []
                lower, upper = [math.inf] * 7, [-math.inf] * 7
                for n in range(count):
                    delays, gains = paths(model, n / RATE, motion, seed, direct_gain)
                    value = 0.0
                    for tap in range(7):
                        lower[tap] = min(lower[tap], delays[tap])
                        upper[tap] = max(upper[tap], delays[tap])
                        value += gains[tap] * legacy.sample(render, n - delays[tap])
                    echo.append(legacy.clamp16(value))
                    if n % FRAME == 0:
                        truth.append({"sample": n, "delay_samples": delays, "gain": gains})
                direct = model["direct_total_delay_ms"] * RATE / 1000
                require(abs(lower[0] - direct) < 1e-6 and abs(upper[0] - direct) < 1e-6,
                        "direct path moved")
                require(min(lower[1:]) > upper[0], "reflection precedes direct")
                require(max(abs(v) for v in echo) < 32767, "fixture clipped")
                legacy.write_pcm(folder / "mic.pcm", echo)
                legacy.write_pcm(folder / "echo.pcm", echo)
                legacy.write_pcm(folder / "render.pcm", render)
                write_json(folder / "ground-truth.json", {"sample_rate_hz": RATE,
                    "frame_samples": FRAME, "path_min_samples": lower, "path_max_samples": upper,
                    "frame_start_paths": truth, "model": model})
                geometry.append({"case_id": case_id, "earliest_path_samples": lower[0],
                                 "initial_causal_margin_samples": lower[0] - model["nominal_reference_delay_ms"] * RATE / 1000,
                                 "minimum_reflection_samples": min(lower[1:])})
                relative = folder.relative_to(output)
                cases.append({"case_id": case_id, "split": "dev", "scenario": "aec-continuous-motion",
                    "sample_rate_hz": RATE, "mic_channels": 1,
                    "mic_audio": str(relative / "mic.pcm"), "render_audio": str(relative / "render.pcm"),
                    "echo_audio": str(relative / "echo.pcm"), "clean_near_audio": None,
                    "vad_labels": None, "control": {}, "processor_profile": "default",
                    "expected": dict(expected),
                    "source": {"dataset_id": "deterministic-aec-geometry-audit-v1", "source_id": case_id,
                               "generator_seed": seed, "movement": motion != "stationary"}})
    corpus = {"schema_version": 1, "corpus_id": f"aec-geometry-audit-seed-{seed}", "tier": "regression",
              "generator": {"name": Path(__file__).name, "version": 1, "seed": seed, "seconds": seconds},
              "sources": ["deterministic-aec-geometry-audit-v1"], "sealed_data": False, "cases": cases}
    write_json(output / "corpus.json", corpus)
    write_json(output / "source-manifest.json", {"schema_version": 1,
        "authority": "development-only-non-shipping", "seed": seed, "cases": len(cases),
        "corpus_sha256": digest(output / "corpus.json"), "generator_sha256": digest(Path(__file__)),
        "primitive_source_sha256": digest(Path(legacy.__file__)),
        "files": {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}})
    return {"cases": geometry, "excitation": {
        kind: sidelobe(excitation(count, seed, kind)) for kind in model["excitation"]}}


def self_test() -> None:
    model = json.loads((ROOT / "docs/program/iterations/I001.json").read_text())["model"]
    check_model(model)
    for motion in model["motion"]:
        for seed in [0, 16411, 36411]:
            for time_s in [0.0, 0.13, 1.7, 3.99]:
                delays, gains = paths(model, time_s, motion, seed, 0.3)
                require(abs(delays[0] - 672) < 1e-6 and min(delays[1:]) > delays[0], "causal fixture")
                require(all(math.isfinite(v) and v > 0 for v in gains), "gain fixture")
    for kind in model["excitation"]:
        require(excitation(16000, 1, kind) == excitation(16000, 1, kind), "determinism")
        require(excitation(16000, 1, kind) != excitation(16000, 2, kind), "seed isolation")
        require(sidelobe(excitation(16000, 1, kind))["peak"] < 0.30, "broadband sidelobe sanity")
    periodic = [round(10000 * math.sin(math.tau * n / 80)) for n in range(16000)]
    require(sidelobe(periodic)["peak"] > 0.999, "periodic negative control not detected")
    for field, value in [("direct_total_delay_ms", 39.0), ("speed_of_sound_m_s", float("nan")),
                         ("speaker_mic_distance_m", -1.0)]:
        bad = dict(model, **{field: value})
        try:
            check_model(bad)
        except ValueError:
            continue
        raise AssertionError("bad model accepted")
    with tempfile.TemporaryDirectory() as temp:
        nonempty = Path(temp)
        (nonempty / "stale").write_text("stale")
        try:
            build_fixture(nonempty, 1, 4.0, model, None, {})
        except ValueError:
            pass
        else:
            raise AssertionError("stale output accepted")
    print("AEC model audit self-test: geometry/determinism/alias negative controls OK")


def run(contract_path: Path, output: Path) -> int:
    contract = json.loads(contract_path.read_text())
    require(contract["iteration_id"] == "I001" and contract["phase"] == "discovery" and
            contract["candidate_limit"] == 0 and contract["confirmation_limit"] == 0 and
            contract["promotion_allowed"] is False and contract["data_role"] == "development", "authority")
    require(4 <= contract["seconds"] <= 8 and len(contract["seeds"]) == 3, "bounded experiment")
    check_model(contract["model"])
    require(not output.exists() or not any(output.iterdir()), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    base_sha = contract["base_sha"]
    tool_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(subprocess.check_output(["git", "rev-parse", base_sha + "^{commit}"], cwd=ROOT, text=True).strip() == base_sha,
            "base must be exact available commit")
    shutil.copyfile(contract_path, output / "contract.json")
    shutil.copyfile(__file__, output / Path(__file__).name)
    result = {"schema_version": 1, "iteration_id": "I001", "processor_source_sha": base_sha,
              "tool_source_sha": tool_sha, "contract_sha256": digest(contract_path),
              "python": platform.python_version(), "platform": platform.platform(),
              "authority": "measurement-discovery-only", "candidate_decision": "NOT_A_CANDIDATE",
              "product_qualification": "DEFERRED_BY_SCOPE", "seeds": [], "errors": []}
    write_json(output / "audit-result.json", result)

    def command(argv: list[str], cwd: Path, name: str, timeout: int = 180) -> None:
        with (output / f"{name}.log").open("w") as log:
            completed = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                       timeout=timeout, check=False)
        with (output / "commands.jsonl").open("a") as record:
            record.write(json.dumps({"argv": argv, "cwd": str(cwd), "returncode": completed.returncode}) + "\n")
        require(completed.returncode == 0, f"{name} failed: {completed.returncode}")

    with tempfile.TemporaryDirectory(prefix="ap-program-audit-") as temp:
        worktree = Path(temp) / "base"
        try:
            command(["git", "worktree", "add", "--detach", str(worktree), base_sha], ROOT, "worktree")
            command(["git", "archive", "--format=tar", "-o", str(output / "base-source.tar"), base_sha], ROOT, "archive-base")
            command(["git", "archive", "--format=tar", "-o", str(output / "tool-source.tar"), tool_sha], ROOT, "archive-tool")
            command(["cc", "--version"], worktree, "compiler")
            build = Path(temp) / "build"
            command(["cmake", "-S", str(worktree), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                     "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON"], worktree, "configure")
            command(["cmake", "--build", str(build), "--target", "ap_process_pcm", "ap_build_info_dump", "--parallel", "2"],
                    worktree, "build")
            command([str(build / "ap_build_info_dump")], worktree, "build-info")
            processor = output / "ap_process_pcm"
            shutil.copy2(build / "ap_process_pcm", processor)
            result["processor_sha256"] = digest(processor)
            module_path = worktree / "validation/tools/build_aec_motion_corpus.py"
            spec = importlib.util.spec_from_file_location("exact_motion_base", module_path)
            legacy = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(legacy)
            policy = worktree / "validation/policies/validation-aec-motion-development.json"
            result["policy_sha256"] = digest(policy)
            for seed in contract["seeds"]:
                try:
                    folder = output / f"seed-{seed}"
                    folder.mkdir()
                    old = legacy.build(folder / "legacy", seed, contract["seconds"])
                    legacy_paths = []
                    for case in old["cases"]:
                        src = case["source"]
                        delays, _ = legacy.motion_path(src["generator_seed"], src["motion_family"], src["motion_intensity"])
                        legacy_paths.append({"case_id": case["case_id"], "earliest_knot_min_samples": min(delays[0]),
                            "earliest_knot_max_samples": max(delays[0]),
                            "initial_margin_min_samples": min(delays[0]) - contract["model"]["nominal_reference_delay_ms"] * RATE / 1000})
                    require(all(c["expected"] == old["cases"][0]["expected"] for c in old["cases"]), "nonuniform legacy policy")
                    geometry = build_fixture(folder / "geometry", seed, contract["seconds"], contract["model"], legacy, old["cases"][0]["expected"])
                    if seed == contract["seeds"][0]:
                        repeat = folder / "geometry-repeat"
                        build_fixture(repeat, seed, contract["seconds"], contract["model"], legacy, old["cases"][0]["expected"])
                        require(legacy.tree_digest(folder / "geometry") == legacy.tree_digest(repeat), "full fixture determinism")
                        shutil.rmtree(repeat)
                    row = {"seed": seed, "data_role": "development", "legacy_paths": legacy_paths,
                           "legacy_excitation": sidelobe(legacy.render_signal(int(contract["seconds"] * RATE), seed + 17)),
                           "geometry": geometry, "reports": {}}
                    write_json(folder / "model-diagnostics.json", row)
                    for mode in ["legacy", "geometry"]:
                        corpus_root = folder / mode
                        report_path = folder / f"{mode}-report.json"
                        # Deliberately measure (no --enforce): baseline FAIL is data,
                        # never a passed acoustic gate and never promotion authority.
                        command([sys.executable, str(worktree / "validation/tools/run_validation.py"),
                                 "--source-revision", base_sha, "--corpus", str(corpus_root / "corpus.json"),
                                 "--policy", str(policy), "--dataset-lock", str(worktree / "validation/datasets.lock.json"),
                                 "--source-manifest", str(corpus_root / "source-manifest.json"),
                                 "--processor", str(processor), "--output", str(report_path),
                                 "--evidence-manifest", str(folder / f"{mode}-evidence.json")], worktree, f"seed-{seed}-{mode}")
                        report = json.loads(report_path.read_text())
                        require(report["source_revision"] == base_sha and len(report["cases"]) == 12,
                                "wrong source or incomplete cases")
                        require(report["validation_result"] in {"PASS", "FAIL"}, "unknown quality result")
                        row["reports"][mode] = {"validation_result": report["validation_result"],
                                                "summary": report["summary"], "report_sha256": digest(report_path)}
                    result["seeds"].append(row)
                except Exception as exc:  # Preserve all seeds, but fail final integrity.
                    result["errors"].append({"seed": seed, "error": str(exc)})
                write_json(output / "audit-result.json", result)
        except Exception as exc:
            result["errors"].append({"stage": "setup", "error": str(exc)})
        finally:
            if worktree.exists():
                cleanup = subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=ROOT,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
                if cleanup.returncode != 0:
                    result["errors"].append({"stage": "cleanup", "error": cleanup.stdout})
    result["execution_result"] = "COMPLETE" if not result["errors"] and len(result["seeds"]) == 3 else "FAILED"
    result["next_action"] = "review-model-evidence-before-canonical-migration"
    write_json(output / "audit-result.json", result)
    write_json(output / "files.sha256.json", {str(p.relative_to(output)): digest(p)
               for p in sorted(output.rglob("*")) if p.is_file() and p.name != "files.sha256.json"})
    print(json.dumps({"execution_result": result["execution_result"], "candidate_decision": "NOT_A_CANDIDATE",
                      "seeds_completed": len(result["seeds"]), "errors": result["errors"]}))
    return 0 if result["execution_result"] == "COMPLETE" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.contract is None or args.output is None:
        parser.error("--contract and --output required")
    return run(args.contract, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
