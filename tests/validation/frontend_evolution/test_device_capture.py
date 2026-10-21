"""Synthetic contract fixtures only; no runner, recording or acoustic qualification claims."""
from pathlib import Path
import copy
import csv
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.codex_assets import device_capture as dc
from tools.codex_assets import device_replay as dr


def fixture(root: Path) -> None:
    n = 320000  # Minimum 20s synthetic schema-v2 test data; NOT physical evidence.
    s = dict(schema_version=2, complete=True, frame_validation=0, sample_rate=16000, pcm_bits=16,
             raw_ref_channels=2, seconds=20, active_profile=1, requested_profile=1, scene='quiet',
             discontinuities=0, execution=0, cleanup=0, capture_error=0, deadline_misses=0,
             ref_delay_samples=20, input_samples=n, output_samples=n, frame_count=n // 128 + n // 256,
             near_activity='human-not-verified', acoustic_verdict='pending')
    (root / 'session.json').write_text(json.dumps(s))
    for name, channels, data in (('mic.wav', 2, struct.pack('<hh', 100, 200) * n),
                                 ('ref_raw.wav', 2, b'\x00' * n * 4),
                                 ('ref_used.wav', 1, b'\x00' * n * 2), ('output.wav', 1, b'\x00' * n * 2)):
        with wave.open(str(root / name), 'wb') as f:
            f.setparams((channels, 2, 16000, 0, 'NONE', 'not compressed')); f.writeframes(data)
    with (root / 'frames.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(dc.FRAME_FIELDS)
        for stage, hop in ((0, 128), (1, 256)):
            for j in range(n // hop):
                pts = 1000000 + j * hop * 1000000 // 16000
                w.writerow((pts, pts, 0, stage, j + 1, j * hop, hop, int(stage == 1)))
    with (root / 'events.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(('mono_us', 'event', 'value'))
        w.writerow((1000000, 'scene_start', 0)); w.writerow((21000000, 'scene_end', 0))


class IntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory(prefix='ap-device-contract-')
        cls.original = Path(cls.storage.name) / 'original'; cls.original.mkdir(); fixture(cls.original)

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ap-device-case-')
        self.root = Path(self.tmp.name); shutil.copytree(self.original, self.root, dirs_exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, **fields):
        p = self.root / 'session.json'; s = json.loads(p.read_text()); s.update(fields); p.write_text(json.dumps(s))

    def frames(self, index, field, value):
        p = self.root / 'frames.csv'
        with p.open(newline='') as f:
            rows = list(csv.DictReader(f))
        rows[index][field] = str(value)
        with p.open('w', newline='') as f:
            w = csv.DictWriter(f, dc.FRAME_FIELDS); w.writeheader(); w.writerows(rows)

    def test_valid_explicit_pairing_and_windows(self):
        c = dc.capture(self.root); c['case_id'] = 'synthetic-unit-fixture'
        self.assertEqual(dc.summary(c)['paired_samples'], 320000)
        self.assertEqual(dr.window(c, 4, 6, 320000, 160), (64000, 96000))
        self.assertIsNone(dc.levels(c['ref'])[0]['rms_dbfs'])

    def test_incomplete_type_and_promotion_are_rejected(self):
        original = (self.root / 'session.json').read_bytes()
        for fields in (dict(complete=False), dict(frame_validation=False), dict(sample_rate=True),
                       dict(deadline_misses=1), dict(active_profile=2), dict(near_activity='verified'),
                       dict(acoustic_verdict='pass'), dict(ref_delay_samples=1601)):
            (self.root / 'session.json').write_bytes(original); self.session(**fields)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                dc.capture(self.root)

    def test_truncated_payload_and_riff_rejected(self):
        p = self.root / 'mic.wav'; original = p.read_bytes()
        p.write_bytes(original[:-4])
        with self.assertRaises(ValueError): dc.wav(p, 2)
        p.write_bytes(original + b'\x00\x00')
        with self.assertRaises(ValueError): dc.wav(p, 2)

    def test_duplicate_wav_chunk_rejected(self):
        p = self.root / 'mic.wav'; b = p.read_bytes(); extra = b[12:36]
        b = b[:4] + struct.pack('<I', len(b) + len(extra) - 8) + b[8:] + extra
        p.write_bytes(b)
        with self.assertRaisesRegex(ValueError, 'duplicate'): dc.wav(p, 2)

    def test_wrong_channels_and_partial_samples_rejected(self):
        p = self.root / 'mic.wav'
        with self.assertRaises(ValueError): dc.wav(p, 1)
        b = bytearray(p.read_bytes()); b[-1:] = b''; struct.pack_into('<I', b, 4, len(b) - 8)
        struct.pack_into('<I', b, 40, len(b) - 44); b += b'\x00'; struct.pack_into('<I', b, 4, len(b) - 8)
        p.write_bytes(b)
        with self.assertRaises(ValueError): dc.wav(p, 2)

    def test_sequence_offset_pts_epoch_and_output_valid(self):
        original = (self.root / 'frames.csv').read_bytes()
        for index, field, value in ((1, 'seq', 7), (1, 'file_sample_offset', 0), (1, 'input_pts_us', 2000000),
                                    (1, 'epoch', 1), (2600, 'output_valid', 0), (1, 'stage', 8)):
            (self.root / 'frames.csv').write_bytes(original); self.frames(index, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError): dc.capture(self.root)

    def test_used_reference_and_scene_end_rejected(self):
        p = self.root / 'ref_used.wav'; b = bytearray(p.read_bytes()); b[44] = 1; p.write_bytes(b)
        with self.assertRaisesRegex(ValueError, 'reference'): dc.capture(self.root)
        shutil.copyfile(self.original / 'ref_used.wav', p)
        (self.root / 'events.csv').write_text('mono_us,event,value\n1000000,scene_start,0\n')
        with self.assertRaises(ValueError): dc.capture(self.root)

    def test_symlink_and_traversal_rejected(self):
        for name in ('../outside', '/tmp/file', 'x/../session.json', 'x\\y'):
            with self.subTest(name=name), self.assertRaises(ValueError): dc.safe_file(self.root, name)
        p = self.root / 'mic.wav'; p.unlink(); p.symlink_to(self.original / 'mic.wav')
        with self.assertRaises(ValueError): dc.capture(self.root)

    def test_strict_json_duplicate_nonfinite(self):
        for text in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'[]'):
            with self.subTest(text=text), self.assertRaises(ValueError): dc.strict_json(text)

    def test_exact_frozen_plan_and_execution_budget(self):
        p, lock = dc.plan(); self.assertEqual(len(lock), 119); self.assertEqual(len(p['cases']), 16)
        self.assertEqual(sum(len(dc.arm_set(s)) for s in dc.SCENES) * 2, 70)
        self.assertEqual(dc.sha((dc.PLAN.parent / p['input_lock']).read_bytes()), p['input_lock_sha256'])

    def test_plan_authority_tamper_rejected(self):
        p = json.loads(dc.PLAN.read_text())
        shutil.copyfile(dc.PLAN.parent / p['input_lock'], self.root / p['input_lock'])
        target = self.root / 'plan.json'
        for key, value in (('promotion_allowed', True), ('training_allowed', True), ('data_role', 'validation'),
                           ('fixed_execution_count', 71), ('cases', p['cases'][:-1]), ('reference_delay_diagnostic_ms', 2)):
            bad = copy.deepcopy(p); bad[key] = value; target.write_text(json.dumps(bad))
            with self.subTest(key=key), self.assertRaises(ValueError): dc.plan(target)

    def test_output_existing_source_or_input_rejected_before_execution(self):
        for out in (ROOT / 'new-forbidden-output', self.root, self.root / 'nested'):
            with self.subTest(output=out), self.assertRaises(ValueError): dr.execute(self.root, out, dry_run=True)

    def test_false_success_bool_exit_wrong_config_or_count(self):
        good = dict(status='success', exit_code=0, samples=160, config_sha256='a' * 64)
        dr.arm_status(good, 160, 'a' * 64)
        for key, value in (('status', 'failed'), ('exit_code', False), ('exit_code', 1),
                           ('samples', 159), ('config_sha256', 'b' * 64)):
            bad = {**good, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError): dr.arm_status(bad, 160, 'a' * 64)

    def test_binding_mutation_missing_and_escape(self):
        p = self.root / 'binding.json'; p.write_text('{"x":1}')
        b = dr.binding(self.root, p); self.assertEqual(dr.verify_binding(self.root, b), p)
        p.write_text('{"x":2}')
        with self.assertRaises(ValueError): dr.verify_binding(self.root, b)
        b['path'] = '../binding.json'
        with self.assertRaises(ValueError): dr.verify_binding(self.root, b)


class CommandReceiptTests(unittest.TestCase):
    def test_excess_output_is_bounded_recorded_and_rejected(self):
        with tempfile.TemporaryDirectory(prefix='ap-command-receipt-') as tmp:
            directory = Path(tmp)
            result = subprocess.CompletedProcess(['fixture'], 1, 'x' * (1024 * 1024 + 1), 'failure')
            with patch.object(dr.subprocess, 'run', return_value=result), self.assertRaisesRegex(ValueError, 'bound'):
                dr.run_logged(['fixture'], directory, 0)
            receipt = json.loads((directory / 'command-000.json').read_text())
            self.assertEqual(receipt['command'], ['fixture'])
            self.assertEqual(receipt['exit_code'], 1)
            self.assertTrue(receipt['output_truncated'])
            self.assertFalse(receipt['timed_out'])
            self.assertEqual(receipt['stderr_characters'], 7)
            self.assertEqual(len(receipt['stdout']) + len(receipt['stderr']), 1024 * 1024)

    def test_timeout_partial_bytes_recorded_and_propagated(self):
        with tempfile.TemporaryDirectory(prefix='ap-command-receipt-') as tmp:
            directory = Path(tmp)
            error = subprocess.TimeoutExpired(['fixture'], 2, output=b'partial\xff', stderr=b'error')
            with patch.object(dr.subprocess, 'run', side_effect=error), self.assertRaises(subprocess.TimeoutExpired):
                dr.run_logged(['fixture'], directory, 0, timeout=2)
            receipt = json.loads((directory / 'command-000.json').read_text())
            self.assertTrue(receipt['timed_out'])
            self.assertIsNone(receipt['exit_code'])
            self.assertEqual(receipt['timeout_seconds'], 2)
            self.assertEqual(receipt['stdout'], 'partial\ufffd')
            self.assertEqual(receipt['stderr'], 'error')

    def test_spawn_error_recorded_and_propagated(self):
        with tempfile.TemporaryDirectory(prefix='ap-command-receipt-') as tmp:
            directory = Path(tmp)
            with patch.object(dr.subprocess, 'run', side_effect=FileNotFoundError('missing executable')):
                with self.assertRaises(FileNotFoundError):
                    dr.run_logged(['fixture'], directory, 0)
            receipt = json.loads((directory / 'command-000.json').read_text())
            self.assertEqual(receipt['execution_error'], 'missing executable')
            self.assertIsNone(receipt['exit_code'])
            self.assertFalse(receipt['timed_out'])


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory(prefix='ap-device-runner-')
        cls.root = Path(cls.storage.name); b = cls.root / 'build'
        cmds = [
            ['cmake', '-S', str(ROOT), '-B', str(b), '-DAP_BUILD_TESTS=OFF', '-DAP_BUILD_BENCH=OFF'],
            ['cmake', '--build', str(b), '--target', 'audio_pipeline', '-j', '2'],
            ['cc', *dr.FLAGS, '-I', str(ROOT / 'include'), '-I', str(b / 'generated'), str(dr.RUNNER_SOURCE),
             str(b / 'libaudio_pipeline.a'), '-lm', '-lpthread', '-o', str(cls.root / 'runner')]]
        for cmd in cmds:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0: raise AssertionError(r.stdout + r.stderr)

    @classmethod
    def tearDownClass(cls): cls.storage.cleanup()

    def run_arm(self, mode, mic: bytes, ref: bytes):
        with tempfile.TemporaryDirectory(prefix='ap-device-native-') as tmp:
            d = Path(tmp); (d / 'mic.pcm').write_bytes(mic); (d / 'ref.pcm').write_bytes(ref)
            r = subprocess.run([str(self.root / 'runner'), mode, str(d / 'mic.pcm'), str(d / 'ref.pcm'),
                                str(d / 'output.pcm'), str(d / 'metrics.jsonl')], capture_output=True, text=True)
            return r.returncode, (d / 'output.pcm').read_bytes() if (d / 'output.pcm').exists() else b''

    def test_config_isolation_and_default_control(self):
        modes = ('default', 'sync-default-control', 'tracked1', 'fixed1', 'tracked1-no-drift',
                 'bf-isolated', 'ns-isolated', 'agc-isolated')
        cfg = {}
        for mode in modes:
            r = subprocess.run([str(self.root / 'runner'), '--describe', mode], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0); cfg[mode] = dc.strict_json(r.stdout.encode())
        for mode in modes: dr.check_config(cfg[mode], mode, cfg['default'])
        self.assertEqual(cfg['default'], cfg['sync-default-control'])
        bad = dict(cfg['tracked1']); bad['aec_mu'] = 0.8
        with self.assertRaises(ValueError): dr.check_config(bad, 'tracked1', cfg['default'])

    def test_full_silence_and_native_eof_negatives(self):
        mic, ref = b'\x00' * 640, b'\x00' * 320
        exit_code, out = self.run_arm('default', mic, ref)
        self.assertEqual(exit_code, 0); self.assertEqual(len(out), 320)
        for m, r in ((mic[:-1], ref), (mic, ref[:-1]), (mic, ref + b'\x00'), (b'', b''), (mic + b'\x00', ref)):
            with self.subTest(mic=len(m), ref=len(r)):
                self.assertNotEqual(self.run_arm('default', m, r)[0], 0)
        self.assertNotEqual(self.run_arm('unknown-mode', mic, ref)[0], 0)


if __name__ == '__main__':
    unittest.main()
