#!/usr/bin/env python3
"""A3-R2-T1 object-only builder negatives. Generic compiler fixtures, no A3 execution."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

SYNTH_HEADER = (b'#define AP_VERSION_STRING "2.3.61"\n'
                b'#define AP_BUILD_MAX_MIC_CHANNELS 2\n'
                b'#define AP_HAVE_PIPELINE 1\n'
                b'#define AP_BUILD_FAST_MATH 0\n')

MODULE = Path(__file__).with_name("fe09_a3_r2_static_build.py")
SPEC = importlib.util.spec_from_file_location("a3_r2_static", MODULE)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def elf(mode):
    out = bytearray(64)
    out[:7] = b"\x7fELF" + bytes((1 if mode == "arm32" else 2, 1, 1))
    struct.pack_into("<HH", out, 16, 1, 40 if mode == "arm32" else 62)
    return bytes(out)


def offline_t0_source():
    return {"status": M.STATUS, "current_tree_is_original_tree": False}


class StaticBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "out"

    def test_four_modes_eight_objects(self):
        self.assertEqual(len(M.MODES), 4)
        self.assertEqual(len(M.C_UNITS) * len(M.MODES), 8)
        self.assertEqual(set(M.MODES),
                         {"native-gcc", "native-clang", "sanitized", "arm32"})

    def test_compile_only_never_links_or_runs(self):
        for mode in M.MODES:
            cmd = M.command("/usr/bin/compiler", mode,
                            self.root / "fe09_a3_f0_live_roll.c",
                            self.root / "unit.o")
            self.assertIn("-c", cmd)
            self.assertIn("-o", cmd)
            self.assertEqual(cmd[cmd.index("-I") + 1], str(M.ROOT / "src"))
            self.assertIn(str(M.ROOT / "include"), cmd)
            self.assertIn(str(self.root / "sdk_config" / "generated"), cmd)
            self.assertNotIn("-shared", cmd)
            self.assertNotIn("-run", cmd)
            self.assertNotIn("-flto", cmd)
            for flag in ("-std=c11", "-O2", "-fno-lto", "-fstack-usage",
                         "-fno-fast-math", "-ffp-contract=off", "-Wall", "-Werror"):
                self.assertIn(flag, cmd)

    def test_real_cmake_configuration_never_runs_generated_targets(self):
        for mode in M.MODES:
            cmd = M.cmake_configuration("/usr/bin/cmake", "/usr/bin/gcc",
                                        mode, M.ROOT, self.root / "sdk_config")
            self.assertIn("-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY", cmd)
            self.assertIn("-DAP_BUILD_MAX_MIC_CHANNELS=2", cmd)
            self.assertIn("-DAP_BUILD_TESTS=OFF", cmd)
            self.assertNotIn("--build", cmd)
            self.assertNotIn("ctest", " ".join(cmd))
            self.assertEqual("-DCMAKE_SYSTEM_NAME=Linux" in cmd, mode == "arm32")

    def test_real_generated_header_required_not_synthetic_promotion(self):
        self.assertEqual(M.generated_config(SYNTH_HEADER)["bytes"], len(SYNTH_HEADER))
        for invalid in (b"", SYNTH_HEADER.replace(b"MIC_CHANNELS 2", b"MIC_CHANNELS 4"),
                        SYNTH_HEADER.replace(b"FAST_MATH 0", b"FAST_MATH 1"),
                        SYNTH_HEADER + b"@PROJECT_VERSION@"):
            with self.assertRaisesRegex(M.Rejected, "A3_REAL_CMAKE_BUILD_HEADER_REQUIRED"):
                M.generated_config(invalid)

    def test_modes_distinguish_sanitizers_and_arm32(self):
        for mode in M.MODES:
            cmd = M.command("/usr/bin/cc", mode,
                            self.root / "fe09_a3_f0_original_validator.c",
                            self.root / "x.o")
            self.assertEqual("-fsanitize=address,undefined" in cmd,
                             mode == "sanitized")
            self.assertEqual("-mcpu=cortex-a32" in cmd, mode == "arm32")
            self.assertEqual("-mfloat-abi=hard" in cmd, mode == "arm32")
            self.assertEqual("-fno-omit-frame-pointer" in cmd, mode == "sanitized")

    def test_unregistered_mode_or_translation_unit_rejected(self):
        for mode, name, output in (
            ("native", "fe09_a3_f0_live_roll.c", "t.o"),
            ("native-gcc", "untrusted.c", "t.o"),
            ("native-gcc", "fe09_a3_f0_live_roll.c", "t.exe")
        ):
            with self.assertRaisesRegex(M.Rejected, "A3_COMPILE_SCOPE_REJECT"):
                M.command("cc", mode, self.root / name, self.root / output)

    def test_real_elf_object_header_positive_for_each_mode(self):
        for mode in M.MODES:
            report = M.object_info(elf(mode), mode)
            self.assertEqual(report["elf_type"], 1)
            self.assertEqual(report["bytes"], 64)
            self.assertEqual(report["elf_machine"], 40 if mode == "arm32" else 62)

    def test_elf_executable_or_different_architecture_rejected(self):
        for mode in M.MODES:
            for offset, value in ((16, 2), (18, 0), (4, 3), (5, 2)):
                wrong = bytearray(elf(mode))
                wrong[offset] = value
                with self.subTest(mode=mode, offset=offset), self.assertRaises(M.Rejected):
                    M.object_info(bytes(wrong), mode)

    def test_elf_truncated_oversized_and_random_rejected(self):
        for raw in (b"", b"no ELF", elf("native-gcc")[:63],
                    elf("native-gcc") + (b"a" * M.MAX_OBJECT)):
            with self.assertRaises(M.Rejected):
                M.object_info(raw, "native-gcc")

    def test_no_target_or_scientific_permission_is_returned(self):
        self.assertIn("NO_EXECUTION", M.STATUS)
        self.assertFalse(any(M.DENIALS.values()))

    def test_pinned_module_rejects_untrusted_bytes_before_compile(self):
        path = self.root / M.T0
        path.parent.mkdir(parents=True)
        path.write_text("raise RuntimeError('do not execute untrusted source')\n")
        with self.assertRaisesRegex(M.Rejected, "A3_PROTECTED_HELPER_DRIFT"):
            M.pin_module(self.root, M.T0, M.T0_BLOB)

    def test_pinned_module_rejects_symlink(self):
        path = self.root / M.T0
        path.parent.mkdir(parents=True)
        (self.root / "real").write_bytes(b"file")
        path.symlink_to(self.root / "real")
        with self.assertRaisesRegex(M.Rejected, "A3_PIN_NOT_REGULAR"):
            M.pin_module(self.root, M.T0, M.T0_BLOB)

    def mock_source(self):
        contents = {path: (path + "\n").encode() for path in M.ARCHIVE_FILES}
        blobs = {path: M.sha256(raw) for path, raw in contents.items()}
        source_ids = {path: M.hashlib.sha1(b"blob " +
                       str(len(raw)).encode() + b"\0" + raw).hexdigest()
                      for path, raw in contents.items()}
        tree = {path: ("100644", source_ids[path]) for path in contents}
        for path, raw in contents.items():
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(raw)
        def reader(root):
            return SimpleNamespace(tree=lambda ref: tree,
                                   blob=lambda oid, cap: next(
                                       raw for path, raw in contents.items()
                                       if source_ids[path] == oid))
        proof = {"status": "offline-t0", "source_only": True,
                 "a3_target_executed": False,
                 "execution_commit": "a" * 40, "execution_tree": "b" * 40,
                 "source_comparison": {"original_88_checked": 88,
                     "registered_88_equal_current": True,
                     "current_tree_is_original_tree": False}}
        t0 = SimpleNamespace(STATUS="offline-t0", DENIALS={"a3_target_executed": False},
                             execute=lambda root: proof, GitReader=reader, MAX_FILE=1048576)
        runner = SimpleNamespace(read_file=lambda path, cap: path.read_bytes(),
                                 blob=lambda raw: M.hashlib.sha1(b"blob " +
                                      str(len(raw)).encode() + b"\0" + raw).hexdigest())
        return t0, runner, source_ids, contents

    def test_actual_archive_source_content_positive(self):
        t0, runner, ids, contents = self.mock_source()
        with mock.patch.object(M, "ARCHIVE_FILES", ids):
            report = M.source_proof(self.root, t0, runner)
        self.assertEqual(len(report["original_a3_members"]), 3)
        self.assertEqual(report["original_88_checked"], 88)
        self.assertFalse(report["current_tree_is_original_tree"])

    def test_archive_source_tree_identity_mismatch_rejected(self):
        t0, runner, ids, contents = self.mock_source()
        bad = dict(ids)
        bad[next(iter(bad))] = "f" * 40
        with mock.patch.object(M, "ARCHIVE_FILES", bad), self.assertRaisesRegex(
                M.Rejected, "A3_ORIGINAL_OBJECT_SOURCE_DRIFT"):
            M.source_proof(self.root, t0, runner)

    def test_worktree_source_changed_rejected(self):
        t0, runner, ids, contents = self.mock_source()
        path = self.root / next(iter(contents))
        path.write_bytes(b"modified source\n")
        with mock.patch.object(M, "ARCHIVE_FILES", ids), self.assertRaisesRegex(
                M.Rejected, "A3_ARCHIVE_AND_WORKTREE_BYTES_DRIFT"):
            M.source_proof(self.root, t0, runner)

    def test_original_88_source_proof_required(self):
        t0, runner, ids, contents = self.mock_source()
        bad = t0.execute(self.root)
        bad["source_comparison"]["registered_88_equal_current"] = False
        with mock.patch.object(M, "ARCHIVE_FILES", ids), self.assertRaisesRegex(
                M.Rejected, "A3_T0_SOURCE_AUDIT_REQUIRED"):
            M.source_proof(self.root, t0, runner)

    def test_compile_failure_receipt_stays_denied(self):
        runner = SimpleNamespace(
            reserve_output=lambda root, out: (out.mkdir() or out),
            environment=lambda: {"PATH": "/usr/bin:/bin"},
            read_file=lambda path, cap=None: b"synthetic tool",
            save=lambda path, raw: path.write_bytes(raw),
            encoded=lambda val: (json.dumps(val, sort_keys=True)+"\n").encode())
        with mock.patch.object(M, "pin_module", side_effect=[object(), runner]), mock.patch.object(
                M, "source_proof", return_value=offline_t0_source()), mock.patch.object(
                M.shutil, "which", return_value=None):
            with self.assertRaisesRegex(M.Rejected, "A3_REQUIRED_PINNED_COMPILER_MISSING"):
                M.build_only(self.root, self.out)
        report = json.loads((self.out / "receipt.json").read_text())
        self.assertEqual(report["status"], "A3_R2_T1_STATIC_BUILD_REJECTED")
        self.assertEqual(report["a3_generated_executions"], 0)
        self.assertFalse(any(report[key] for key in M.DENIALS))

    def test_cli_rejects_without_promoting_any_authority(self):
        stderr = io.StringIO()
        with mock.patch.object(M, "build_only", side_effect=M.Rejected("A3_MISSING_SOURCE")), \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(M.main(["--output", str(self.out)]), 2)
        rejected = json.loads(stderr.getvalue())
        self.assertEqual(rejected["a3_generated_executions"], 0)
        self.assertFalse(any(rejected[key] for key in M.DENIALS))

    def test_fake_full_pipeline_records_eight_not_executed_objects(self):
        t0 = object()
        modes = {}
        dummy = SimpleNamespace()
        dummy.environment = lambda: {"PATH": "/usr/bin:/bin"}
        dummy.reserve_output = lambda root, out: (out.mkdir() or out)
        dummy.read_file = lambda path, cap=None: (
            path.read_bytes() if path.suffix in (".o", ".h") else b"synthetic-compiler")
        dummy.run_tool = lambda argv, root, logfile, deadline: fake_tool(argv, logfile)
        dummy.save = lambda path, raw: path.write_bytes(raw)
        dummy.encoded = lambda x: (json.dumps(x, sort_keys=True) + "\n").encode()
        def fake_tool(argv, logfile):
            if "-S" in argv and "-B" in argv:
                config = Path(argv[argv.index("-B") + 1])
                header = config / "generated" / "audio_pipeline" / "audio_pipeline_build.h"
                header.parent.mkdir(parents=True)
                header.write_bytes(SYNTH_HEADER)
            elif "-c" in argv:
                out = Path(argv[-1])
                out.write_bytes(elf(out.parent.name))
                modes.setdefault(out.parent.name, []).append(out.name)
            logfile.write_bytes(b"synthetic tool stdout\n")
            return b"synthetic tool stdout\n"
        proof = offline_t0_source()
        with mock.patch.object(M, "pin_module", side_effect=[t0, dummy]), mock.patch.object(
                M, "source_proof", side_effect=[proof, proof]), mock.patch.object(
                M.shutil, "which", return_value=sys.executable):
            report = M.build_only(self.root, self.out)
        self.assertEqual(report["status"], M.STATUS)
        self.assertEqual(sum(map(len, modes.values())), 8)
        self.assertEqual(set(modes), set(M.MODES))
        self.assertEqual(report["a3_generated_executions"], 0)
        self.assertFalse(any(report[k] for k in M.DENIALS))
        self.assertEqual(len(report["compilers"]), 4)
        self.assertEqual(len(report["configured_headers"]), 4)
        self.assertEqual(len(report["modes"]), 4)
        self.assertTrue((self.out / "receipt.json.sha256").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
