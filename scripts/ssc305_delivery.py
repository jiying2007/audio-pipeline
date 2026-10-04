#!/usr/bin/env python3
"""Bind the existing SSC305 resource gate to consumable, non-DUT evidence.

No evaluator, DSP tuning policy or BSP certification lives here. Acoustic checks
invoke the canonical generator/validator at frozen seeds and unchanged policy.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PRESET = "ssc305-cortex-a32-low"
SEEDS = (1307, 2307, 3307)
FLAGS = ["-O3", "-mcpu=cortex-a32", "-mfpu=neon-fp-armv8", "-mfloat-abi=hard"]
QEMU = ["qemu-arm", "-cpu", "max", "-L", "/usr/arm-linux-gnueabihf"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(result, dict), f"not an object: {path}")
    return result


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run(*command: str | Path, stdout: Path | None = None, env: dict | None = None) -> None:
    args = list(map(str, command))
    if stdout:
        with stdout.open("w", encoding="utf-8") as stream:
            subprocess.run(args, cwd=ROOT, check=True, stdout=stream, env=env)
    else:
        subprocess.run(args, cwd=ROOT, check=True, env=env)


def pack(root: Path, output: Path, epoch: int) -> None:
    """Deterministic packaging, not an independent rebuild reproducibility claim."""
    with output.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.GNU_FORMAT) as tar:
            for path in sorted(root.rglob("*")):
                require(not path.is_symlink(), f"unexpected symlink: {path}")
                if not path.is_file():
                    continue
                info = tar.gettarinfo(str(path), arcname=path.relative_to(root).as_posix())
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = epoch
                info.mode = 0o755 if path.stat().st_mode & 0o111 else 0o644
                with path.open("rb") as stream:
                    tar.addfile(info, stream)


def seal(root: Path, record: dict) -> None:
    record["files"] = {p.relative_to(root).as_posix(): digest(p)
                       for p in sorted(root.rglob("*")) if p.is_file()
                       and p.relative_to(root).as_posix() not in {"delivery-manifest.json", "SHA256SUMS"}}
    write(root / "delivery-manifest.json", record)
    (root / "SHA256SUMS").write_text("".join(
        f"{digest(p)}  {p.relative_to(root).as_posix()}\n"
        for p in sorted(root.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"), encoding="utf-8")


def acoustic(processor: Path, out: Path, source: str) -> dict:
    sys.path.insert(0, str(ROOT / "validation/tools"))
    import run_validation
    invoke = run_validation.canonical_evaluation_semantics().invoke
    out.mkdir(parents=True, exist_ok=True)
    replay = []
    for seed in SEEDS:
        corpus_dir = out / str(seed)
        run(sys.executable, "validation/tools/build_validation_corpus.py", "--output", corpus_dir, "--seed", str(seed))
        corpus = corpus_dir / "corpus.json"
        cases = read(corpus)["cases"]
        require(len(cases) == 27, "canonical corpus cardinality changed; review required")
        run(sys.executable, "validation/tools/run_validation.py", "--corpus", corpus,
            "--policy", "validation/policies/validation-smoke.json",
            "--dataset-lock", "validation/datasets.lock.json", "--processor", processor,
            "--source-revision", source, "--output", corpus_dir / "report.json",
            "--evidence-manifest", corpus_dir / "evidence.json", "--enforce", stdout=corpus_dir / "validation-summary.txt")
        report = read(corpus_dir / "report.json")
        require(report["validation_result"] == "PASS", "canonical acoustic policy failed")
        for case in cases:
            with tempfile.TemporaryDirectory(prefix="ssc305-pcm-repeat-") as tmp:
                hashes = []
                for repeat in (0, 1):
                    work = Path(tmp) / str(repeat)
                    work.mkdir()
                    invoke(processor, case, corpus, work)
                    hashes.append(digest(work / "out.pcm"))
                require(hashes[0] == hashes[1], f"PCM repeat mismatch: {seed}/{case['case_id']}")
                replay.append({"seed": seed, "case_id": case["case_id"], "output_pcm_sha256": hashes[0]})
    result = {"schema_version": 1, "authority": "regression-only-not-public-or-product-acoustics",
              "source_revision": source, "seeds": list(SEEDS), "cases": len(replay),
              "policy_sha256": digest(ROOT / "validation/policies/validation-smoke.json"),
              "processor_launcher_sha256": digest(processor),
              "pcm_repeat_sha256_equal": True, "replay": replay,
              "unmeasured": ["real-motor-noise", "real-enclosure-far-field", "shipping-route-acoustics"]}
    write(out / "snapshot.json", result)
    return result


def reference(args: argparse.Namespace) -> None:
    out, build = args.output.resolve(), args.build.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = args.source_revision
    resources = read(args.resource_qualification)
    require(resources.get("schema_version") == 2 and resources.get("status") == "PASS", "resource qualification required")
    require(resources.get("source_revision") == source, "resource source mismatch")
    measured = resources["profiles"]["conservative"]["measured"]
    probe = measured["probe"]
    require(measured["preset"] == PRESET, "wrong reference preset")
    shutil.copy2(args.resource_qualification, out / "resource-qualification.json")
    for rel in ("CMakePresets.json", "ci/ssc305-resource-profiles.json", "cmake/toolchains/arm-linux-gnueabihf.cmake"):
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    with tempfile.TemporaryDirectory(prefix="ssc305-installed-") as tmp:
        prefix = Path(tmp) / "sdk"
        run("cmake", "--install", build, "--prefix", prefix)
        generated = prefix / "include/audio_pipeline/audio_pipeline_build.h"
        header = generated.read_text()
        for token in ('#define AP_BUILD_RESAMPLER_MODE_NAME "BANDLIMITED"', '#define AP_BUILD_FAST_MATH 0',
                      '#define AP_HAVE_LINUX_RUNTIME 1'):
            require(token in header, f"reference header drift: {token}")
        shutil.copy2(generated, out / "audio_pipeline_build.h")
        core, runtime = prefix / "lib/libaudio_pipeline.a", prefix / "lib/libaudio_pipeline_runtime.a"
        libraries = {"lib/libaudio_pipeline.a": digest(core), "lib/libaudio_pipeline_runtime.a": digest(runtime)}
        run("cmake", "-S", ROOT / "tests/consumer", "-B", Path(tmp) / "consumer",
            f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/arm-linux-gnueabihf.cmake'}",
            f"-DCMAKE_PREFIX_PATH={prefix}", "-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH",
            "-DCMAKE_C_FLAGS=" + " ".join(FLAGS))
        run("cmake", "--build", Path(tmp) / "consumer", "--parallel", "4")
        run(*QEMU, Path(tmp) / "consumer/audio_pipeline_consumer", stdout=out / "cmake-consumer.txt")
        for name, src, libs in (
            ("runtime-consumer", "tests/consumer/runtime_main.c", [runtime, core]),
            ("build-info-consumer", "tests/test_build_info.c", [core]),
            ("installed-probe", "tests/validation/resource_profile_probe.c", [runtime, core]),
            ("ap_process_pcm", "examples/process_pcm.c", [core]),
        ):
            run("arm-linux-gnueabihf-gcc", *FLAGS, "-I" + str(prefix / "include"), ROOT / src,
                *libs, "-lm", "-pthread", "-o", out / name)
            if name != "ap_process_pcm":
                run(*QEMU, out / name, stdout=out / (name + ".json" if name == "installed-probe" else name + ".txt"))
        require(read(out / "installed-probe.json") == probe, "installed SDK and measured build differ")
        env = dict(os.environ, PKG_CONFIG_LIBDIR=str(prefix / "lib/pkgconfig"), PKG_CONFIG_SYSROOT_DIR="")
        pcflags = subprocess.check_output(["pkg-config", "--cflags", "--libs", "audio-pipeline"], env=env, text=True).split()
        run("arm-linux-gnueabihf-gcc", *FLAGS, "-I" + str(prefix / "include"), ROOT / "tests/consumer/consumer.c",
            *pcflags, "-o", out / "pkgconfig-consumer")
        run(*QEMU, out / "pkgconfig-consumer", stdout=out / "pkgconfig-consumer.txt")
        run("arm-linux-gnueabihf-gcc", "--version", stdout=out / "compiler.txt")
        run("arm-linux-gnueabihf-gcc", "-print-sysroot", stdout=out / "compiler-sysroot.txt")
        run("dpkg-query", "-W", "libc6-armhf-cross", "gcc-13-arm-linux-gnueabihf", stdout=out / "reference-toolchain-packages.txt")
        run("arm-linux-gnueabihf-readelf", "-h", out / "ap_process_pcm", stdout=out / "elf-header.txt")
        require("ELF32" in (out / "elf-header.txt").read_text() and "ARM" in (out / "elf-header.txt").read_text(), "processor is not AArch32")
        epoch = int(subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "show", "-s", "--format=%ct", "HEAD"], cwd=ROOT, text=True))
        pack(prefix, out / "reference-armhf-sdk.tar.gz", epoch)
        pack(prefix, Path(tmp) / "repeat.tar.gz", epoch)
        require(digest(out / "reference-armhf-sdk.tar.gz") == digest(Path(tmp) / "repeat.tar.gz"), "SDK packaging is not deterministic")
        run(sys.executable, "tools/generate_spdx_sbom.py", "--root", prefix, "--name", "audio-pipeline-reference-armhf",
            "--version", probe["version"], "--revision", source, "--created-epoch", str(epoch), "--output", out / "reference-armhf.spdx.json")
    launcher = out / "processor-qemu.sh"
    launcher.write_text('#!/bin/sh\nset -eu\nexec qemu-arm -cpu max -L /usr/arm-linux-gnueabihf "$(dirname "$0")/ap_process_pcm" "$@"\n')
    launcher.chmod(0o755)
    snapshot = acoustic(launcher, out / "acoustic", source)
    seal(out, {"schema_version": 1, "status": "PASS", "source_revision": source, "preset": PRESET,
               "config_digest": probe["config_digest"], "artifact_class": "reference-armhf-sdk-not-shipping-bsp",
               "timing_authority": "none-target", "product_certification_authority": False,
               "installed_consumers": ["CMake-core", "pkg-config-core", "runtime", "build-info"],
               "installed_library_sha256": libraries, "processor_elf_sha256": digest(out / "ap_process_pcm"),
               "processor_launcher_sha256": digest(launcher), "acoustic_cases": snapshot["cases"],
               "toolchain_image": args.toolchain_image, "emulator_sysroot": "/usr/arm-linux-gnueabihf"})
    verify(out, source, "reference-armhf-sdk-not-shipping-bsp")


def configure_endurance(args: argparse.Namespace) -> None:
    require(args.build is not None, "--build required")
    definitions = {p["name"]: p for p in read(ROOT / "CMakePresets.json")["configurePresets"]}
    def resolve(name: str) -> dict:
        item = definitions[name]
        inherited = item.get("inherits", [])
        if isinstance(inherited, str):
            inherited = [inherited]
        result = {}
        for parent in reversed(inherited):
            result.update(resolve(parent))
        result.update(item.get("cacheVariables", {}))
        return result
    original = resolve(PRESET)
    flags = "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer"
    options = {k: v for k, v in original.items() if k.startswith("AP_")}
    options.update(AP_SIMD_BACKEND="SCALAR", AP_BUILD_TESTS="ON", AP_BUILD_BENCH="OFF",
                   AP_BUILD_EXAMPLES="OFF", AP_STRICT_WARNINGS="ON", AP_BUILD_SOURCE_REVISION=args.source_revision)
    run("cmake", "-S", ROOT, "-B", args.build, "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_C_COMPILER=gcc",
        "-DCMAKE_C_FLAGS=" + flags, "-DCMAKE_EXE_LINKER_FLAGS=-fsanitize=address,undefined",
        *[f"-D{k}={v}" for k, v in sorted(options.items())])
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output / "configuration.json", {"reference_preset": PRESET, "reference_cache_variables": original,
                                               "effective_host_options": options, "c_flags": flags,
                                               "authority": "native-scalar-conservative-envelope-not-AArch32"})
    run("gcc", "--version", stdout=args.output / "compiler.txt")


def verify(root: Path, source: str, artifact_class: str) -> dict:
    record = read(root / "delivery-manifest.json")
    require(record.get("schema_version") == 1 and record.get("status") == "PASS", "delivery did not pass")
    require(record.get("source_revision") == source, "delivery source mismatch")
    require(re.fullmatch(r"[0-9a-f]{64}", str(record.get("config_digest", ""))) is not None, "invalid config digest")
    require(record.get("artifact_class") == artifact_class, "wrong evidence class")
    require(record.get("product_certification_authority") is False, "invalid certification authority")
    actual = {p.relative_to(root).as_posix(): digest(p) for p in root.rglob("*") if p.is_file()
              and p.relative_to(root).as_posix() not in {"delivery-manifest.json", "SHA256SUMS"}}
    require(actual == record.get("files") and bool(actual), "delivery file/hash set mismatch")
    if artifact_class == "reference-armhf-sdk-not-shipping-bsp":
        require(record.get("preset") == PRESET, "wrong reference preset")
        probe = read(root / "installed-probe.json")
        require(probe["source_revision"] == source and probe["config_digest"] == record["config_digest"], "installed identity mismatch")
        require(digest(root / "ap_process_pcm") == record["processor_elf_sha256"], "ELF hash mismatch")
        snapshot = read(root / "acoustic/snapshot.json")
        require(snapshot["cases"] == 81 and snapshot["seeds"] == list(SEEDS) and snapshot["pcm_repeat_sha256_equal"] is True, "incomplete acoustic replay")
        require(snapshot["source_revision"] == source and len(snapshot["replay"]) == 81, "acoustic source/count mismatch")
        require(len({(item["seed"], item["case_id"]) for item in snapshot["replay"]}) == 81, "duplicate replay cases")
        require(all(re.fullmatch(r"[0-9a-f]{64}", item["output_pcm_sha256"]) for item in snapshot["replay"]), "invalid PCM hash")
        require(record["processor_launcher_sha256"] == digest(root / "processor-qemu.sh") == snapshot["processor_launcher_sha256"], "launcher identity mismatch")
        resources = read(root / "resource-qualification.json")
        require(resources["source_revision"] == source and resources["status"] == "PASS", "resource qualification mismatch")
        require(resources["profiles"]["conservative"]["measured"]["probe"] == probe, "probe/resource drift")
        for seed in SEEDS:
            report = read(root / f"acoustic/{seed}/report.json")
            require(report["source_revision"] == source and report["validation_result"] == "PASS" and len(report["cases"]) == 27, "missing acoustic report")
        require(set(record["installed_library_sha256"]) == {"lib/libaudio_pipeline.a", "lib/libaudio_pipeline_runtime.a"}, "incomplete SDK library inventory")
        with tarfile.open(root / "reference-armhf-sdk.tar.gz") as sdk:
            for member, expected in record["installed_library_sha256"].items():
                stream = sdk.extractfile(member)
                require(stream is not None and hashlib.sha256(stream.read()).hexdigest() == expected, "SDK library mismatch")
    else:
        result = read(root / "result.json")
        require(result.get("source_revision") == source and result.get("status") == "PASS", "endurance identity/status mismatch")
        require(result.get("frames") == 2000000 and result.get("cycles") == 64, "incomplete endurance")
        require(result.get("fault_contract_cycles") == 64 and result.get("metadata_faults", 0) > 0 and result.get("missing_render_frames", 0) > 0, "missing fault execution")
        require(record.get("sanitizers") == ["address", "undefined", "leak"], "missing sanitizer qualification")
        require(result.get("config_digest") == record.get("config_digest"), "endurance config digest mismatch")
    return record


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root / "result.json", {"source_revision": "a" * 40, "status": "PASS", "frames": 2000000,
                                     "cycles": 64, "config_digest": "d" * 64, "fault_contract_cycles": 64, "metadata_faults": 10, "missing_render_frames": 10})
        record = {"schema_version": 1, "status": "PASS", "source_revision": "a" * 40,
                  "artifact_class": "host-engineering-not-product-soak", "product_certification_authority": False,
                  "sanitizers": ["address", "undefined", "leak"], "config_digest": "d" * 64}
        seal(root, record)
        verify(root, "a" * 40, record["artifact_class"])
        for field, value in (("source_revision", "b" * 40), ("status", "FAIL"), ("sanitizers", []), ("config_digest", None), ("product_certification_authority", True)):
            bad = copy.deepcopy(record)
            bad[field] = value
            write(root / "delivery-manifest.json", bad)
            try:
                verify(root, "a" * 40, record["artifact_class"])
            except ValueError:
                pass
            else:
                raise AssertionError(f"accepted invalid {field}")
        seal(root, record)
        (root / "result.json").write_text('{}')
        try:
            verify(root, "a" * 40, record["artifact_class"])
        except ValueError:
            pass
        else:
            raise AssertionError("accepted tampered evidence")
    print("SSC305 delivery positive/negative contracts: OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("reference", "acoustic", "verify", "seal-endurance", "configure-endurance", "self-test"))
    parser.add_argument("--source-revision")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--resource-qualification", type=Path)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--toolchain-image")
    parser.add_argument("--artifact-class", choices=("reference-armhf-sdk-not-shipping-bsp", "host-engineering-not-product-soak"))
    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
        return
    require(re.fullmatch(r"[0-9a-f]{40}", args.source_revision or "") is not None, "exact source SHA required")
    require(args.output is not None, "--output required")
    if args.command == "configure-endurance":
        configure_endurance(args)
    elif args.command == "reference":
        require(args.build is not None and args.resource_qualification is not None and bool(args.toolchain_image), "reference build/resource/image required")
        reference(args)
    elif args.command == "acoustic":
        require(args.processor is not None, "--processor required")
        acoustic(args.processor.resolve(), args.output.resolve(), args.source_revision)
    elif args.command == "seal-endurance":
        result = read(args.output / "result.json")
        require(result["source_revision"] == args.source_revision, "endurance source mismatch")
        header = (args.output / "audio_pipeline_build.h").read_text()
        require(f'#define AP_BUILD_CONFIG_DIGEST "{result["config_digest"]}"' in header, "endurance header digest mismatch")
        require(f'#define AP_BUILD_SOURCE_REVISION "{args.source_revision}"' in header, "endurance header source mismatch")
        require((args.output / "sanitizer.log").stat().st_size == 0, "sanitizer diagnostics are not empty")
        require((args.output / "runtime-extended-tests").is_file(), "missing executed endurance ELF")
        seal(args.output, {"schema_version": 1, "status": "PASS", "source_revision": args.source_revision,
                           "config_digest": result["config_digest"], "artifact_class": "host-engineering-not-product-soak",
                           "sanitizers": ["address", "undefined", "leak"], "product_certification_authority": False,
                           "timing_authority": "host-wall-only-not-silicon", "configuration": "native-scalar-conservative-envelope"})
        verify(args.output, args.source_revision, "host-engineering-not-product-soak")
    else:
        require(args.artifact_class is not None, "--artifact-class required")
        verify(args.output, args.source_revision, args.artifact_class)


if __name__ == "__main__":
    main()
