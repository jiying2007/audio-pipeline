#!/usr/bin/env python3
"""Independent finite transport examples plus real libopus/Runtime negative tests."""
from __future__ import annotations

import argparse
import copy
import ctypes as ct
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import dualmic_intercom_transport as transport

BRIDGE: Path | None = None


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.packets = [struct.pack("<I", value) for value in range(110)]

    @staticmethod
    def decode_test_payload(payload):
        # Explicit test-only tagged PCM. Formal runs use the real Opus decoder.
        sample = -1000 if payload is None else struct.unpack("<I", payload)[0]
        return [sample] * 320

    def test_eight_schedules_have_independently_expected_playout(self):
        expected_missing = {"single-loss": {100}, "burst-loss": {100, 101}, "late": {100}}
        for scenario in transport.SCENARIOS:
            with self.subTest(scenario=scenario):
                events = transport.arrival_schedule(self.packets, scenario)
                audio, counts, rows = transport.playout(self.packets, events, self.decode_test_payload)
                expected = [0] * 1280
                missing = expected_missing.get(scenario, set())
                for sequence in range(110):
                    expected.extend([-1000 if sequence in missing else sequence] * 320)
                self.assertEqual(audio, expected)
                self.assertEqual(counts["plc_packets"], len(missing))
                self.assertEqual(counts["late_packets"], int(scenario == "late"))
                self.assertEqual(counts["duplicates"], int(scenario == "duplicate"))
                played = [row["sequence"] for row in rows if row["kind"] == "playout"]
                self.assertEqual(played, list(range(110)))
                self.assertLessEqual(counts["queue_high_water"], 6)
                if scenario == "reorder":
                    arrived = [event.sequence for event in events]
                    self.assertLess(arrived.index(41), arrived.index(40))

    def test_deadline_inclusive_and_one_microsecond_late(self):
        packets = self.packets[:2]
        for delta, expected in ((0, 0), (1, 1)):
            events = [transport.Arrival(80000 + delta, 0, packets[0]),
                      transport.Arrival(50000, 1, packets[1])]
            _, counts, _ = transport.playout(packets, events, self.decode_test_payload)
            self.assertEqual(counts["plc_packets"], expected)
            self.assertEqual(counts["late_packets"], expected)

    def test_duplicate_conflict_and_queue_capacity_fail(self):
        events = transport.arrival_schedule(self.packets, "duplicate")
        position = next(i for i, event in enumerate(events)
                        if event.sequence == 70 and event.time_us == 1431000)
        events[position] = transport.Arrival(1431000, 70, b"wrong")
        with self.assertRaisesRegex(transport.ContractError, "conflicting duplicate"):
            transport.playout(self.packets, events, self.decode_test_payload)
        with self.assertRaisesRegex(transport.ContractError, "jitter queue full"):
            transport.playout(self.packets, transport.arrival_schedule(self.packets, "normal"),
                              self.decode_test_payload, capacity=2)

    def test_invalid_time_sequence_payload_and_decoder_rejected(self):
        for event in (transport.Arrival(float("nan"), 0, self.packets[0]),
                      transport.Arrival(True, 0, self.packets[0]),
                      transport.Arrival(0, 0, self.packets[0]),
                      transport.Arrival(30000, True, self.packets[0]),
                      transport.Arrival(30000, -1, self.packets[0]),
                      transport.Arrival(30000, 110, self.packets[0])):
            with self.subTest(event=event), self.assertRaises(transport.ContractError):
                transport.playout(self.packets, [event], self.decode_test_payload)
        with self.assertRaisesRegex(transport.ContractError, "payload identity"):
            transport.playout(self.packets, [transport.Arrival(30000, 0, b"wrong")], self.decode_test_payload)
        for decoder in (lambda _: [], lambda _: [float("nan")] * 320):
            with self.assertRaises(transport.ContractError):
                transport.playout(self.packets, [], decoder)

    def test_render_binding_and_pcm_completeness(self):
        source = transport.pcm_bytes([100] * transport.LOCAL_SAMPLES)
        muted = transport.pcm_bytes(transport.apply_playback([100] * transport.LOCAL_SAMPLES, "gain-mute"))
        transport.require_reference(muted, muted)
        with self.assertRaisesRegex(transport.ContractError, "post-PLC/post-volume"):
            transport.require_reference(muted, source)
        with self.assertRaises(transport.ContractError):
            transport.pcm_samples(b"\x01")
        for samples in ([32768], [-32769], [True], [float("nan")]):
            with self.subTest(samples=samples), self.assertRaises(transport.ContractError):
                transport.pcm_bytes(samples)

    def test_missing_counts_not_success(self):
        _, counts, _ = transport.playout(self.packets, transport.arrival_schedule(self.packets, "normal"),
                                         self.decode_test_payload)
        transport.check_counts(counts, "normal", 110)
        for key in ("decoded_packets", "playout_samples", "decode_order"):
            bad = copy.deepcopy(counts)
            bad.pop(key)
            with self.assertRaises(transport.ContractError):
                transport.check_counts(bad, "normal", 110)


class RealOpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A missing codec is an actual test error, never an invented codec PASS.
        cls.library = transport.OpusLibrary()

    def test_actual_codec_roundtrip_and_plc(self):
        with self.library.session() as codec:
            source = [int(8000 * math.sin(index * 0.1)) for index in range(320)]
            payload = codec.encode(source)
            decoded = codec.decode(payload)
            concealed = codec.decode(None)
            self.assertEqual(len(payload), 60)  # Frozen 24 kbit/s, 20 ms CBR.
            self.assertEqual(len(decoded), 320)
            self.assertEqual(len(concealed), 320)
            self.assertTrue(any(decoded))
            self.assertGreaterEqual(codec.settings["lookahead_samples"], 0)
            self.assertEqual(codec.settings["inband_fec"], 0)
            self.assertEqual(codec.settings["dtx"], 0)
            self.assertTrue(Path(self.library.identity["loaded_path"]).is_file())

    def test_actual_codec_errors_remain_errors(self):
        with self.library.session() as codec:
            for payload in (b"", b"\x03", b"x" * 1276):
                with self.subTest(payload_length=len(payload)), self.assertRaises(transport.ContractError):
                    codec.decode(payload)
            for source in ([0] * 319, [0] * 321, [40000] * 320):
                with self.assertRaises(transport.ContractError):
                    codec.encode(source)
            source = (ct.c_int16 * 320)()
            encoded = (ct.c_ubyte * 1275)()
            self.assertLess(self.library.lib.opus_encode(codec.encoder, source, 319, encoded, 1275), 0)
            bad_packet = (ct.c_ubyte * 1)(3)
            output = (ct.c_int16 * 320)()
            self.assertLess(self.library.lib.opus_decode(codec.decoder, bad_packet, 1, output, 320, 0), 0)

    def test_partial_twenty_ms_stream_never_silently_padded(self):
        with tempfile.TemporaryDirectory() as temporary:
            for count in (0, 160, 321):
                with self.subTest(count=count), self.assertRaises(transport.ContractError):
                    transport.transport(self.library, [0] * count, "normal",
                                        Path(temporary) / str(count), transport.Budget())


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if BRIDGE is None:
            raise RuntimeError("--bridge is required for actual Runtime tests")

    def invoke(self, mode, mic, render, *, bad_output=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "mic.pcm").write_bytes(mic)
        (root / "render.pcm").write_bytes(render)
        command = [str(BRIDGE), mode, str(root / "mic.pcm"), str(root / "render.pcm"),
                   "/dev/full" if bad_output else str(root / "output.pcm"),
                   str(root / "consumed.pcm"), str(root / "trace.jsonl"),
                   str(root / "report.json"), "0"]
        result = subprocess.run(command, capture_output=True, timeout=10)
        return result, root

    def test_actual_runtime_and_direct_complete_frames(self):
        mic = transport.pcm_bytes([1000, -1000] * 160 * 4)
        render = transport.pcm_bytes([100] * 160 * 4)
        first, a = self.invoke("runtime", mic, render)
        second, b = self.invoke("direct", mic, render)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((a / "output.pcm").read_bytes(), (b / "output.pcm").read_bytes())
        self.assertEqual((a / "consumed.pcm").read_bytes(), render)
        self.assertEqual(len((a / "output.pcm").read_bytes()), 1280)
        report = json.loads((a / "report.json").read_text())
        self.assertEqual(report["runtime"]["submitted_frames"], 4)
        self.assertEqual(report["runtime"]["processed_frames"], 4)
        self.assertEqual(report["runtime"]["timestamp_frames"], 0)

    def test_truncated_capture_render_suffix_and_write_failure(self):
        mic, render = b"\0" * 640, b"\0" * 320
        for broken_mic, broken_render in ((mic + b"x", render), (mic[:-1], render),
                                          (mic, render[:-1]), (mic, render + b"x"),
                                          (b"", b"")):
            with self.subTest(lengths=(len(broken_mic), len(broken_render))):
                result, directory = self.invoke("runtime", broken_mic, broken_render)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(json.loads((directory / "report.json").read_text())["status"], "FAIL")
        result, directory = self.invoke("runtime", mic, render, bad_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads((directory / "report.json").read_text())["status"], "FAIL")

    def test_build_identity_and_wrong_source_are_distinct(self):
        result = subprocess.run([str(BRIDGE), "--identity"], check=True, capture_output=True,
                                text=True, timeout=10)
        identity = json.loads(result.stdout)
        transport.validate_build(identity, identity["source_revision"])
        with self.assertRaisesRegex(transport.ContractError, "source identity"):
            transport.validate_build(identity, "0" * 40)
        for key in ("effective_readback", "tuning"):
            bad = copy.deepcopy(identity)
            bad.pop(key)
            with self.assertRaises(transport.ContractError):
                transport.validate_build(bad, bad["source_revision"])
        for name in ("aec_mu", "ns_floor", "limiter_dbfs"):
            bad = copy.deepcopy(identity)
            bad["config"][name] = float("nan")
            with self.assertRaises(transport.ContractError):
                transport.validate_build(bad, bad["source_revision"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--bridge", required=True, type=Path)
    args, remaining = parser.parse_known_args()
    BRIDGE = args.bridge.resolve(strict=True)
    unittest.main(argv=[sys.argv[0], *remaining])
