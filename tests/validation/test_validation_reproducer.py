#!/usr/bin/env python3
"""F02 engineering fixtures: each signal is 10 ms, never real acoustic evidence."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import validation_reproducer as reproducer

# Records the actual processor arguments/bytes, rather than pretending to be DSP.
PROCESSOR = '''#!/usr/bin/env python3
import hashlib
import json
import struct
import sys
from pathlib import Path

args = sys.argv[1:]
channels = int(args[args.index("--mic-channels") + 1])
metrics = Path(args[args.index("--metrics-jsonl") + 1])
if "--capture-only" in args:
    mic, output = map(Path, args[-2:])
    render = None
else:
    mic, render, output = map(Path, args[-3:])
raw = mic.read_bytes()
if raw.startswith(b"RIFF"):
    raise SystemExit("WAV header entered raw processor")
values = struct.unpack("<" + "h" * (len(raw) // 2), raw)[::channels]
output.write_bytes(struct.pack("<" + "h" * len(values), *values))
metrics.write_text(json.dumps({
    "argv": args, "mic_sha256": hashlib.sha256(raw).hexdigest(),
    "render_sha256": hashlib.sha256(render.read_bytes()).hexdigest() if render else None,
}) + "\\n", encoding="utf-8")
'''


class ReproducerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ap-reproducer-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.corpus_path = self.root / "corpus.json"
        self.report_path = self.root / "report.json"
        self.destination = self.root / "bundle"
        self.processor = self.root / "processor with space"
        self.processor.write_text(PROCESSOR, encoding="utf-8")
        self.processor.chmod(0o755)
        self.raw = {}
        self.case = {
            "case_id": "tiny", "sample_rate_hz": 16000, "mic_channels": 2,
            "split": "validation", "scenario": "engineering-fixture",
            "control": {"echo_path_change_frame": 1, "discontinuity_frame": 2,
                        "discontinuity_flags": 3, "discontinuity_lost_frames": 1},
        }
        for index, role in enumerate(reproducer.INPUT_KEYS[:-1]):
            channels = 2 if role == "mic_audio" else 1
            self.raw[role] = struct.pack("<" + "h" * (160 * channels),
                                        *[index * 1000 + (i % 101) - 50
                                          for i in range(160 * channels)])
            path = self.root / role / "same.wav"
            self.write_wav(path, self.raw[role], channels)
            self.case[role] = path.relative_to(self.root).as_posix()
        labels = self.root / "vad_labels" / "same.wav"
        labels.parent.mkdir()
        labels.write_text("1\n", encoding="utf-8")
        self.case["vad_labels"] = labels.relative_to(self.root).as_posix()
        self.write_metadata()

    def write_wav(self, path, raw, channels=1, rate=16000, width=2):
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(channels)
            handle.setframerate(rate)
            handle.setsampwidth(width)
            handle.writeframes(raw)

    def write_metadata(self, corpus=None, report=None):
        corpus = corpus if corpus is not None else {"schema_version": 1, "corpus_id": "tiny",
                                                    "tier": "regression", "cases": [self.case]}
        reproducer.write_json(self.corpus_path, corpus)
        report = report if report is not None else {
            "cases": [{"case_id": self.case["case_id"], "passed": False}],
            "bindings": {"corpus_sha256": reproducer.engine.sha256_file(self.corpus_path)},
        }
        reproducer.write_json(self.report_path, report)

    def cli(self, destination=None, processor=None):
        command = [sys.executable, str(ROOT / "scripts/validation_reproducer.py"),
                   "--corpus", str(self.corpus_path), "--report", str(self.report_path),
                   "--destination", str(destination or self.destination)]
        if processor is not None:
            command += ["--processor", str(processor)]
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def assert_cli_failure(self, pattern):
        result = self.cli()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(pattern, result.stderr)
        self.assertFalse((self.destination / "tiny" / "reproduce.sh").exists())

    def test_wav_same_basename_and_canonical_bytes_command(self):
        work = self.root / "canonical-run"
        work.mkdir()
        output, trace, _ = reproducer.stage_profile_support.build_invoke(reproducer.engine)(
            self.processor, self.case, self.corpus_path, work)
        result = self.cli(processor=self.processor)
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = self.destination / "tiny"
        case = json.loads((bundle / "case.json").read_text())
        manifest = json.loads((bundle / "input-manifest.json").read_text())
        self.assertEqual(len(set(case[key] for key in reproducer.INPUT_KEYS)), 5)
        for role, binding in manifest["inputs"].items():
            source = self.root / self.case[role]
            self.assertEqual((bundle / binding["original_path"]).read_bytes(), source.read_bytes())
            self.assertEqual(binding["original_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            if role != "vad_labels":
                self.assertEqual((bundle / binding["pcm_path"]).read_bytes(), self.raw[role])
                self.assertEqual(binding["pcm_sha256"], hashlib.sha256(self.raw[role]).hexdigest())
                self.assertNotEqual(binding["pcm_sha256"], binding["original_sha256"])
                self.assertLessEqual(binding["sample_frames"], binding["sample_rate_hz"])
        self.assertEqual((bundle / "out.pcm").read_bytes(), (work / "out.pcm").read_bytes())
        replay_trace = json.loads((bundle / "metrics.jsonl").read_text())
        normalize = lambda argv: ["<path>" if Path(arg).is_absolute() else arg for arg in argv]
        self.assertEqual(normalize(trace[0]["argv"]), normalize(replay_trace["argv"]))
        self.assertEqual(trace[0]["mic_sha256"], replay_trace["mic_sha256"])
        self.assertEqual(trace[0]["render_sha256"], replay_trace["render_sha256"])
        for name in reproducer.INVOCATION_SOURCES:
            self.assertEqual((bundle / "canonical" / name).read_bytes(),
                             (reproducer.TOOLS / name).read_bytes())
        self.assertEqual((bundle / "replay-returncode.txt").read_text(), "0\n")

        # Move the self-contained bundle away from its original corpus and cwd.
        moved = self.root / "moved bundle"
        shutil.move(str(self.destination), str(moved))
        for role in reproducer.INPUT_KEYS:
            shutil.rmtree(self.root / role)
        environment = dict(os.environ, PROCESSOR=str(self.processor), PYTHON=sys.executable)
        replay = subprocess.run(["sh", str(moved / "tiny" / "reproduce.sh")],
                                cwd=str(self.root), env=environment,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        self.assertEqual((moved / "tiny/out.pcm").read_bytes(), (work / "out.pcm").read_bytes())

    def test_raw_control_and_all_capture_profiles_use_canonical_invocation(self):
        for role in reproducer.INPUT_KEYS[:-1]:
            path = self.root / role / "same.pcm"
            path.write_bytes(self.raw[role])
            self.case[role] = path.relative_to(self.root).as_posix()
        self.case.pop("render_audio")
        for profile in sorted(reproducer.stage_profile_support.SUPPORTED_CAPTURE_PROFILES):
            with self.subTest(profile=profile):
                self.case["processor_profile"] = profile
                self.write_metadata()
                work = self.root / ("canonical-" + profile)
                work.mkdir()
                _, trace, _ = reproducer.stage_profile_support.build_invoke(reproducer.engine)(
                    self.processor, self.case, self.corpus_path, work)
                destination = self.root / ("bundle-" + profile)
                result = self.cli(destination, self.processor)
                self.assertEqual(result.returncode, 0, result.stderr)
                bundle = destination / "tiny"
                manifest = json.loads((bundle / "input-manifest.json").read_text())
                mic = manifest["inputs"]["mic_audio"]
                self.assertEqual(mic["original_path"], mic["pcm_path"])
                self.assertEqual(mic["original_sha256"], mic["pcm_sha256"])
                self.assertEqual((bundle / mic["pcm_path"]).read_bytes(), self.raw["mic_audio"])
                actual = json.loads((bundle / "metrics.jsonl").read_text())
                normalize = lambda argv: ["<path>" if Path(arg).is_absolute() else arg for arg in argv]
                self.assertEqual(normalize(trace[0]["argv"]), normalize(actual["argv"]))
                self.assertEqual((bundle / "out.pcm").read_bytes(), (work / "out.pcm").read_bytes())

    def test_malformed_audio_fails_before_replay(self):
        path = self.root / self.case["mic_audio"]
        original = path.read_bytes()
        cases = [
            ("empty", b"", "EOF"),
            ("invalid-header", b"not a WAV", "RIFF"),
            ("truncated-payload", original[:-4], "truncated WAV"),
        ]
        for name, data, message in cases:
            with self.subTest(name=name):
                path.write_bytes(data)
                self.destination = self.root / ("bad-" + name)
                # EOFError has no message, but the CLI must still fail explicitly.
                self.assert_cli_failure("validation reproducer:" if name == "empty" else message)
        for name, rate, channels, width, message in [
                ("rate", 8000, 2, 2, "rate mismatch"),
                ("channels", 16000, 1, 2, "channel mismatch"),
                ("width", 16000, 2, 1, "PCM16")]:
            with self.subTest(name=name):
                self.write_wav(path, self.raw["mic_audio"], channels, rate, width)
                self.destination = self.root / ("bad-" + name)
                self.assert_cli_failure(message)
        for name, raw, message in [
                ("odd", b"\x00", "odd S16LE"),
                ("empty-pcm", b"", "empty or incomplete"),
                ("incomplete-channel", b"\x00\x00", "empty or incomplete")]:
            with self.subTest(name=name):
                pcm = self.root / "bad.pcm"
                pcm.write_bytes(raw)
                self.case["mic_audio"] = "bad.pcm"
                self.write_metadata()
                self.destination = self.root / ("bad-" + name)
                self.assert_cli_failure(message)

    def test_missing_input_and_invalid_labels_fail(self):
        (self.root / self.case["vad_labels"]).write_text("2\n")
        self.assert_cli_failure("invalid VAD label")
        self.destination = self.root / "missing"
        self.case["mic_audio"] = "missing.wav"
        self.write_metadata()
        self.assert_cli_failure("No such file")

    def test_declared_symlink_suffix_is_preserved(self):
        source = self.root / self.case["mic_audio"]
        target = source.with_suffix(".bin")
        source.rename(target)
        source.symlink_to(target.name)
        result = self.cli(processor=self.processor)
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = self.destination / "tiny"
        case = json.loads((bundle / "case.json").read_text())
        self.assertEqual((bundle / case["mic_audio"]).read_bytes(), self.raw["mic_audio"])

    def test_bad_geometry_profile_and_controls_fail(self):
        for name, value, message in [("sample_rate_hz", 11025, "geometry"),
                                     ("mic_channels", 3, "geometry"),
                                     ("processor_profile", "unknown", "processor_profile"),
                                     ("control", [], "control must be an object"),
                                     ("control", {"discontinuity_frame": "bad"}, "invalid literal")]:
            with self.subTest(name=name, value=value):
                case = dict(self.case, **{name: value})
                self.write_metadata(corpus={"cases": [case]})
                self.destination = self.root / ("bad-metadata-" + str(len(list(self.root.iterdir()))))
                self.assert_cli_failure(message)

    def test_invalid_metadata_and_existing_evidence_fail(self):
        for identity in ("../outside", ".", "/absolute", "a\\b"):
            with self.subTest(case_id=identity):
                self.case["case_id"] = identity
                self.write_metadata()
                self.assert_cli_failure("unsafe replay case_id")
        self.case["case_id"] = "tiny"
        self.write_metadata(report={"cases": [{"case_id": "unknown", "passed": False}]})
        self.assert_cli_failure("unknown or duplicate")
        self.write_metadata(corpus={"cases": [self.case, copy.deepcopy(self.case)]})
        self.assert_cli_failure("unique")
        self.write_metadata(report={"cases": [{"case_id": "tiny", "passed": False}],
                                    "bindings": {"corpus_sha256": "0" * 64}})
        self.assert_cli_failure("corpus_sha256")
        self.write_metadata()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        original = (self.destination / "tiny/case.json").read_bytes()
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to overwrite", result.stderr)
        self.assertEqual((self.destination / "tiny/case.json").read_bytes(), original)

    def test_processor_failure_retained_and_propagated(self):
        self.processor.write_text("#!/usr/bin/env python3\nraise SystemExit(7)\n")
        result = self.cli(processor=self.processor)
        self.assertNotEqual(result.returncode, 0)
        bundle = self.destination / "tiny"
        self.assertEqual((bundle / "replay-returncode.txt").read_text(), "7\n")
        self.assertTrue((bundle / "replay.log").exists())
        self.assertTrue((bundle / "input-manifest.json").exists())
        self.assertEqual(json.loads(result.stdout)["replay_failures"], 1)

    def test_tampered_materialized_pcm_is_not_replayed(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = self.destination / "tiny"
        case = json.loads((bundle / "case.json").read_text())
        (bundle / case["mic_audio"]).write_bytes(b"\x00\x00")
        result = subprocess.run([sys.executable, str(bundle / "reproduce.py"), str(self.processor)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hash mismatch", result.stderr)
        self.assertFalse((bundle / "out.pcm").exists())

    def test_canonical_snapshot_is_verified_before_import(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = self.destination / "tiny"
        source = bundle / "canonical/run_validation_engine.py"
        source.write_text('raise RuntimeError("unverified source executed")\n')
        result = subprocess.run([sys.executable, str(bundle / "reproduce.py"), str(self.processor)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hash mismatch", result.stderr)
        self.assertNotIn("unverified source executed", result.stderr)
        self.assertFalse((bundle / "out.pcm").exists())

    def test_python38_syntax(self):
        for path in (ROOT / "scripts/validation_reproducer.py", Path(__file__)):
            ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 8))
        ast.parse(reproducer.REPLAY_PY, feature_version=(3, 8))


if __name__ == "__main__":
    unittest.main(verbosity=2)
