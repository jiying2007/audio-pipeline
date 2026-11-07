"""Build D1's exact-source plain CLI and an explicitly transformed observer.

This command only builds and reads build identity. It never processes audio or
runs a model. Formal invocation belongs to the preregistered Actions job.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import time

EXPERIMENT = "FE-DUALMIC-STAGES-D1"
BASE_SHA = "4daa7e239eebda11f6c7066df2e851269021112f"
BASE_TREE = "605d5660d73ffb47c9d7bc5f4c2fd82e56cdeb36"
BUILD_BUDGET = 300
OBSERVER = "tests/validation/frontend_evolution/dualmic_stages_d1.c"
BUILDER = "tools/codex_assets/dualmic_stages_build.py"
PRODUCTION = ("CMakeLists.txt", "cmake", "src", "include", "examples")
RENAMES = {
    "src/activity/ap_activity.c": ("void", "ap_activity_process"),
    "src/aec/ap_aec_mdf.c": ("void", "ap_aec_backend_process"),
    "src/enhance/ap_ns.c": ("void", "ap_ns_process"),
    "src/enhance/ap_agc.c": ("void", "ap_agc_process_controlled"),
    "src/enhance/ap_res.c": ("float", "ap_res_process"),
}
SHA = re.compile(r"[0-9a-f]{40}\Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def json_write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def git(source: Path, *arguments: str) -> bytes:
    result = subprocess.run(["git", "-C", str(source), *arguments], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    return result.stdout


def clean_head(source: Path, revision: str) -> str:
    require(git(source, "rev-parse", "--verify", "HEAD").decode().strip() == revision,
            "checkout HEAD does not match the requested source revision")
    require(not git(source, "status", "--porcelain=v1", "--untracked-files=all").strip(),
            "tracked or untracked checkout changes are forbidden; ignored build files are allowed")
    tree = git(source, "rev-parse", revision + "^{tree}").decode().strip()
    require(bool(SHA.fullmatch(tree)), "source tree identity is not a full SHA")
    return tree


def production_entries(source: Path, revision: str) -> dict[str, dict[str, str]]:
    entries = {}
    for row in git(source, "ls-tree", "-r", "-z", "--full-tree", revision,
                   "--", *PRODUCTION).split(b"\0"):
        if not row:
            continue
        metadata, raw_path = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        name = raw_path.decode("utf-8")
        require(kind == "blob" and mode in ("100644", "100755"),
                "production source must contain only regular Git blobs")
        require(name not in entries, "duplicate production Git path")
        entries[name] = {"git_mode": mode, "git_blob": oid}
    require(bool(entries), "empty production source inventory")
    return entries


def file_record(path: Path, root: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "expected a regular build artifact")
    return {"path": path.relative_to(root).as_posix(), "sha256": digest(path),
            "bytes": path.stat().st_size}


def inventory(root: Path) -> dict[str, str]:
    records = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "source snapshot contains a symbolic link")
        if path.is_file():
            records[path.relative_to(root).as_posix()] = digest(path)
    return records


def extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir()
    seen = set()
    with tarfile.open(archive, "r:") as stream:
        for member in stream:
            name = member.name.rstrip("/")
            path = PurePosixPath(name)
            require(name and not path.is_absolute() and ".." not in path.parts and
                    "\\" not in name and path.as_posix() == name and name not in seen,
                    "unsafe or duplicate Git archive member")
            require(member.isfile() or member.isdir(), "non-regular Git archive member")
            seen.add(name)
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                original = stream.extractfile(member)
                require(original is not None, "Git archive member has no content")
                with original, target.open("xb") as output:
                    shutil.copyfileobj(original, output)
                require(target.stat().st_size == member.size, "truncated Git archive member")
                target.chmod(member.mode & 0o777)


class Phase:
    def __init__(self, name: str, output: Path, report: dict):
        self.name = name
        self.output = output
        self.report = report
        self.started = time.monotonic()

    def remaining(self) -> float:
        remaining = BUILD_BUDGET - (time.monotonic() - self.started)
        require(remaining > 0.0, self.name + " exceeded its frozen 300-second budget")
        return remaining

    def run(self, label: str, arguments: list[str], cwd: Path) -> bytes:
        remaining = self.remaining()
        prefix = self.output / "logs" / (self.name + "-" + label)
        stdout = prefix.with_suffix(".stdout.txt")
        stderr = prefix.with_suffix(".stderr.txt")
        record = {"phase": self.name, "step": label, "command": arguments,
                  "cwd": str(cwd), "timeout_seconds": remaining,
                  "stdout": stdout.relative_to(self.output).as_posix(),
                  "stderr": stderr.relative_to(self.output).as_posix()}
        started = time.monotonic()
        timed_out = False
        with stdout.open("xb") as out, stderr.open("xb") as err:
            process = subprocess.Popen(arguments, cwd=cwd, stdout=out, stderr=err,
                                       start_new_session=True)
            try:
                code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                code = process.wait()
        record.update({"returncode": code, "timed_out": timed_out,
                       "elapsed_seconds": time.monotonic() - started,
                       "stdout_sha256": digest(stdout), "stderr_sha256": digest(stderr)})
        self.report["commands"].append(record)
        json_write(self.output / "build-manifest.json", self.report)
        require(not timed_out and code == 0, self.name + ": " + label + " failed")
        self.remaining()
        return stdout.read_bytes()


def flags_from_build(build: Path) -> dict[str, list[str]]:
    values = {}
    path = build / "CMakeFiles/audio_pipeline.dir/flags.make"
    for name in ("C_DEFINES", "C_INCLUDES", "C_FLAGS"):
        lines = [line.split("=", 1)[1].strip() for line in path.read_text().splitlines()
                 if line.startswith(name + " =")]
        require(len(lines) == 1, "missing or duplicated actual compiler flags")
        values[name] = shlex.split(lines[0])
    definitions = values["C_DEFINES"]
    require(definitions and all(re.fullmatch(r"-DAP_BUILD_[A-Z0-9_]+=[0-9]+", item)
                                for item in definitions), "unexpected library ABI definitions")
    required = {"-DAP_BUILD_STAGE_HPF=1", "-DAP_BUILD_STAGE_BF=1", "-DAP_BUILD_STAGE_SYNC=1",
                "-DAP_BUILD_BF_DIRECTION_TRACKING=1", "-DAP_BUILD_ACTIVITY=1",
                "-DAP_BUILD_STAGE_AEC=1", "-DAP_BUILD_STAGE_RES=1",
                "-DAP_BUILD_STAGE_NS=1", "-DAP_BUILD_STAGE_AGC=1", "-DAP_BUILD_AEC_MDF=1",
                "-DAP_BUILD_STAGE_VAD=1", "-DAP_BUILD_NS_EMA=1", "-DAP_BUILD_RESAMPLER_BANDLIMITED=1"}
    require(required.issubset(definitions), "observer requires the frozen full scalar MDF/EMA build")
    require("-ffast-math" not in values["C_FLAGS"] and "-Werror" in values["C_FLAGS"],
            "unexpected fast math or relaxed warnings")
    return values


def configure(phase: Phase, source: Path, build: Path, revision: str,
              compiler: Path, cmake: Path) -> None:
    phase.run("configure", [str(cmake), "-S", str(source), "-B", str(build),
        "-G", "Unix Makefiles", "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_C_COMPILER=" + str(compiler), "-DCMAKE_C_FLAGS=",
        "-DCMAKE_C_FLAGS_RELEASE=-O3 -DNDEBUG", "-DAP_BUILD_PIPELINE=ON",
        "-DAP_BUILD_TESTS=OFF", "-DAP_BUILD_BENCH=OFF", "-DAP_BUILD_EXAMPLES=ON",
        "-DAP_BUILD_ALSA_EXAMPLE=OFF", "-DAP_BUILD_FUZZ=OFF", "-DAP_STRICT_WARNINGS=ON",
        "-DAP_ENABLE_FAST_MATH=OFF", "-DAP_AEC_BACKEND=MDF", "-DAP_NS_ESTIMATOR=EMA",
        "-DAP_SIMD_BACKEND=SCALAR", "-DAP_RESAMPLER_MODE=BANDLIMITED",
        "-DAP_BUILD_SOURCE_REVISION=" + revision], phase.output)


def build_record(source: Path, build: Path, revision: str, compiler: Path,
                 output: Path, flags: dict, elapsed: float) -> dict:
    return {"source_revision": revision, "source_dir": source.relative_to(output).as_posix(),
            "build_dir": build.relative_to(output).as_posix(), "elapsed_seconds": elapsed,
            "budget_seconds": BUILD_BUDGET, "definitions": flags["C_DEFINES"],
            "flags": flags["C_FLAGS"], "includes": flags["C_INCLUDES"],
            "compiler": {"path": str(compiler), "sha256": digest(compiler),
                         "bytes": compiler.stat().st_size},
            "library": file_record(build / "libaudio_pipeline.a", output),
            "generated_header": file_record(build / "generated/audio_pipeline/audio_pipeline_build.h", output),
            "flags_make": file_record(build / "CMakeFiles/audio_pipeline.dir/flags.make", output)}


def transform(source: Path, original: dict[str, str]) -> list[dict]:
    records = []
    for name, (result_type, function) in RENAMES.items():
        path = source / name
        data = path.read_bytes()
        needle = (result_type + " " + function + "(").encode("ascii")
        replacement = (result_type + " " + function + "_d1_real(").encode("ascii")
        require(data.count(needle) == 1 and replacement not in data,
                "observer transform requires exactly one original function definition")
        changed = data.replace(needle, replacement, 1)
        require(changed.replace(replacement, needle, 1) == data, "non-invertible definition rename")
        path.write_bytes(changed)
        records.append({"path": name, "definition": needle.decode(),
                        "renamed_definition": replacement.decode(),
                        "before_sha256": original[name], "after_sha256": digest(path),
                        "inverse_sha256": hashlib.sha256(changed.replace(replacement, needle, 1)).hexdigest()})
    return records


def check_transform(original_root: Path, observer_root: Path,
                    original: dict[str, str], transforms: list[dict]) -> dict[str, str]:
    require(inventory(original_root) == original, "plain source changed during build")
    measured = inventory(observer_root)
    require(set(measured) == set(original), "observer source file set changed")
    require({name for name in original if measured[name] != original[name]} == set(RENAMES),
            "observer changed more than the five declared definitions")
    for row in transforms:
        data = (observer_root / row["path"]).read_bytes()
        before = row["definition"].encode("ascii")
        after = row["renamed_definition"].encode("ascii")
        require(data.count(after) == 1 and before not in data, "transformed definition drift")
        restored = data.replace(after, before, 1)
        require(restored == (original_root / row["path"]).read_bytes() and
                hashlib.sha256(restored).hexdigest() == row["inverse_sha256"] == row["before_sha256"] and
                measured[row["path"]] == row["after_sha256"], "inverse source proof failed")
    return measured


def build(source: Path, revision: str, output: Path) -> dict:
    require(bool(SHA.fullmatch(revision)), "--source-revision must be exactly 40 lowercase hex digits")
    source = source.resolve(strict=True)
    require(source.is_dir(), "source checkout is not a directory")
    require(not output.exists() and not output.is_symlink(), "output must be a new, absent directory")
    output = output.absolute()
    require(source != output.resolve() and source not in output.resolve().parents,
            "build output must be outside the source checkout")
    source_tree = clean_head(source, revision)
    require(git(source, "rev-parse", BASE_SHA + "^{tree}").decode().strip() == BASE_TREE,
            "frozen base tree identity differs")
    original_production = production_entries(source, BASE_SHA)
    production = production_entries(source, revision)
    require(production == original_production, "production source differs from frozen base 4daa7e2")
    require(Path(__file__).resolve() == source / BUILDER,
            "run the builder belonging to the exact checked-out source")
    compiler_name, cmake_name = shutil.which("cc"), shutil.which("cmake")
    require(bool(compiler_name and cmake_name), "C compiler and CMake are required")
    compiler, cmake = Path(compiler_name).resolve(strict=True), Path(cmake_name).resolve(strict=True)
    output.mkdir(parents=True)
    (output / "logs").mkdir()
    report = {"schema_version": 1, "experiment": EXPERIMENT, "status": "BUILDING",
              "source_revision": revision, "source_tree": source_tree,
              "base_sha": BASE_SHA, "base_tree": BASE_TREE,
              "production_source_unchanged": True, "source_files": {}, "production_files": {},
              "transforms": [], "builds": {}, "programs": {}, "commands": []}
    json_write(output / "build-manifest.json", report)
    try:
        plain_source, observer_source = output / "baseline-source", output / "observer-source"
        plain_build, observer_build = output / "baseline-build", output / "observer-build"
        plain = Phase("plain", output, report)
        archive = output / "exact-source.tar"
        plain.run("archive", ["git", "-C", str(source), "archive", "--format=tar",
                              "--output=" + str(archive), revision], source)
        extract_archive(archive, plain_source)
        original = inventory(plain_source)
        require(original[BUILDER] == digest(Path(__file__)) and
                original[OBSERVER] == digest(source / OBSERVER), "builder/observer source is not the archived revision")
        report["source_files"] = original
        report["production_files"] = {name: {**record, "sha256": original[name]}
                                      for name, record in production.items()}
        report["source_archive"] = file_record(archive, output)
        configure(plain, plain_source, plain_build, revision, compiler, cmake)
        plain.run("compile", [str(cmake), "--build", str(plain_build), "--target",
                              "ap_process_pcm", "ap_build_info_dump", "--parallel", "2"], output)
        plain_flags = flags_from_build(plain_build)
        info_lines = plain.run("build-info", [str(plain_build / "ap_build_info_dump")], output).decode().splitlines()
        require(all("=" in line for line in info_lines), "malformed actual build-info output")
        info = dict(line.split("=", 1) for line in info_lines)
        require(len(info) == len(info_lines) and info.get("source_revision") == revision and
                info.get("version") == "2.3.63" and info.get("module_mask") == "1023" and
                info.get("aec_backend") == "MDF" and info.get("ns_estimator") == "EMA" and
                info.get("simd_backend") == "SCALAR" and info.get("fast_math") == "0" and
                info.get("resampler_mode") == "BANDLIMITED" and info.get("build_type") == "Release",
                "plain build identity differs from the frozen production configuration")
        report["builds"]["plain"] = build_record(plain_source, plain_build, revision, compiler,
                                               output, plain_flags, time.monotonic() - plain.started)
        report["builds"]["plain"]["build_info"] = info
        report["programs"]["plain_cli"] = file_record(plain_build / "ap_process_pcm", output)
        report["programs"]["plain_build_info"] = file_record(plain_build / "ap_build_info_dump", output)
        report["builds"]["plain"]["elapsed_seconds"] = time.monotonic() - plain.started
        report["builds"]["plain"]["elapsed_scope"] = "through hash bookkeeping; final manifest write also deadline checked"
        json_write(output / "build-manifest.json", report)
        plain.remaining()
        measured = Phase("observer", output, report)
        shutil.copytree(plain_source, observer_source)
        report["transforms"] = transform(observer_source, original)
        observer_revision = revision + "-D1-observer"
        configure(measured, observer_source, observer_build, observer_revision, compiler, cmake)
        measured.run("compile-library", [str(cmake), "--build", str(observer_build), "--target",
                                         "audio_pipeline", "--parallel", "2"], output)
        observer_flags = flags_from_build(observer_build)
        require(plain_flags["C_DEFINES"] == observer_flags["C_DEFINES"] and
                plain_flags["C_FLAGS"] == observer_flags["C_FLAGS"], "plain/observer compiler ABI or flags differ")
        plain_header = (plain_build / "generated/audio_pipeline/audio_pipeline_build.h").read_bytes()
        observer_header = (observer_build / "generated/audio_pipeline/audio_pipeline_build.h").read_bytes()
        require(observer_header.count(observer_revision.encode()) == 1 and
                observer_header.replace(observer_revision.encode(), revision.encode(), 1) == plain_header,
                "generated headers differ beyond the disclosed measurement identity")
        measured.run("compile-observer", [str(compiler), *observer_flags["C_DEFINES"],
            *observer_flags["C_INCLUDES"], *observer_flags["C_FLAGS"],
            str(observer_source / OBSERVER), str(observer_build / "libaudio_pipeline.a"),
            "-lm", "-o", str(observer_build / "ap_process_pcm_observer")], output)
        report["observer_source_files"] = check_transform(plain_source, observer_source, original,
                                                          report["transforms"])
        report["builds"]["observer"] = build_record(observer_source, observer_build, observer_revision,
            compiler, output, observer_flags, time.monotonic() - measured.started)
        report["programs"]["observer_cli"] = file_record(observer_build / "ap_process_pcm_observer", output)
        require(clean_head(source, revision) == source_tree, "checkout moved during build")
        require(digest(source / BUILDER) == original[BUILDER] and
                digest(source / OBSERVER) == original[OBSERVER], "measurement implementation changed during build")
        proof_paths = {archive, *(output / row["path"] for row in report["programs"].values())}
        for details in report["builds"].values():
            for name in ("library", "generated_header", "flags_make"):
                proof_paths.add(output / details[name]["path"])
        for command in report["commands"]:
            proof_paths.update((output / command["stdout"], output / command["stderr"]))
        proof_paths.update(observer_source / name for name in (*RENAMES, OBSERVER))
        report["proof_files"] = {path.relative_to(output).as_posix(): file_record(path, output)
                                 for path in sorted(proof_paths)}
        report["status"] = "BUILT"
        report["audio_or_model_executed"] = False
        report["measurement_copy_is_clean_git_source"] = False
        report["builds"]["observer"]["elapsed_seconds"] = time.monotonic() - measured.started
        report["builds"]["observer"]["elapsed_scope"] = "through source, HEAD and proof hashes; final manifest write also deadline checked"
        json_write(output / "build-manifest.json", report)
        # Include all hash/readback/bookkeeping and the actual final write in the
        # frozen phase budget. The exception path overwrites BUILT with failure.
        measured.remaining()
        return report
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        report["status"] = "BUILD_FAILED"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        json_write(output / "build-manifest.json", report)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        result = build(arguments.source, arguments.source_revision, arguments.output)
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "source_revision": result["source_revision"],
                      "manifest": str(arguments.output.absolute() / "build-manifest.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
