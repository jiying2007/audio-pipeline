#!/usr/bin/env python3
"""Tiny transport metadata tests; no original audio, decoder, SDK or compiler."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import zipfile

import speech_pinned_snapshot as recovery
import speech_source_cache_profiles as profiles
import speech_source_cas as cas

P = profiles.SPATIAL
COMMIT = '1' * 40  # Control-flow test double only, never a source admission.


class ProfileTests(unittest.TestCase):
    def test_none_reads_original_default_constants_at_call_time(self):
        with mock.patch.object(recovery,'ORIGIN_ARTIFACT',123), \
             mock.patch.object(recovery,'ORIGIN_ZIP_SHA256','2'*64):
            self.assertEqual(recovery._settings(None).artifact_id,123)
            self.assertEqual(recovery._settings(None).zip_sha256,'2'*64)
            self.assertEqual(recovery._settings(P).artifact_id,14417923975)

    def test_only_closed_object_and_none_are_accepted(self):
        self.assertIsNone(profiles.select(None))
        self.assertIs(profiles.select(P.name), P)
        for value in ('offset0', 'offset16', {}, replace(P), COMMIT):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ValueError):
                    recovery._settings(value)
        with self.assertRaises(FrozenInstanceError):
            P.offset = 0

    def test_original_contract_bytes_and_two_checkers_stay_distinct(self):
        old = recovery.original_source_policy()
        new = recovery.original_source_policy(profile=P)
        self.assertEqual(old['bound_source_sha256'], recovery.ADMITTED_SOURCE_SHA256)
        self.assertEqual(new['bound_source_sha256'], P.admitted_source_sha256)
        self.assertNotEqual(old['source_id'], new['source_id'])
        import speech_spatial_weights
        with mock.patch.object(recovery, 'source_check', return_value={'old':True}) as old_check, \
             mock.patch.object(speech_spatial_weights, 'source_check', return_value={'new':True}) as new_check:
            self.assertEqual(recovery.check_source(Path('fixture')), {'old':True})
            self.assertEqual(recovery.check_source(Path('fixture'),profile=P), {'new':True})
            old_check.assert_called_once_with(Path('fixture'))
            new_check.assert_called_once_with(Path('fixture'))

    def test_original_spatial_role_and_cross_profile_receipts_rejected_without_audio(self):
        import speech_spatial_weights
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = {'source_id':P.source_id,'status':'SOURCE_ONLY_NOT_ACOUSTIC_EVIDENCE',
                'shipping_authority':False,'url':recovery.speech_source.URL,
                'archive_sha256':recovery.ORIGIN_ARCHIVE_SHA256,'archive_md5':recovery.speech_source.MD5,
                'archive_bytes':337926286,'plan_sha256':P.plan_sha256,
                'speaker_selection':[{'role':'optimizer-training'}],'files_sha256':{}}
            (root/'source-receipt.json').write_text(json.dumps(record))
            with mock.patch.object(recovery.subprocess,'Popen',side_effect=AssertionError('process forbidden')):
                with self.assertRaisesRegex(ValueError,'admitted source bytes changed'):
                    speech_spatial_weights.source_check(root)
                record['source_id']='librispeech-dev-clean-fe03'
                (root/'source-receipt.json').write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError,'source authority'):
                    speech_spatial_weights.source_check(root)

    def test_parent_receipt_cannot_cross_profile(self):
        good = {'snapshot_profile':P.name,'source_speaker_offset':8,'source_id':P.source_id,
                'source_admission_sha256':P.admission_sha256,'source_plan_sha256':P.plan_sha256}
        recovery.check_profile_receipt(good,P)
        for key,value in (('snapshot_profile',None),('source_speaker_offset',0),
                          ('source_id','librispeech-dev-clean-fe03'),('source_plan_sha256','0'*64)):
            bad={**good,key:value}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'PROFILE_IDENTITY'):
                recovery.check_profile_receipt(bad,P)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.archive=self.root/'cache.zip'; self.output=self.root/'source'
        self.transfer=self.root/'transfer.json'; self.failure=self.root/'cache-failure.json'
        self.patch=mock.patch.object(recovery,'strict_source_commit'); self.patch.start()
        self.addCleanup(self.patch.stop)

    def run_metadata(self):
        return {'id':P.verify_run,'head_sha':P.origin_main,'head_branch':'main',
                'event':'push','conclusion':'success'}

    def artifact_metadata(self):
        return {'id':P.artifact_id,'name':P.artifact_name,'size_in_bytes':P.zip_bytes,
                'digest':'sha256:'+P.zip_sha256,'expired':False,
                'workflow_run':{'id':P.verify_run,'head_sha':P.origin_main}}

    def profile_record(self, acquisition='protected-artifact-cache'):
        return {'source_commit':COMMIT,'decision':recovery.DECISION,'acquisition_path':acquisition,
                'snapshot_profile':P.name,'source_speaker_offset':8,'source_id':P.source_id,
                'source_admission_sha256':P.admission_sha256,'source_plan_sha256':P.plan_sha256,
                'original_source_artifact_zip_sha256':P.zip_sha256}

    def acquire(self):
        return recovery.acquire_source_worker(self.archive,self.output,self.transfer,self.failure,COMMIT,profile=P)

    def test_cache_fixed_endpoints_profile_and_no_official_on_hit(self):
        expected=self.profile_record()
        with mock.patch.object(recovery,'cache_api',side_effect=[self.run_metadata(),self.artifact_metadata(),None]) as api, \
             mock.patch.object(recovery,'restore',return_value=expected) as restore, \
             mock.patch.object(recovery,'reacquire_official') as official:
            self.assertEqual(self.acquire(),expected)
            restore.assert_called_once_with(self.archive,self.output,self.transfer,COMMIT,profile=P)
            official.assert_not_called()
            self.assertEqual([c.args[0] for c in api.call_args_list],[
                '/actions/runs/'+str(P.verify_run),'/actions/artifacts/'+str(P.artifact_id),
                '/actions/artifacts/'+str(P.artifact_id)+'/zip'])
        self.assertFalse(self.archive.exists())

    def test_wrong_branch_event_fullrun_and_head_rejected_before_download(self):
        for key,value in (('head_branch','feature'),('head_branch',None),('event','pull_request'),
                          ('conclusion','failure'),('conclusion',None),('head_sha','0'*40),('id',1)):
            with self.subTest(key=key,value=value):
                meta={**self.run_metadata(),key:value}
                with mock.patch.object(recovery,'cache_api',return_value=meta) as api:
                    with self.assertRaisesRegex(recovery.CacheFailure,'RUN_IDENTITY_REJECTED'):
                        recovery.restore_cache(self.archive,self.output,self.transfer,COMMIT,profile=P)
                    self.assertEqual(api.call_count,1)
                self.assertFalse(self.archive.exists())

    def test_expired_missing_expired_and_offset0_artifact_are_rejected(self):
        changes=[('expired',True),('expired',None),('id',recovery.ORIGIN_ARTIFACT),
                 ('size_in_bytes',recovery.ORIGIN_ZIP_BYTES),('digest','sha256:'+recovery.ORIGIN_ZIP_SHA256),
                 ('workflow_run',{'id':recovery.ORIGIN_VERIFY_RUN,'head_sha':recovery.ORIGIN_MAIN})]
        for key,value in changes:
            with self.subTest(key=key):
                artifact={**self.artifact_metadata(),key:value}
                with mock.patch.object(recovery,'cache_api',side_effect=[self.run_metadata(),artifact]) as api:
                    with self.assertRaises(recovery.CacheFailure):
                        recovery.restore_cache(self.archive,self.output,self.transfer,COMMIT,profile=P)
                    self.assertEqual(api.call_count,2)

    def test_wrong_zip_size_precedes_cas_and_source_checks(self):
        self.archive.write_bytes(b'not-original')
        with mock.patch.object(cas,'copy_source') as copy_source, mock.patch.object(recovery,'check_source') as check:
            with self.assertRaisesRegex(ValueError,'SIZE_WRONG'):
                recovery.restore(self.archive,self.output,self.transfer,COMMIT,profile=P)
            copy_source.assert_not_called(); check.assert_not_called()

    def test_wrong_exact_size_zip_hash_precedes_cas(self):
        with self.archive.open('wb') as stream:
            stream.truncate(P.zip_bytes)
        with mock.patch.object(cas,'copy_source') as copy_source:
            with self.assertRaisesRegex(ValueError,'ZIP_SHA256_CHANGED'):
                recovery.restore(self.archive,self.output,self.transfer,COMMIT,profile=P)
            copy_source.assert_not_called()

    def test_cache_failure_retained_and_official_fallback_has_no_github_token(self):
        def official(output,transfer,commit,*,cache_failure,profile):
            self.assertIs(profile,P); self.assertEqual(cache_failure,self.failure)
            self.assertNotIn('GH_TOKEN',os.environ); self.assertNotIn('GITHUB_TOKEN',os.environ)
            record=self.profile_record('official-original-archive')
            record['cache_failure_receipt_sha256']=recovery.sha256_file(cache_failure)
            output.mkdir(); (output/'source-receipt.json').write_text('{}\n')
            transfer.write_text(json.dumps(record)); return record
        with mock.patch.dict(os.environ,{'GH_TOKEN':'tiny-only','GITHUB_TOKEN':'tiny-only'}), \
             mock.patch.object(recovery,'restore_cache',side_effect=recovery.CacheFailure('PINNED_CACHE_RUN_UNAVAILABLE')), \
             mock.patch.object(recovery,'reacquire_official',side_effect=official), \
             mock.patch.object(recovery,'check_source') as check:
            result=self.acquire()
            check.assert_called_once_with(self.output,profile=P)
            self.assertEqual(os.environ['GH_TOKEN'],'tiny-only')
        failure=json.loads(self.failure.read_text())
        self.assertEqual(failure['snapshot_profile'],P.name)
        self.assertEqual(failure['original_source_artifact_id'],P.artifact_id)
        self.assertEqual(result['cache_failure_receipt_sha256'],recovery.sha256_file(self.failure))

    def test_official_same_archive_calls_original_offset8_and_preserves_auth_strip(self):
        with self.archive.open('wb') as stream: stream.truncate(337926286)
        def acquire(archive,data,offset):
            self.assertEqual(offset,8)
            self.assertNotIn('GH_TOKEN',os.environ); self.assertNotIn('GITHUB_TOKEN',os.environ)
            data.mkdir()
        with mock.patch.dict(os.environ,{'GH_TOKEN':'tiny-only','GITHUB_TOKEN':'tiny-only'}), \
             mock.patch.object(recovery,'sha256_file',side_effect=lambda p:recovery.ORIGIN_ARCHIVE_SHA256 if p==self.archive else
                  hashlib.sha256(p.read_bytes()).hexdigest()), \
             mock.patch.object(recovery.speech_source,'acquire',side_effect=acquire) as decode, \
             mock.patch.object(recovery,'publish_source',return_value={}) as publish:
            recovery.reacquire_official(self.output,self.transfer,COMMIT,archive=self.archive,profile=P)
            self.assertEqual(decode.call_count,1)
            self.assertIs(publish.call_args.kwargs['profile'],P)

    def test_worker_profile_and_original_1800_budget_propagation(self):
        def worker(command,output,remaining,**kwargs):
            self.assertEqual(command[-2:],['--profile',P.name])
            self.assertIn('--acquire-worker',command)
            self.assertEqual(remaining,1797)
            output.mkdir(); (output/'source-receipt.json').write_text('{}\n')
            self.transfer.write_text(json.dumps(self.profile_record()))
            return True
        with mock.patch.object(recovery.time,'monotonic',side_effect=[100,103,104]), \
             mock.patch.object(recovery.stage_budget,'run_bounded',side_effect=worker) as run:
            recovery.acquire_source(self.archive,self.output,self.transfer,self.failure,COMMIT,profile=P)
            self.assertEqual(run.call_count,1)
        self.assertEqual(recovery.CACHE_BUDGET_SECONDS,600)
        self.assertEqual(recovery.stage_budget.DEADLINE_SECONDS,1800)

    def test_cache_late_readback_is_rejected(self):
        with mock.patch.object(recovery,'cache_api',side_effect=[self.run_metadata(),self.artifact_metadata(),None]), \
             mock.patch.object(recovery,'restore',return_value=self.profile_record()), \
             mock.patch.object(recovery.time,'monotonic',side_effect=[0,1,601]):
            with self.assertRaisesRegex(recovery.CacheFailure,'WALL_DEADLINE'):
                recovery.restore_cache(self.archive,self.output,self.transfer,COMMIT,profile=P)


class CasTests(unittest.TestCase):
    def setUp(self):
        self.reader=cas.transport_reader()

    def test_fixed_inner_sidecar_identity_and_missing_fields(self):
        good={'schema':self.reader.SCHEMA,'authority':'BYTE_TRANSPORT_ONLY',
            'execution_source':P.origin_main,'run_id':str(P.verify_run),
            'manifest_sha256':P.manifest_sha256,'archive_sha256':P.inner_sha256,
            'archive_bytes':P.inner_bytes,'files':3486,'unique_blobs':1347,
            'logical_bytes':936047672,'unique_bytes':779123123,
            'equivalent_regular_zip_bytes':531396157,'wire_or_billing_measurement':False}
        cas.validate_sidecar(good,self.reader)
        for key,value in (('archive_sha256','0'*64),('archive_bytes',1),
                          ('manifest_sha256','0'*64),('run_id','1'),
                          ('execution_source',recovery.ORIGIN_MAIN)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'PINNED_IDENTITY'):
                cas.validate_sidecar({**good,key:value},self.reader)
        missing=dict(good); missing.pop('archive_sha256')
        with self.assertRaisesRegex(ValueError,'SIDECAR_FIELDS'):
            cas.validate_sidecar(missing,self.reader)

    def test_truncated_inner_bytes_rejected_before_source_publication(self):
        good={'schema':self.reader.SCHEMA,'authority':'BYTE_TRANSPORT_ONLY',
            'execution_source':P.origin_main,'run_id':str(P.verify_run),
            'manifest_sha256':P.manifest_sha256,'archive_sha256':P.inner_sha256,
            'archive_bytes':P.inner_bytes,'files':3486,'unique_blobs':1347,
            'logical_bytes':936047672,'unique_bytes':779123123,
            'equivalent_regular_zip_bytes':531396157,'wire_or_billing_measurement':False}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); archive=root/'toy.zip'; source=root/'source'; source.mkdir()
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('evidence.zip',b'tiny deliberately truncated inner bytes')
                z.writestr('transport.json',self.reader.canonical(good))
            # Only bypass the already independently tested outer-size parser
            # to reach the inner stream rejection; this cannot admit data.
            with mock.patch.object(cas,'outer_members'), \
                 mock.patch.object(cas,'source_rows') as rows:
                with self.assertRaisesRegex(ValueError,'INNER_DIGEST'):
                    cas.copy_source(archive,source)
                rows.assert_not_called()
            self.assertEqual(list(source.iterdir()),[])

    def fixture(self, mutate=None, extra=None):
        # Tiny format only: these bytes cannot match the pinned outer ZIP or
        # f77a source contract and are never published as admitted source.
        names=['source-receipt.json','ATTRIBUTION.txt','LICENSE.TXT','README.TXT','SPEAKERS.TXT']
        names += ['flac/tiny-%s.flac'%i for i in range(8)]
        bodies={cas.PREFIX+n:('tiny format '+n).encode() for n in names}
        bodies['effects/result.json']=b'old scientific result must not be opened'
        files=sorted([{'path':k,'mode':0o644,'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()}
                      for k,v in bodies.items()],key=lambda r:r['path'])
        manifest={'schema':self.reader.SCHEMA,'authority':'BYTE_TRANSPORT_ONLY',
            'execution_source':P.origin_main,'run_id':str(P.verify_run),'tool_sha256':P.transport_tool_sha256,
            'files':files,'directories':[{'path':n,'mode':0o755} for n in ['effects','effects/data','effects/data/flac']],
            'logical_bytes':sum(map(len,bodies.values())),'unique_bytes':sum(map(len,bodies.values()))}
        if mutate: mutate(manifest)
        raw=self.reader.canonical(manifest)
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr(self.reader.zip_info('manifest.json'),raw)
            for body in bodies.values():
                z.writestr(self.reader.zip_info('objects/'+hashlib.sha256(body).hexdigest()),body)
            if extra: extra(z)
            ordinary=22+sum(z.getinfo('objects/'+r['sha256']).compress_size+76+2*len(r['path'].encode()) for r in files)
        record={'manifest_sha256':hashlib.sha256(raw).hexdigest(),'files':len(files),'unique_blobs':len(bodies),
            'logical_bytes':manifest['logical_bytes'],'unique_bytes':manifest['unique_bytes'],
            'equivalent_regular_zip_bytes':ordinary}
        return out.getvalue(),record

    def test_source_subset_only_no_result_body_read(self):
        blob,record=self.fixture()
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            read=z.read
            with mock.patch.object(z,'read',side_effect=lambda name:read(name) if name=='manifest.json' else
                                   (_ for _ in ()).throw(AssertionError('nonmetadata read'))):
                rows=cas.source_rows(z,record,self.reader)
        self.assertEqual(len(rows),13)
        self.assertTrue(all(r['path'].startswith(cas.PREFIX) for r in rows))

    def test_wrong_source_run_tool_and_unsafe_path_rejected(self):
        mutations=[lambda m:m.update(execution_source='0'*40),lambda m:m.update(run_id='1'),
                   lambda m:m.update(tool_sha256='0'*64),
                   lambda m:m['files'][0].update(path='../escape')]
        for mutation in mutations:
            blob,record=self.fixture(mutation)
            with self.subTest(mutation=mutations.index(mutation)),zipfile.ZipFile(io.BytesIO(blob)) as z:
                with self.assertRaises(ValueError): cas.source_rows(z,record,self.reader)

    def test_extra_or_symlink_object_rejected(self):
        def extra(z): z.writestr(self.reader.zip_info('objects/'+'0'*64),b'extra')
        def link(z):
            info=self.reader.zip_info('objects/'+'0'*64); info.external_attr=(stat.S_IFLNK|0o777)<<16
            z.writestr(info,b'target')
        for change in (extra,link):
            blob,record=self.fixture(extra=change)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                with self.assertRaises(ValueError): cas.source_rows(z,record,self.reader)

    def test_wrong_manifest_hash_and_missing_source_notices(self):
        blob,record=self.fixture()
        record['manifest_sha256']='0'*64
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            with self.assertRaisesRegex(ValueError,'MANIFEST_DIGEST'): cas.source_rows(z,record,self.reader)
        def absent(m):
            m['files'][0]['path']='effects/data/AAA-ATTRIBUTION-removed.txt'
            m['files'].sort(key=lambda r:r['path'])
        blob,record=self.fixture(absent)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            with self.assertRaisesRegex(ValueError,'NOTICES_MISSING'): cas.source_rows(z,record,self.reader)

    def test_outer_wrong_members_size_and_link(self):
        for names in (['evidence.zip'],['evidence.zip','transport.json','extra'],['../evidence.zip','transport.json']):
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:
                for name in names:
                    info=zipfile.ZipInfo(name); info.external_attr=(stat.S_IFREG|0o644)<<16
                    z.writestr(info,b'x')
            with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z:
                with self.assertRaises(ValueError): cas.outer_members(z)
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for name in ('evidence.zip','transport.json'):
                info=zipfile.ZipInfo(name); info.external_attr=(stat.S_IFREG|0o644)<<16
                z.writestr(info,b'x')
        with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z:
            with self.assertRaisesRegex(ValueError,'SIZE_LIMIT'): cas.outer_members(z)
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for name in ('evidence.zip','transport.json'):
                info=zipfile.ZipInfo(name)
                info.external_attr=((stat.S_IFLNK if name=='evidence.zip' else stat.S_IFREG)|0o644)<<16
                z.writestr(info,b'x')
        with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z:
            with self.assertRaisesRegex(ValueError,'TYPE_OR_ENCODING'): cas.outer_members(z)


if __name__=='__main__':
    unittest.main()
