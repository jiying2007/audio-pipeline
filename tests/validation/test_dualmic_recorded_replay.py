#!/usr/bin/env python3
"""D0 method tests: artificial arrays never enter real-speech source admission."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import build_dualmic_recorded_corpus as builder
import run_dualmic_recorded_replay as replay
import dualmic_profile_support as support


class RecordedCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="ap-recorded-method-unit-")
        cls.root = Path(cls.temporary.name)
        cls.source = cls.root / "not-real-speech-test-fixture"
        cls.source.mkdir()
        rows = []
        for index, speaker in enumerate(s for pair in builder.PAIRS for s in pair):
            filename = f"speaker-{speaker}.s16"
            values = [((sample * (index + 11)) % 3001) - 1500 for sample in range(builder.SOURCE_SAMPLES)]
            (cls.source / filename).write_bytes(builder.pcm(values))
            rows.append({"speaker": speaker, "window_file": filename,
                         "role": "development-diagnostic" if index < 4 else "speaker-disjoint-confirmation-diagnostic"})
        cls.fixture_record = {"speaker_selection": rows}
        builder.write_json(cls.source / "source-receipt.json", {"test_only": True})
        for name in ("LICENSE.TXT", "README.TXT", "ATTRIBUTION.txt", "SPEAKERS.TXT"):
            (cls.source / name).write_text("FIRST-PARTY METHOD TEST, NOT REAL SPEECH\n")
        cls.output = cls.root / "corpus"
        # This scoped unit seam tests derivation only, not source admission.
        with patch.object(builder, "source_check", return_value=cls.fixture_record):
            cls.corpus = builder.build(cls.source, cls.output)
            builder.verify(cls.output / "corpus.json")
        cls.original_corpus = (cls.output / "corpus.json").read_bytes()
        cls.original_manifest = (cls.output / "source-manifest.json").read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def tearDown(self):
        (self.output / "corpus.json").write_bytes(self.original_corpus)
        (self.output / "source-manifest.json").write_bytes(self.original_manifest)

    def checked(self):
        with patch.object(builder, "source_check", return_value=self.fixture_record):
            return builder.verify(self.output / "corpus.json")

    def test_real_source_admission_rejects_artificial_fixture(self):
        with self.assertRaises((ValueError, KeyError, FileNotFoundError)):
            builder.expected(self.source)
        with self.assertRaises((ValueError, KeyError, FileNotFoundError)):
            builder.verify(self.output / "corpus.json")

    def test_frozen_coverage_placement_and_profile_pairing(self):
        corpus = self.checked()
        self.assertEqual(len(corpus["cases"]), 56)
        self.assertEqual(len({c["mic_audio"] for c in corpus["cases"]}), 28)
        rows = {c["case_id"]: c for c in corpus["cases"]}
        for pair in range(4):
            for scenario in builder.SCENARIOS:
                first, second = [rows[f"pair-{pair}-{scenario}-{p}"] for p in builder.PROFILES]
                for field in builder.SOURCE_FIELDS:
                    self.assertEqual(first[field], second[field])
                self.assertIsNone(first["vad_labels"])
                self.assertEqual(first["dimensions"]["data_role"], "regression")
            case = rows[f"pair-{pair}-near-only-call"]
            clean = builder.samples((self.output / case["clean_near_audio"]).read_bytes())
            self.assertEqual(clean[:24000], [0] * 24000)
            self.assertEqual(clean[88000:], [0] * 8000)
            self.assertTrue(any(clean[24000:88000]))
            gap = rows[f"pair-{pair}-render-gap-call"]
            render = builder.samples((self.output / gap["render_audio"]).read_bytes())
            self.assertEqual(render[48000:48640], [0] * 640)
            self.assertEqual(render[64000:], [0] * 32000)

    def test_frozen_metadata_rejects_coverage_roles_events_and_labels(self):
        mutations = {
            "missing": lambda x: x["cases"].pop(),
            "duplicate": lambda x: x["cases"].append(copy.deepcopy(x["cases"][0])),
            "profile": lambda x: x["cases"][0].update(pipeline_profile="assistant"),
            "tuning-gate": lambda x: x["cases"][0].update(expected={"min_erle_db": -100}),
            "event": lambda x: x["cases"][0].update(control={"echo_path_change_frame": 1}),
            "relabel": lambda x: x["cases"][0]["dimensions"].update(data_role="independent"),
            "invented-vad": lambda x: x["cases"][0].update(vad_labels="cases/fake.labels"),
            "physical-claim": lambda x: x["cases"][0]["dimensions"].update(real_array_recording=True),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(self.corpus)
                mutate(changed)
                builder.write_json(self.output / "corpus.json", changed)
                with self.assertRaises(ValueError):
                    self.checked()

    def test_resealed_modified_derivative_is_rejected(self):
        relative = self.corpus["cases"][0]["mic_audio"]
        path = self.output / relative
        original = path.read_bytes()
        try:
            altered = b"\x01\x00" + original[2:]
            path.write_bytes(altered)
            manifest = json.loads(self.original_manifest)
            manifest["files"][relative] = {"sha256": hashlib.sha256(altered).hexdigest(), "size_bytes": len(altered)}
            builder.write_json(self.output / "source-manifest.json", manifest)
            corpus = copy.deepcopy(self.corpus)
            corpus["source_manifest_sha256"] = builder.sha256_file(self.output / "source-manifest.json")
            builder.write_json(self.output / "corpus.json", corpus)
            with self.assertRaises(ValueError):
                self.checked()
        finally:
            path.write_bytes(original)

    def test_truncated_derivative_and_extra_file_are_rejected(self):
        path = self.output / self.corpus["cases"][0]["mic_audio"]
        original = path.read_bytes()
        try:
            path.write_bytes(original[:-2])
            with self.assertRaises(ValueError):
                self.checked()
        finally:
            path.write_bytes(original)
        extra = self.output / "unregistered-pcm.bin"
        try:
            extra.write_bytes(b"\0\0")
            with self.assertRaises(ValueError):
                self.checked()
        finally:
            extra.unlink()

    def test_no_silent_clipping(self):
        with self.assertRaises(ValueError):
            builder.safe_mix([32767] * builder.SAMPLES, [1] * builder.SAMPLES)

    def test_listening_wavs_preserve_exact_levels_and_anonymous_key(self):
        with tempfile.TemporaryDirectory(prefix="ap-recorded-listening-method-") as temp:
            root = Path(temp)
            import shutil
            shutil.copytree(self.output, root / "input")
            for case in self.corpus["cases"]:
                directory = root / "replay" / case["case_id"]
                directory.mkdir(parents=True)
                # First-party sentinels test the packer, not DSP or actual speech.
                value = 101 if case["pipeline_profile"] == "call" else 202
                (directory / "out.pcm").write_bytes(builder.pcm([value] * builder.SAMPLES))
            result = replay.export_listening(root, self.corpus)
            self.assertEqual(result["wav_options"], 84)
            self.assertEqual(replay.verify_listening(root, self.corpus), result)
            key = json.loads((root / "listening-key.json").read_text())
            first = root / "listening" / key["options"][0]["wav"]
            original = first.read_bytes()
            with wave.open(str(first), "rb") as stream:
                payload = stream.readframes(builder.SAMPLES)
            with wave.open(str(first), "wb") as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(builder.RATE)
                stream.writeframes(b"\x7b\x00" + payload[2:])
            with self.assertRaises(ValueError):
                replay.verify_listening(root, self.corpus)
            first.write_bytes(original)
            key["options"][0]["identity"] = "forged"
            builder.write_json(root / "listening-key.json", key)
            with self.assertRaises(ValueError):
                replay.verify_listening(root, self.corpus)

    def test_frame_loss_and_nonfinite_values_are_not_hidden(self):
        case = self.corpus["cases"][0]
        good = [{"frame": n, "vad_probability": .2} for n in range(600)]
        inputs = {"mic": [0] * 192000, "render": None}
        support.continuity(case, [0] * 96000, good, inputs)
        for output, trace in (([0] * 95999, good), ([0] * 96000, good[:-1]),
                              ([0] * 96000, good[:20] + good[21:] + [good[-1]]),
                              ([0] * 96000, [dict(row, vad_probability=float("nan")) for row in good])):
            with self.assertRaises(ValueError):
                support.continuity(case, output, trace, inputs)
        self.assertFalse(replay.finite({"a": [None, {"b": float("inf")}] }))

    def test_failed_worker_is_retained_and_never_complete(self):
        output = self.root / "failed-worker"
        args = argparse.Namespace(output=output, processor=self.root / "not-a-processor",
                                  corpus=self.output / "corpus.json", source_revision="0" * 40)
        self.assertEqual(replay.supervise(args), 1)
        phase = json.loads((output / "execution-phase.json").read_text())
        self.assertEqual(phase["status"], "FAIL")
        self.assertTrue(phase["terminal"])
        self.assertNotEqual(phase["returncode"], 0)
        self.assertIn("execution source differ", (output / "execution.log").read_text())
        self.assertTrue((output / "artifact-manifest.json").is_file())
        with self.assertRaises(ValueError):
            replay.supervise(args)


if __name__ == "__main__":
    unittest.main()
