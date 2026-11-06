#!/usr/bin/env python3
"""Host unit/negative contracts for the new profile invocation and corpus.

Unit command stubs below test argument construction only. Actual DSP, effective
configuration and PCM equivalence are covered by ap_process_pcm_profile_tests
and by the source-bound replay; no stub result is acoustic evidence.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_dualmic_profile_corpus as builder
import dualmic_profile_support as support
import run_dualmic_profile_replay as replay


class ProfileInvocationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ap-profile-unit-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.mic = self.root / "mic.pcm"
        self.render = self.root / "render.pcm"
        builder.write_pcm(self.mic, [100] * (4 * 160 * 2))
        builder.write_pcm(self.render, [20] * (4 * 160))
        self.case = {"case_id": "unit", "sample_rate_hz": 16000, "mic_channels": 2,
                     "mic_audio": "mic.pcm", "render_audio": None,
                     "processor_profile": "default", "pipeline_profile": "assistant"}
        self.commands = []

    def command_stub(self, command, **kwargs):
        self.commands.append(command)
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(kwargs["timeout"], 30)
        builder.write_pcm(Path(command[-1]), [10] * (4 * 160))
        metrics = Path(command[command.index("--metrics-jsonl") + 1])
        metrics.write_text("".join(json.dumps({"frame": index, "vad_probability": 0.5}) + "\n"
                                   for index in range(4)))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def forbidden_delegate(self, *args):
        self.fail("explicit profile silently used the legacy invocation")

    def test_legacy_is_delegated_without_changes(self):
        case = copy.deepcopy(self.case)
        case.pop("pipeline_profile")
        sentinel = object()
        seen = []

        def original(*args):
            seen.append(args)
            return sentinel

        invoke = support.build_invoke(original, run_command=self.command_stub)
        arguments = (Path("processor"), case, self.root / "corpus.json", self.root)
        self.assertIs(invoke(*arguments), sentinel)
        self.assertEqual(seen, [arguments])
        self.assertEqual(self.commands, [])

    def test_two_profiles_all_capture_stages_and_events(self):
        invoke = support.build_invoke(self.forbidden_delegate, run_command=self.command_stub)
        for profile in sorted(support.PIPELINE_PROFILES):
            for capture in sorted(support.stage_profile_support.SUPPORTED_CAPTURE_PROFILES):
                with self.subTest(profile=profile, capture=capture):
                    case = dict(self.case, pipeline_profile=profile, processor_profile=capture,
                                control={"echo_path_change_frame": 2, "discontinuity_frame": 3,
                                         "discontinuity_flags": 2, "discontinuity_lost_frames": 4})
                    invoke(Path("processor"), case, self.root / "corpus.json", self.root)
                    command = self.commands[-1]
                    self.assertEqual(command[command.index("--profile") + 1], profile)
                    self.assertEqual(command[command.index("--capture-profile") + 1], capture)
                    self.assertIn("--capture-only", command)
                    self.assertEqual(command[command.index("--echo-path-change-frame") + 1], "2")
                    self.assertEqual(command[command.index("--discontinuity-lost-frames") + 1], "4")
                    self.assertTrue({"--aec-mu", "--ns-floor", "--agc-target-dbfs", "--limiter-dbfs"}.isdisjoint(command))

    def test_duplex_passes_reference_and_no_capture_stage(self):
        invoke = support.build_invoke(self.forbidden_delegate, run_command=self.command_stub)
        for profile in sorted(support.PIPELINE_PROFILES):
            case = dict(self.case, pipeline_profile=profile, render_audio="render.pcm")
            _, _, inputs = invoke(Path("processor"), case, self.root / "corpus.json", self.root)
            self.assertEqual(len(inputs["render"]), 640)
            self.assertEqual(self.commands[-1][-2], str(self.render))
            self.assertNotIn("--capture-only", self.commands[-1])
            self.assertNotIn("--capture-profile", self.commands[-1])

    def test_invalid_configuration_fails_before_command(self):
        invoke = support.build_invoke(self.forbidden_delegate, run_command=self.command_stub)
        for value in (None, "voice", "", 0, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                invoke(Path("processor"), dict(self.case, pipeline_profile=value), self.root / "corpus.json", self.root)
        with self.assertRaises(ValueError):
            invoke(Path("processor"), dict(self.case, processor_profile="bf-isolated", render_audio="render.pcm"),
                   self.root / "corpus.json", self.root)
        builder.write_pcm(self.mic, [0] * 321)
        with self.assertRaises(ValueError):
            invoke(Path("processor"), self.case, self.root / "corpus.json", self.root)
        self.assertEqual(self.commands, [])

    def test_partial_outputs_and_frame_holes_are_rejected(self):
        inputs = {"mic": [0] * 1280, "render": None}
        good = [{"frame": index} for index in range(4)]
        support.continuity(self.case, [0] * 640, good, inputs)
        for output, trace in (([0] * 639, good), ([0] * 640, good[:-1]),
                              ([0] * 640, [{"frame": 0}, {"frame": 2}, {"frame": 2}, {"frame": 3}]),
                              ([0] * 640, [{"frame": index, "vad_probability": float("nan")} for index in range(4)])):
            with self.assertRaises(ValueError):
                support.continuity(self.case, output, trace, inputs)

    def test_failed_command_keeps_partial_evidence(self):
        def fail(command, **kwargs):
            return subprocess.CompletedProcess(command, 5, stdout="partial", stderr="disk full")

        invoke = support.build_invoke(self.forbidden_delegate, retain_root=self.root / "retained", run_command=fail)
        with self.assertRaises(subprocess.CalledProcessError):
            invoke(Path("processor"), self.case, self.root / "corpus.json", self.root)
        retained = self.root / "retained/unit"
        self.assertEqual((retained / "stderr.txt").read_text(), "disk full")
        self.assertEqual(json.loads((retained / "execution.json").read_text())["returncode"], 5)
        with self.assertRaises(FileExistsError):
            invoke(Path("processor"), self.case, self.root / "corpus.json", self.root)

    def test_semantics_do_not_mutate_canonical_engine(self):
        original_invoke = support.engine.invoke
        original_evaluate = support.engine.evaluate_case
        original_policy = support.engine.policy_violations
        semantics = support.validation_semantics()
        self.assertIs(support.engine.invoke, original_invoke)
        self.assertIs(support.engine.evaluate_case, original_evaluate)
        self.assertIs(support.engine.policy_violations, original_policy)
        self.assertIsNot(semantics.evaluation.invoke, original_invoke)


class FrozenMatrixTests(unittest.TestCase):
    def test_fixed_coverage_sources_and_negative_mutations(self):
        with tempfile.TemporaryDirectory(prefix="ap-dualmic-corpus-unit-") as temporary:
            output = Path(temporary) / "corpus"
            corpus = builder.build(output)
            path = output / "corpus.json"
            self.assertEqual(len(builder.verify(path)["cases"]), 42)
            self.assertEqual({case["dimensions"]["data_role"] for case in corpus["cases"]}, {"regression"})
            schema = json.loads((builder.ROOT / "validation/corpus.schema.json").read_text())
            allowed_splits = schema["properties"]["cases"]["items"]["properties"]["split"]["enum"]
            self.assertTrue(all(case["split"] in allowed_splits for case in corpus["cases"]))
            for seed in builder.SEEDS:
                members = [case for case in corpus["cases"] if case["dimensions"]["seed"] == seed]
                self.assertEqual(len(members), 14)
                for scenario in builder.SCENARIOS:
                    pair = [case for case in members if case["scenario"] == scenario]
                    self.assertEqual(pair[0]["mic_audio"], pair[1]["mic_audio"])
                    self.assertEqual({case["pipeline_profile"] for case in pair}, {"call", "assistant"})
            with self.assertRaises(ValueError):
                builder.build(output)
            for field, value in (("pipeline_profile", "voice"), ("expected", {"min_erle_db": -100}),
                                 ("control", {"echo_path_change_frame": 1})):
                damaged = copy.deepcopy(corpus)
                damaged["cases"][0][field] = value
                replay.write_json(path, damaged)
                with self.assertRaises(ValueError):
                    builder.verify(path)
            replay.write_json(path, corpus)
            mic = output / corpus["cases"][0]["mic_audio"]
            mic.write_bytes(mic.read_bytes()[:-2])
            with self.assertRaises(ValueError):
                builder.verify(path)

    def test_byte_comparison_detects_metric_only_drift(self):
        with tempfile.TemporaryDirectory(prefix="ap-dualmic-byte-unit-") as temporary:
            left, right = Path(temporary) / "a", Path(temporary) / "b"
            left.mkdir()
            right.mkdir()
            for directory in (left, right):
                (directory / "out.pcm").write_bytes(b"\0\0" * 160)
                (directory / "metrics.jsonl").write_text('{"frame":0}\n')
            self.assertTrue(replay.compare_artifacts(left, right)["passed"])
            (right / "metrics.jsonl").write_text('{"frame":1}\n')
            self.assertFalse(replay.compare_artifacts(left, right)["passed"])


if __name__ == "__main__":
    unittest.main()
