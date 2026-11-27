#!/usr/bin/env python3
"""Pure tiny F05 transport/metadata tests. No real corpus download or codec call.

The tiny FLAC objects contain STREAMINFO test headers, not encoded speech.
Mock-decoded PCM is explicitly synthetic and cannot pass the public archive pin.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest import mock

import f05_speech_source as f


def streaminfo(pcm: bytes, rate=16000, channels=1, bits=16, frames=None) -> bytes:
    header = bytearray(b'fLaC\x80\x00\x00\x22' + b'\0' * 34)
    count = len(pcm) // 2 if frames is None else frames
    value = (rate << 44) | ((channels - 1) << 41) | ((bits - 1) << 36) | count
    header[18:26] = value.to_bytes(8, 'big')
    header[26:42] = hashlib.md5(pcm).digest()
    return bytes(header) + b'TINY-HEADER-ONLY-NOT-ENCODED-AUDIO'


class Response(io.BytesIO):
    def __init__(self, data, url, status=200, length=None):
        super().__init__(data)
        self.url, self.status = url, status
        self.headers = {} if length is None else {'Content-Length': str(length)}

    def geturl(self):
        return self.url


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='f05-tiny-')
        self.root = Path(self.tmp.name)
        self.plan = f.load_json(f.PLAN)

    def tearDown(self):
        self.tmp.cleanup()

    def names(self):
        return [f'LibriSpeech/dev-clean/{s}/{c}/{s}-{c}-{u:04d}.flac'
                for s in self.plan['selection']['roster'] for c, u in ((10, 0), (2, 12), (2, 2), (2, 1), (2, 0))]

    def tiny_archive(self):
        plan = copy.deepcopy(self.plan)
        data_by_name, pcm_by_name = {}, {}
        for name in self.names():
            # Deterministic fabricated bytes, not generated/listened-to speech.
            value = int(Path(name).stem.split('-')[0]) % 30000
            pcm = value.to_bytes(2, 'little') * 20000
            data_by_name[name], pcm_by_name[name] = streaminfo(pcm), pcm
        data_by_name['LibriSpeech/LICENSE.TXT'] = b'TINY TEST NOTICE - NOT REAL CORPUS\n'
        data_by_name['LibriSpeech/README.TXT'] = b'TEST DOUBLE ONLY\n'
        data_by_name['LibriSpeech/SPEAKERS.TXT'] = ''.join(
            f'{s} | F | dev-clean | 0 | TEST\n' for s in plan['selection']['roster']).encode()
        plan['notices_sha256'] = {name: f.sha256(data_by_name[name]) for name in f.NOTICES}
        archive = self.root / 'tiny.tar.gz'
        with tarfile.open(archive, 'w:gz') as tf:
            for name, data in data_by_name.items():
                info = tarfile.TarInfo(name); info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        data = archive.read_bytes()
        # Private helper tests only. Public read_plan rejects this archive spec.
        plan['archive'] = {'url': 'https://example.invalid/never-fetched', 'bytes': len(data),
                           'sha256': f.sha256(data), 'official_md5': hashlib.md5(data).hexdigest()}
        return archive, plan, pcm_by_name

    def assets(self):
        archive, plan, pcm_by_name = self.tiny_archive()
        output = self.root / 'prepared'; output.mkdir()
        (output / 'contract.json').write_bytes(f.PLAN.read_bytes())
        metadata = f.archive_snapshot(archive, plan, output)
        f.save_json(output / 'selection.json', metadata)
        (output / 'pcm').mkdir()
        for selected in metadata['selection']:
            for original in selected['originals']:
                (output / 'pcm' / (Path(original['member']).stem + '.s16')).write_bytes(pcm_by_name[original['member']])
        for name in ('decoder-version.txt', 'decoder-license.txt'):
            (output / name).write_text('TEST DOUBLE: no real decoder invocation\n')
        f.save_json(output / 'transport.json', {'mode': 'provided', 'attempts': 0, 'wall_seconds': 0, 'archive': plan['archive']})
        (output / 'ATTRIBUTION.txt').write_text(f.ATTRIBUTION)
        rows = f.source_rows(output, metadata, plan, create_windows=True)
        decoder = {'executable': '/synthetic/ffmpeg', 'sha256': '0' * 64, 'decode_wall_seconds': .01,
                   'commands': [f.decode_command('/synthetic/ffmpeg', output / original['file'])
                                for selected in metadata['selection'] for original in selected['originals']],
                   'file_wall_seconds': [{'member': original['member'], 'seconds': .01 / 32}
                                         for selected in metadata['selection'] for original in selected['originals']]}
        receipt = {'study_id': plan['study_id'], 'status': f.STATUS, 'role': plan['role'], 'archive': plan['archive'],
                   'plan_sha256': f.file_hash(f.PLAN), 'sources': rows, 'files_sha256': f.manifest(output, plan['budgets']),
                   'acoustic_runs': 0, 'listening_sessions': 0, 'parameter_searches': 0, 'shipping_authority': False,
                   'prepare_wall_seconds': .1, 'decode_wall_seconds': .01, 'decoded_files': 32,
                   'full_pcm_is_main_asset': True, 'decoder': decoder, 'preparation_directory': str(output)}
        return archive, output, plan, metadata, receipt

    def test_frozen_contract(self):
        f.validate_plan(self.plan)
        self.assertEqual(f.read_plan(f.file_hash(f.PLAN)), self.plan)
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            f.read_plan('0' * 64)

    def test_role_exclusions_and_budget_cannot_be_relaxed(self):
        for section, field, value in [('role', 'training_allowed', True), ('role', 'blind_status', 'BLIND'),
                                      ('role', 'promotion_allowed', True), ('role', 'acoustic_execution_allowed_by_this_contract', True),
                                      ('budgets', 'transport_attempts', 2), ('budgets', 'prepare_wall_seconds', 301),
                                      ('selection', 'quality_selection', True), ('exposure_review', 'excluded_speakers', [])]:
            plan = copy.deepcopy(self.plan); plan[section][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                f.validate_plan(plan)

    def test_metadata_numeric_selection(self):
        selected = f.select_members(list(reversed(self.names())), self.plan)
        self.assertEqual([row[0] for row in selected], f.SELECTED)
        self.assertEqual(selected[0][1], [f'LibriSpeech/dev-clean/2412/2/2412-2-{u:04d}.flac' for u in (0, 1, 2, 12)])
        self.assertTrue(set(f.EXCLUDED).isdisjoint(row[0] for row in selected))

    def test_missing_roster_short_speaker_and_numeric_alias(self):
        names = self.names()
        invalid = [names[5:], [n for n in names if not ('/2412/' in n and n.endswith(('0000.flac', '0001.flac')))],
                   names + [names[0]], names + ['LibriSpeech/dev-clean/02412/2/02412-2-0000.flac'],
                   names + ['elsewhere/2412.flac']]
        for sample in invalid:
            with self.subTest(sample=sample[-1]), self.assertRaises(ValueError):
                f.select_members(sample, self.plan)

    def test_archive_path_types_and_sizes(self):
        for name in ('/absolute', '../escape', 'LibriSpeech/../escape', 'LibriSpeech//a',
                     'LibriSpeech/./a', 'LibriSpeech\\a', '.', 'Other/a', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                f.safe_member(tarfile.TarInfo(name), self.plan['budgets'])
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE):
            info = tarfile.TarInfo('LibriSpeech/link'); info.type = kind
            with self.assertRaisesRegex(ValueError, 'links/special'):
                f.safe_member(info, self.plan['budgets'])
        info = tarfile.TarInfo('LibriSpeech/huge'); info.size = 5000001
        with self.assertRaisesRegex(ValueError, 'byte bound'):
            f.safe_member(info, self.plan['budgets'])

    def test_native_reader_reused_and_rejects_wrong_format(self):
        pcm = b'\x01\0' * 10
        self.assertEqual(f.native_metadata(streaminfo(pcm))['frames'], 10)
        for kwargs in ({'rate': 48000}, {'channels': 2}, {'bits': 24}, {'frames': 0}, {'frames': 960001}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                f.native_metadata(streaminfo(pcm, **kwargs))
        bad = bytearray(streaminfo(pcm)); bad[26:42] = b'\0' * 16
        for data in (b'fLaC', bytes(bad), b'RIFF' + bytes(bad)[4:]):
            with self.assertRaises(ValueError):
                f.native_metadata(data)

    def test_fixed_archive_checked_before_any_decoder(self):
        archive, _plan, _pcm = self.tiny_archive()
        with mock.patch.object(f, 'decode_sources') as decode:
            with self.assertRaisesRegex(ValueError, 'byte count'):
                f.prepare(archive, self.root / 'new', self.plan, {}, 'ffmpeg', time.monotonic())
            decode.assert_not_called()

    def test_archive_digest_and_local_symlink(self):
        archive, plan, _pcm = self.tiny_archive()
        self.assertEqual(f.check_archive(archive, plan['archive']), plan['archive'])
        spec = {**plan['archive'], 'sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'digest'):
            f.check_archive(archive, spec)
        link = self.root / 'link'; link.symlink_to(archive)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            f.check_archive(link, plan['archive'])

    def test_download_exact_bytes_once_no_real_network(self):
        data = b'TINY TRANSPORT ONLY'
        spec = {'url': 'https://example.invalid/no-network', 'bytes': len(data), 'sha256': f.sha256(data),
                'official_md5': hashlib.md5(data).hexdigest()}
        opener = mock.Mock(); opener.open.return_value = Response(data, spec['url'], length=len(data))
        record = f.fetch_archive(self.root / 'tiny', spec, opener)
        self.assertEqual(record['attempts'], 1)
        opener.open.assert_called_once_with(spec['url'], timeout=30)

    def test_transport_failures_no_retry_or_alternate(self):
        data = b'ABCD'
        spec = {'url': 'https://example.invalid/no-network', 'bytes': 4, 'sha256': f.sha256(data),
                'official_md5': hashlib.md5(data).hexdigest()}
        for ordinal, response in enumerate((Response(b'ABCDE', spec['url']), Response(b'AB', spec['url']),
                                             Response(data, 'https://other.invalid'), Response(data, spec['url'], status=206),
                                             Response(data, spec['url'], length=5), Response(b'WXYZ', spec['url']))):
            opener = mock.Mock(); opener.open.return_value = response
            with self.subTest(ordinal=ordinal), self.assertRaises(ValueError):
                f.fetch_archive(self.root / str(ordinal), spec, opener)
            self.assertEqual(opener.open.call_count, 1)
            self.assertTrue((self.root / str(ordinal)).exists())
        with self.assertRaisesRegex(ValueError, 'redirect'):
            f.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid')

    def test_archive_notice_and_expansion_bounds(self):
        archive, plan, _pcm = self.tiny_archive()
        for section, key, value in [('notices_sha256', 'LibriSpeech/LICENSE.TXT', '0' * 64),
                                    ('budgets', 'archive_members', 1), ('budgets', 'expanded_bytes', 1)]:
            altered = copy.deepcopy(plan); altered[section][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                f.archive_snapshot(archive, altered)

    def test_full_assets_and_cross_utterance_spans_without_codec(self):
        _archive, output, plan, metadata, receipt = self.assets()
        with mock.patch.object(f.subprocess, 'run', side_effect=AssertionError('no codec permitted')):
            f.validate_assets(output, metadata, plan, receipt)
        self.assertEqual(len(receipt['sources']), 8)
        self.assertEqual(sum(len(s['originals']) for s in receipt['sources']), 32)
        row = receipt['sources'][0]
        self.assertTrue(row['crosses_original_utterances'])
        self.assertEqual([span['window_frames'] for span in row['window_source_spans']],
                         [[0, 20000], [20000, 40000], [40000, 60000], [60000, 64000]])
        self.assertEqual(row['window_source_spans'][-1]['source_frames'], [0, 4000])

    def test_pcm_window_notice_and_hidden_file_tampering(self):
        _archive, output, plan, metadata, receipt = self.assets()
        for relative in (receipt['sources'][0]['originals'][0]['pcm_file'], receipt['sources'][0]['window_file'], 'LICENSE.TXT'):
            path = output / relative; data = path.read_bytes(); path.write_bytes(b'X' + data[1:])
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                f.validate_assets(output, metadata, plan, receipt)
            path.write_bytes(data)
        hidden = output / 'pcm' / 'source-receipt.json'; hidden.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'closure'):
            f.validate_assets(output, metadata, plan, receipt)

    def test_short_window_and_native_md5_fail_no_reselection(self):
        pcm = b'\1\0' * 3
        original = {'member': 'a', 'frames': 3, 'native_pcm_md5': hashlib.md5(pcm).hexdigest()}
        with self.assertRaisesRegex(ValueError, 'no padding/reselection'):
            f.window_bytes([original], {'a': pcm}, 4)
        with self.assertRaisesRegex(ValueError, 'PCM MD5'):
            f.window_bytes([original], {'a': b'\2\0' * 3}, 3)

    def test_receipt_role_budget_and_decoder_command_tampering(self):
        _archive, output, plan, metadata, receipt = self.assets()
        for field, value in [('status', 'PASS_ACOUSTIC'), ('decoded_files', 31), ('prepare_wall_seconds', 301),
                             ('decode_wall_seconds', 181), ('prepare_wall_seconds', float('nan')),
                             ('acoustic_runs', 1), ('full_pcm_is_main_asset', False)]:
            altered = copy.deepcopy(receipt); altered[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                f.validate_assets(output, metadata, plan, altered)
        altered = copy.deepcopy(receipt); altered['decoder']['commands'][0].extend(['-ar', '8000'])
        with self.assertRaisesRegex(ValueError, 'fixed native'):
            f.validate_assets(output, metadata, plan, altered)
        altered = copy.deepcopy(receipt); altered['role']['optimizer_selection_allowed'] = True
        with self.assertRaisesRegex(ValueError, 'role'):
            f.validate_assets(output, metadata, plan, altered)
        altered = copy.deepcopy(receipt); altered['decoder']['file_wall_seconds'][0]['seconds'] = 21
        with self.assertRaisesRegex(ValueError, 'per-file'):
            f.validate_assets(output, metadata, plan, altered)

    def test_duplicate_json_and_nonfinite_input(self):
        for ordinal, text in enumerate(('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}')):
            path = self.root / f'{ordinal}.json'; path.write_text(text)
            with self.assertRaises(ValueError):
                f.load_json(path)

    def test_wall_timer_is_hard_and_restored(self):
        before = signal.getsignal(signal.SIGALRM)
        with self.assertRaisesRegex(TimeoutError, 'wall budget'):
            with f.wall_limit(1, 'tiny-test'):
                time.sleep(2)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertEqual(signal.getsignal(signal.SIGALRM), before)

    def test_failures_preserved_and_no_success_reuse(self):
        archive = self.root / 'wrong.tar'; archive.write_bytes(b'TINY WRONG ARCHIVE')
        output = self.root / 'failed'
        argv = ['f05', 'prepare', '--archive', str(archive), '--output', str(output), '--code-revision', '0' * 40,
                '--plan-sha256', f.file_hash(f.PLAN)]
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(f, 'code_identity', return_value={}), \
             mock.patch.object(f, 'decode_sources') as decode, mock.patch('builtins.print'):
            self.assertEqual(f.main(), 1)
            decode.assert_not_called()
            failure = (output / 'source-failure.json').read_bytes()
            self.assertEqual(json.loads(failure)['status'], 'FAIL_SOURCE_PREPARATION')
            self.assertFalse((output / 'source-receipt.json').exists())
            self.assertEqual(f.main(), 1)
            self.assertEqual((output / 'source-failure.json').read_bytes(), failure)

    def test_real_git_identity_rejects_wrong_revision(self):
        with self.assertRaisesRegex(ValueError, 'exact execution commit'):
            f.code_identity('main')

    def test_process_failure_preserves_bounded_stderr_and_payload_hash(self):
        archive = self.root / 'input'; archive.write_bytes(b'TEST ONLY')
        output = self.root / 'failed-process'
        argv = ['f05', 'prepare', '--archive', str(archive), '--output', str(output), '--code-revision', '0' * 40,
                '--plan-sha256', f.file_hash(f.PLAN)]
        error = subprocess.CalledProcessError(7, ['SYNTHETIC-DECODER-NEVER-RUN'], output=b'partial', stderr=b'decoder diagnostic')
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(f, 'code_identity', return_value={}), \
             mock.patch.object(f, 'prepare', side_effect=error), mock.patch('builtins.print'):
            self.assertEqual(f.main(), 1)
        failure = f.load_json(output / 'source-failure.json')['child_process']
        self.assertEqual(failure['returncode'], 7)
        self.assertEqual(failure['stderr_tail'], 'decoder diagnostic')
        self.assertEqual(failure['stdout_sha256'], f.sha256(b'partial'))


if __name__ == '__main__':
    unittest.main()
