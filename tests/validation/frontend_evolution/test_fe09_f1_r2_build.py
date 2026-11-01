#!/usr/bin/env python3
"""Offline T1 controls; no archived/generated F1 process is executed."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).with_name("fe09_f1_r2_build.py")
SPEC = importlib.util.spec_from_file_location("f1_r2_build", MODULE_PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def elf(mode):
    raw = bytearray(64)
    raw[:7] = b"\x7fELF" + bytes((1 if mode == "arm32" else 2, 1, 1))
    struct.pack_into("<HH", raw, 16, 3, 40 if mode == "arm32" else 62)
    return bytes(raw)


def database(root, build, mode):
    rows = []
    for target in M.targets(mode):
        names = (["fe09_t3s3_f1_rss_" + target.rsplit("_", 1)[1] + ".c"] if target in M.HELPERS else
                 [*M.COMMON, "fe09_b3_f0_composition_test.c" if target == M.PLAIN else "fe09_t3s3_f0_call_resource_probe.c"])
        for name in names:
            flags = " -ffp-contract=off -fno-fast-math -fno-lto -fstack-usage -Wall -Wextra -Wpedantic -Werror"
            if mode == "sanitized":
                flags += " -fsanitize=address,undefined"
            rows.append({"file": str(root / M.REL / name), "directory": str(build),
                         "command": "/usr/bin/gcc" + flags + " -o CMakeFiles/" + target + ".dir/" + name + ".o -c source.c"})
    return rows


class BuildContractTests(unittest.TestCase):
    def setUp(self):
        self.root, self.build = Path("/trusted/source"), Path("/trusted/build")

    def audit(self, rows, mode="native"):
        return M.audit_commands(json.dumps(rows).encode(), self.root, self.build, mode)

    def test_three_modes_have_eight_images(self):
        self.assertEqual(sum(len(M.targets(m)) for m in ("native", "sanitized", "arm32")), 8)
        for mode in ("native", "sanitized", "arm32"):
            result = self.audit(database(self.root, self.build, mode), mode)
            self.assertEqual(len(result[M.PLAIN]), 8)
            self.assertEqual(len(result[M.PROBE]), 8)

    def test_unknown_mode_rejected(self):
        for value in ("qemu", "release", "", None):
            with self.assertRaises(M.Rejected):
                M.targets(value)

    def test_configure_does_not_schedule_target_execution(self):
        for mode in ("native", "sanitized", "arm32"):
            argv = M.configure(self.root, self.build, mode, "/usr/bin/cmake", "/usr/bin/gcc")
            self.assertIn("-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY", argv)
            self.assertNotIn("ctest", " ".join(argv))
            self.assertNotIn("qemu", " ".join(argv))
            self.assertEqual("-DCMAKE_SYSTEM_NAME=Linux" in argv, mode == "arm32")
            self.assertEqual("-DB3_F0_SANITIZE=ON" in argv, mode == "sanitized")

    def test_each_compile_flag_is_required(self):
        for flag in ("-ffp-contract=off", "-fno-fast-math", "-fno-lto", "-fstack-usage", "-Wall", "-Wextra", "-Wpedantic", "-Werror"):
            rows = database(self.root, self.build, "native")
            rows[0]["command"] = rows[0]["command"].replace(flag, "")
            with self.subTest(flag=flag), self.assertRaises(M.Rejected):
                self.audit(rows)

    def test_fastmath_or_lto_rejected(self):
        for flag in ("-ffast-math", "-flto", "-flto=auto"):
            rows = database(self.root, self.build, "native")
            rows[0]["command"] += " " + flag
            with self.assertRaises(M.Rejected):
                self.audit(rows)

    def test_sanitizer_missing_or_extra_rejected(self):
        for mode in ("native", "sanitized", "arm32"):
            rows = database(self.root, self.build, mode)
            if mode == "sanitized":
                rows[0]["command"] = rows[0]["command"].replace(" -fsanitize=address,undefined", "")
            else:
                rows[0]["command"] += " -fsanitize=address,undefined"
            with self.assertRaises(M.Rejected):
                self.audit(rows, mode)

    def test_each_translation_unit_is_required(self):
        base = database(self.root, self.build, "native")
        for index in range(len(base)):
            with self.subTest(index=index), self.assertRaises(M.Rejected):
                self.audit(base[:index] + base[index+1:])

    def test_duplicate_translation_unit_rejected(self):
        rows = database(self.root, self.build, "native")
        with self.assertRaises(M.Rejected):
            self.audit(rows + [rows[0]])

    def test_changed_translation_unit_rejected(self):
        rows = database(self.root, self.build, "native")
        rows[0]["file"] = str(self.root / "other.c")
        with self.assertRaises(M.Rejected):
            self.audit(rows)

    def test_external_source_and_build_directory_rejected(self):
        for key, value in (("file", "/other/source.c"), ("directory", "/other/build")):
            rows = database(self.root, self.build, "native")
            rows[0][key] = value
            with self.assertRaises(M.Rejected):
                self.audit(rows)

    def test_helper_in_sanitizer_or_arm_rejected(self):
        for mode in ("sanitized", "arm32"):
            rows = database(self.root, self.build, mode)
            rows += database(self.root, self.build, "native")[-1:]
            with self.assertRaises(M.Rejected):
                self.audit(rows, mode)

    def test_compile_database_shape_and_duplicate_key(self):
        for raw in (b"[]", b"{}", b'[{}]', b'[{"command":"a","command":"b"}]'):
            with self.assertRaises((M.Rejected, KeyError)):
                M.audit_commands(raw, self.root, self.build, "native")

    def test_compile_output_required(self):
        for command in ("gcc -c x.c", "gcc -o", "gcc -o a -o b"):
            with self.assertRaises(M.Rejected):
                self.audit([{ "command": command}])

    def test_elf_class_machine_and_endian(self):
        for mode in ("native", "sanitized", "arm32"):
            result = M.elf_header(elf(mode), mode)
            self.assertEqual(result["bytes"], 64)
            for offset in (0, 4, 5, 6, 16, 18):
                changed = bytearray(elf(mode)); changed[offset] = 255
                with self.subTest(mode=mode, offset=offset), self.assertRaises(M.Rejected):
                    M.elf_header(bytes(changed), mode)

    def test_truncated_elf_rejected(self):
        for size in (0, 4, 20, 63):
            with self.assertRaises(M.Rejected):
                M.elf_header(elf("native")[:size], "native")

    def test_wrapped_and_unwrapped_symbols(self):
        M.verify_symbols(b"0000 T main\n0001 T __wrap_main\n", True)
        M.verify_symbols(b"0000 T main\n", False)
        for raw, wrapped in ((b"0000 T main\n", True), (b"0001 T __wrap_main\n", True),
                             (b"0000 T main\n0001 T __wrap_main\n", False)):
            with self.assertRaises(M.Rejected):
                M.verify_symbols(raw, wrapped)

    def test_no_environment_credentials_or_compiler_overrides(self):
        with mock.patch.dict(os.environ, {"GH_TOKEN":"private", "CFLAGS":"bad", "LD_PRELOAD":"bad", "CC":"bad"}):
            env = M.environment()
        self.assertEqual(set(env), {"PATH", "HOME", "LC_ALL", "TZ"})
        self.assertNotIn("private", repr(env))


class FileAndToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_changed_bridge_refused_before_execution(self):
        path = self.root / M.BRIDGE; path.parent.mkdir(parents=True)
        path.write_text('raise RuntimeError("untrusted")\n')
        with self.assertRaisesRegex(M.Rejected, "PROTECTED_T0_DRIFT"):
            M.source_check(self.root)

    def test_fresh_private_directory_only(self):
        source = self.root / "source"; source.mkdir()
        path = M.reserve_output(source, self.root / "output")
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        for value in (path, source / "nested", Path("relative")):
            with self.assertRaises((M.Rejected, FileExistsError)):
                M.reserve_output(source, value)

    def test_existing_output_symlink_not_reused(self):
        source = self.root / "source"; source.mkdir()
        link = self.root / "link"; link.symlink_to(source, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            M.reserve_output(source, link)

    def test_read_regular_nonempty_bounded(self):
        path = self.root / "file"; path.write_bytes(b"abc")
        self.assertEqual(M.read_file(path, 3), b"abc")
        with self.assertRaises(M.Rejected): M.read_file(path, 2)
        path.write_bytes(b"")
        with self.assertRaises(M.Rejected): M.read_file(path)
        path.unlink(); path.symlink_to("missing")
        with self.assertRaises(M.Rejected): M.read_file(path)

    def test_evidence_never_overwritten(self):
        path = self.root / "file"; M.save(path, b"original")
        with self.assertRaises(FileExistsError): M.save(path, b"new")
        self.assertEqual(path.read_bytes(), b"original")

    def test_evidence_short_write_and_close_error(self):
        for failure in ("short", "close"):
            stream = mock.MagicMock()
            stream.__enter__.return_value = stream
            stream.write.return_value = 2 if failure == "short" else 3
            if failure == "close": stream.__exit__.side_effect = OSError("close")
            with mock.patch.object(Path, "open", return_value=stream), self.assertRaises((M.Rejected, OSError)):
                M.save(self.root / "out", b"abc")

    def test_bounded_real_tool_log(self):
        raw = M.run_tool([sys.executable, "-c", "print('offline child, not F1')"], self.root,
                         self.root / "tool.log", time.monotonic() + 5)
        self.assertEqual(raw, b"offline child, not F1\n")
        self.assertEqual((self.root / "tool.log").read_bytes(), raw)

    def test_nonzero_tool_retains_log(self):
        with self.assertRaisesRegex(M.Rejected, "BUILD_TOOL_FAILED"):
            M.run_tool([sys.executable, "-c", "print('retained');raise SystemExit(7)"], self.root,
                       self.root / "tool.log", time.monotonic() + 5)
        self.assertEqual((self.root / "tool.log").read_bytes(), b"retained\n")

    def test_tool_log_cap_is_fail_visible(self):
        with mock.patch.object(M, "MAX_LOG", 8), self.assertRaisesRegex(M.Rejected, "BUILD_LOG_BOUND"):
            M.run_tool([sys.executable, "-c", "print('x'*100)"], self.root,
                       self.root / "tool.log", time.monotonic() + 5)
        self.assertLessEqual((self.root / "tool.log").stat().st_size, 8)

    def test_expired_deadline_makes_no_process(self):
        with mock.patch.object(M.subprocess, "Popen") as create, self.assertRaises(M.Rejected):
            M.run_tool(["unused"], self.root, self.root / "tool.log", time.monotonic())
        create.assert_not_called()

    def test_stalled_child_killed_with_original_deadline(self):
        start = time.monotonic()
        with self.assertRaisesRegex(M.Rejected, "BUILD_TOOL_TIMEOUT"):
            M.run_tool([sys.executable, "-c", "import time;time.sleep(60)"], self.root,
                       self.root / "tool.log", start + .7)
        self.assertLess(time.monotonic() - start, 1.5)

    def test_bad_source_stops_before_build(self):
        with mock.patch.object(M, "source_check", side_effect=M.Rejected("BAD_SOURCE")), mock.patch.object(M, "run_tool") as tool:
            with self.assertRaises(M.Rejected): M.build_only(self.root, self.root / "out")
        tool.assert_not_called()
        self.assertFalse((self.root / "out").exists())

    def test_missing_tools_preserve_rejected_receipt(self):
        output = self.root / "out"; source = self.root / "source"; source.mkdir()
        with mock.patch.object(M, "source_check", return_value={"commit":"fixture"}), mock.patch.object(M.shutil, "which", return_value=None):
            with self.assertRaises(M.Rejected): M.build_only(source, output)
        report = json.loads((output / "receipt.json").read_bytes())
        self.assertEqual(report["status"], "F1_R2_T1_BUILD_REJECTED")
        self.assertFalse(any(report[k] for k in M.DENIALS))

    def fake_build(self, changed=False):
        source = self.root / "source"; source.mkdir()
        output = self.root / "output"
        calls = []
        def tool(argv, cwd, log, deadline):
            calls.append(list(argv))
            mode = log.name.split(".")[0]
            if "-S" in argv:
                (output / mode).mkdir()
            elif "--build" in argv:
                directory = output / mode
                (directory / "compile_commands.json").write_bytes(json.dumps(database(source, directory, mode)).encode())
                for target in M.targets(mode):
                    path = directory / ("f0/b3/" + target if target == M.PLAIN else target)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(elf(mode))
            raw = b"offline synthetic compiler log\n"
            if "--defined-only" in argv:
                raw = b"0000 T main\n"
                if Path(argv[-1]).name not in M.HELPERS:
                    raw += b"0001 T __wrap_main\n"
            log.write_bytes(raw)
            return raw
        first = {"commit":"offline-a", "tree":"offline-tree"}
        last = {**first, "commit":"offline-b"} if changed else first
        with mock.patch.object(M, "source_check", side_effect=[first, last]), mock.patch.object(
                M.shutil, "which", return_value=sys.executable), mock.patch.object(M, "run_tool", side_effect=tool):
            if changed:
                with self.assertRaisesRegex(M.Rejected, "SOURCE_CHANGED_DURING_BUILD"):
                    M.build_only(source, output)
                report = json.loads((output / "receipt.json").read_bytes())
            else:
                report = M.build_only(source, output)
        self.assertEqual(len(calls), 19)
        self.assertTrue(all(argv[0] == sys.executable for argv in calls))
        self.assertEqual(sum(len(row["images"]) for row in report["modes"].values()), 8)
        self.assertEqual(report["generated_target_executions"], 0)
        self.assertFalse(any(report[key] for key in M.DENIALS))
        return report, output

    def test_complete_orchestration_only_builds_and_inspects(self):
        report, output = self.fake_build()
        self.assertEqual(report["status"], M.STATUS)
        raw = (output / "receipt.json").read_bytes()
        self.assertEqual((output / "receipt.json.sha256").read_text(), M.sha(raw) + "  receipt.json\n")

    def test_post_build_source_change_rejects_even_eight_images(self):
        report, output = self.fake_build(changed=True)
        self.assertEqual(report["status"], "F1_R2_T1_BUILD_REJECTED")
        self.assertFalse((output / "receipt.json.sha256").exists())

    def test_cli_redacts_error_and_has_no_promotion(self):
        with mock.patch.object(M, "build_only", side_effect=OSError("private detail")), contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(M.main(["--output", "/unused"]), 2)
        self.assertNotIn("private", output.getvalue())
        report = json.loads(output.getvalue())
        self.assertEqual(report["generated_target_executions"], 0)
        self.assertFalse(any(report[k] for k in M.DENIALS))


class GroupLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def descendant_result(self, exit_code):
        # Subreaper state is confined to this separate test-driver process.
        # The generic child waits for a file released AFTER run_tool returns,
        # so the regression does not depend on winning a short sleep race.
        driver = r"""
import ctypes, importlib.util, json, os, pathlib, sys, time
spec = importlib.util.spec_from_file_location('tested_build', sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(36, 1, 0, 0, 0) != 0:
    raise OSError(ctypes.get_errno(), 'test-only child-subreaper unavailable')
root = pathlib.Path(sys.argv[2]); status = int(sys.argv[3])
child = __CHILD_SCRIPT__
reason = None
try:
    m.run_tool([sys.executable, '-I', '-S', '-c', child, str(root), str(status)],
               root, root / 'tool.log', time.monotonic() + 3)
except m.Rejected as exc:
    reason = str(exc)
pid = int((root / 'tool.log').read_bytes().splitlines()[-1])
(root / 'release-child').write_text('owner returned')
waited, raw_status = os.waitpid(pid, 0)
print(json.dumps({'reason': reason, 'child_reaped': waited == pid,
                  'child_exit': os.waitstatus_to_exitcode(raw_status),
                  'late_marker': (root / 'late-marker').exists()}))
"""
        child = "\n".join([
            "import os,pathlib,sys,time", "root=pathlib.Path(sys.argv[1])", "pid=os.fork()",
            "if pid:", " print(pid,flush=True)", " os._exit(int(sys.argv[2]))",
            "fd=os.open('/dev/null',os.O_WRONLY)",
            "os.dup2(fd,1);os.dup2(fd,2);os.close(fd)",
            "limit=time.monotonic()+2", "flag=root/'release-child'",
            "while not flag.exists() and time.monotonic()<limit: time.sleep(.001)",
            "if flag.exists(): (root/'late-marker').write_text('descendant survived')",
            "os._exit(0)"])
        driver = driver.replace("__CHILD_SCRIPT__", repr(child))
        result = subprocess.run([sys.executable, '-I', '-S', '-c', driver, str(MODULE_PATH),
                                 str(self.root), str(exit_code)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=M.environment(), timeout=5, check=True)
        return json.loads(result.stdout)

    def test_successful_leader_cannot_leave_active_descendant(self):
        result = self.descendant_result(0)
        self.assertEqual(result, {'reason': None, 'child_reaped': True,
                                  'child_exit': -9, 'late_marker': False})

    def test_nonzero_leader_cannot_leave_active_descendant(self):
        result = self.descendant_result(7)
        self.assertEqual(result, {'reason': 'BUILD_TOOL_FAILED', 'child_reaped': True,
                                  'child_exit': -9, 'late_marker': False})

    def test_closed_pipes_with_running_leader_still_time_out(self):
        with self.assertRaisesRegex(M.Rejected, 'BUILD_TOOL_TIMEOUT'):
            M.run_tool([sys.executable, '-I', '-S', '-c',
                        'import os,time;os.close(1);os.close(2);time.sleep(60)'],
                       self.root, self.root / 'tool.log', time.monotonic() + .8)

    def test_nonconsuming_observation_precedes_group_signal_and_reap(self):
        process = mock.Mock(pid=123, returncode=None)
        events = []
        def observe(*args):
            self.assertEqual(args, (M.os.P_PID, 123, M.os.WEXITED | M.os.WNOHANG | M.os.WNOWAIT))
            events.append('observe'); return mock.Mock(si_pid=123)
        def group(pid, sig):
            self.assertEqual((pid, sig), (123, M.signal.SIGKILL))
            self.assertIsNone(process.returncode); events.append('group-signal')
        def wait(*, timeout):
            events.append('reap'); process.returncode = 0; return 0
        process.wait.side_effect = wait
        with mock.patch.object(M.os, 'waitid', side_effect=observe), mock.patch.object(
                M.os, 'getpgid', return_value=123), mock.patch.object(M.os, 'killpg', side_effect=group):
            self.assertEqual(M.finish_tool(process, time.monotonic() + 5), 0)
        self.assertEqual(events, ['observe', 'group-signal', 'reap'])

    def test_previously_consumed_leader_is_not_signaled(self):
        for consumed in (0, 7, -9):
            process = mock.Mock(pid=123, returncode=consumed)
            with mock.patch.object(M.os, 'killpg') as group, mock.patch.object(M.os, 'kill') as direct:
                with self.assertRaisesRegex(M.Rejected, 'BUILD_CHILD_OWNERSHIP_LOST'):
                    M.finish_tool(process, time.monotonic() + 5)
                group.assert_not_called(); direct.assert_not_called(); process.wait.assert_not_called()

    def test_externally_reaped_leader_is_not_signaled(self):
        process = mock.Mock(pid=123, returncode=None)
        with mock.patch.object(M.os, 'waitid', side_effect=ChildProcessError), mock.patch.object(
                M.os, 'killpg') as group, mock.patch.object(M.os, 'kill') as direct:
            with self.assertRaisesRegex(M.Rejected, 'BUILD_CHILD_OWNERSHIP_LOST'):
                M.finish_tool(process, time.monotonic() + 5)
        group.assert_not_called(); direct.assert_not_called(); process.wait.assert_not_called()
        self.assertEqual(process.returncode, 255)

    def test_wrong_observed_child_identity_is_rejected(self):
        process = mock.Mock(pid=123, returncode=None)
        with mock.patch.object(M.os, 'waitid', return_value=mock.Mock(si_pid=456)), mock.patch.object(
                M.os, 'killpg') as group:
            with self.assertRaisesRegex(M.Rejected, 'BUILD_CHILD_IDENTITY'):
                M.finish_tool(process, time.monotonic() + 5)
        group.assert_not_called(); process.wait.assert_not_called()

    def test_wrong_group_cannot_signal_other_processes(self):
        process = mock.Mock(pid=123, returncode=None)
        process.wait.return_value = -9
        with mock.patch.object(M.os, 'waitid', return_value=None), mock.patch.object(
                M.os, 'getpgid', return_value=456), mock.patch.object(M.os, 'killpg') as group, mock.patch.object(
                M.os, 'kill') as direct:
            with self.assertRaisesRegex(M.Rejected, 'BUILD_PROCESS_GROUP_CLEANUP_FAILED'):
                M.finish_tool(process, time.monotonic() + 5)
        group.assert_not_called(); direct.assert_called_once_with(123, M.signal.SIGKILL)
        process.wait.assert_called_once()

    def test_missing_group_is_not_silent_success(self):
        process = mock.Mock(pid=123, returncode=None)
        process.wait.return_value = 0
        with mock.patch.object(M.os, 'waitid', return_value=mock.Mock(si_pid=123)), mock.patch.object(
                M.os, 'getpgid', side_effect=ProcessLookupError), mock.patch.object(M.os, 'killpg') as group:
            with self.assertRaisesRegex(M.Rejected, 'BUILD_PROCESS_GROUP_CLEANUP_FAILED'):
                M.finish_tool(process, time.monotonic() + 5)
        group.assert_not_called(); process.wait.assert_called_once()

    def test_group_signal_error_attempts_direct_reap_but_never_passes(self):
        process = mock.Mock(pid=123, returncode=None)
        process.wait.return_value = -9
        with mock.patch.object(M.os, 'waitid', return_value=None), mock.patch.object(
                M.os, 'getpgid', return_value=123), mock.patch.object(M.os, 'killpg', side_effect=PermissionError), mock.patch.object(
                M.os, 'kill') as direct:
            with self.assertRaisesRegex(M.Rejected, 'BUILD_PROCESS_GROUP_CLEANUP_FAILED'):
                M.finish_tool(process, time.monotonic() + 5)
        direct.assert_called_once_with(123, M.signal.SIGKILL); process.wait.assert_called_once()

    def test_cleanup_does_not_reset_expired_deadline(self):
        process = mock.Mock(pid=123, returncode=None)
        process.wait.return_value = 0
        with mock.patch.object(M.os, 'waitid', return_value=mock.Mock(si_pid=123)), mock.patch.object(
                M.os, 'getpgid', return_value=123), mock.patch.object(M.os, 'killpg'), mock.patch.object(
                M.time, 'monotonic', return_value=10):
            with self.assertRaisesRegex(M.Rejected, 'BUILD_CLEANUP_DEADLINE'):
                M.finish_tool(process, 9)
        process.wait.assert_called_once_with(timeout=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
