#!/usr/bin/env python3
"""Pure contract/transport/math tests, never real speech or an AP executable.

The tiny PCM arrays are fabricated integers. The fake process in one test only
writes fixture bytes; it is not a compiled processor or engineering evidence.
"""
from __future__ import annotations

import array
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock

import f05_dualmic_validation as f


TRACE_KEYS = {'frame','algorithmic_latency_ms','vad_probability','vad_active','far_end_active',
              'double_talk_active','erle_db','erle_valid','aec_converged','estimated_delay_ms','delay_error_samples'}


def trace_row(frame=0):
    return {'frame':frame, 'algorithmic_latency_ms':10, 'vad_probability':0.25, 'vad_active':0,
            'far_end_active':0, 'double_talk_active':0, 'erle_db':0.0, 'erle_valid':0,
            'aec_converged':0, 'estimated_delay_ms':0.0, 'delay_error_samples':0.0}


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='f05-dualmic-tiny-')
        self.root = Path(self.tmp.name)
        self.plan = f.load_json(f.PLAN)

    def tearDown(self):
        self.tmp.cleanup()

    def sample_case(self, scene='near-only', profile='call', count=160):
        folder = self.root/'input'; folder.mkdir(exist_ok=True)
        case = {'case_id':'tiny-'+scene+'-'+profile, 'scenario':scene, 'sample_rate_hz':16000,
                'mic_channels':2, 'pipeline_profile':profile, 'processor_profile':'default', 'control':{},
                'mic_audio':'mic.s16', 'clean_near_audio':'clean.s16', 'render_audio':None,
                'interference_audio':None, 'echo_audio':None,
                'dimensions':{'samples_per_channel':count,'capture_frames':count//160}}
        (folder/'mic.s16').write_bytes(bytes(count*4))
        (folder/'clean.s16').write_bytes(bytes(count*2))
        if scene == 'doubletalk':
            case.update(render_audio='render.s16',interference_audio='interference.s16')
            (folder/'render.s16').write_bytes(bytes(count*2))
            (folder/'interference.s16').write_bytes(bytes(count*2))
        return folder/'corpus.json', case

    def engineering_pair(self):
        revision = 'a'*40
        bundle = {'manifest':{'kind':'AP_CURRENT_PORTABLE_V1','status':'PASS_ENGINEERING_ONLY',
            'code_revision':revision,'files':{'bin/ap_process_pcm':'1'*64,'bin/ap_build_info_dump':'2'*64},
            'paths':{'processor':'bin/ap_process_pcm','build_info':'bin/ap_build_info_dump'}}}
        record = {'status':'PASS_ENGINEERING_ONLY','source_revision':revision,
            'processor_sha256':'1'*64,'build_info_sha256':'2'*64,
            'algorithmic_latency_samples':{'call':160,'assistant':160},
            'algorithmic_latency_ms':{'call':10,'assistant':10},'implicit_default_equals_call':True,
            'default_tuning':{profile:{'aec_mu':0.1,'ns_floor':0.1,'agc_target_dbfs':-18.0,'limiter_dbfs':-1.0}
                              for profile in f.PROFILES}}
        return revision, bundle, record

    def replay(self):
        cases = [{'case_id':'tiny-'+str(index)} for index in range(128)]
        for case in cases:
            path = self.root/'replay'/case['case_id']; path.mkdir(parents=True)
            for name in ('command.json','stdout.txt','stderr.txt','out.pcm','metrics.jsonl','continuity.json'):
                (path/name).write_bytes(b'')
            f.write_json(path/'execution.json',{'returncode':0,'elapsed_seconds':0.25})
        return cases

    def test_frozen_plan_and_metadata_totals(self):
        f.validate_plan(self.plan)
        schedule = f.metadata_schedule(self.plan['source']['originals'])
        self.assertEqual(len(schedule),64)
        self.assertEqual(2*sum(row['samples_per_channel'] for row in schedule),28277760)
        self.assertEqual(sum(row['frames'] for row in self.plan['source']['originals']),5241680)
        self.assertEqual(max(row['samples_per_channel'] for row in schedule),479840)
        self.assertEqual(sum(row['frames']%160 == 80 for row in self.plan['source']['originals']),11)
        self.assertEqual(len({(row['speaker'],row['ordinal']) for row in schedule}),32)
        self.assertEqual({row['frame_tail_padding_samples'] for row in schedule},{0,80})

    def test_role_gain_lag_and_budget_changes_refused(self):
        for section, key, value in [('data_use','optimizer_selection_allowed',True),
                ('data_use','blind_status','BLIND'),('renderer','near_source_gain',0.5),
                ('measurement','primary_delays_samples',{'raw':0,'call':161,'assistant':160}),
                ('measurement','secondary_render_interference_maxcorr_radius_ms',0),
                ('budgets','maximum_audio_processor_calls',129),('budgets','parallel_processors',True),
                ('processor','engineering_copy_bound',{'files':200,'bytes':67108864})]:
            with self.subTest(section=section,key=key):
                changed = copy.deepcopy(self.plan); changed[section][key] = value
                with self.assertRaises(ValueError): f.validate_plan(changed)

    def test_selection_duplicate_and_schedule_change_refused(self):
        changed = copy.deepcopy(self.plan)
        changed['source']['originals'][1] = changed['source']['originals'][0]
        with self.assertRaises(ValueError): f.validate_plan(changed)
        changed = copy.deepcopy(self.plan)
        changed['renderer']['schedule'][0]['near_mask'][1] -= 80
        with self.assertRaises(ValueError): f.validate_plan(changed)

    def test_potential_echo_support_is_partial_not_vad(self):
        row = next(row for row in self.plan['renderer']['schedule']
                   if row['speaker']==2428 and row['ordinal']==0 and row['scene']=='doubletalk')
        support = row['structural_support']
        self.assertEqual(support['mic0']['intersection_samples'],17920)
        self.assertEqual(support['mic0']['fraction_of_original_near'],17920/212880)
        self.assertEqual(support['mic1']['echo_support'][0],321)
        self.assertEqual(support['mic1']['echo_support'][1],support['mic0']['echo_support'][1]+2)
        self.assertEqual(support['meaning'],'metadata-structural-envelope-not-VAD')
        self.assertIsNone(f.structural_support(240,320,'near-only')['mic0'])

    def test_full_synthetic_original_and_final_80_samples_preserved(self):
        pcm = {'near':[32767,-32768]*120,'far':[100]*320}
        originals = {key:{'frames':len(value)} for key,value in pcm.items()}
        schedule = {'speaker':2412,'ordinal':0,'far_speaker':2428,'near_member':'near','far_member':'far',
                    'scene':'near-only','samples_per_channel':32320,'frame_tail_padding_samples':80,
                    'structural_support':f.structural_support(240,320,'near-only')}
        case, files = f.derive_case(schedule,originals,pcm,self.plan)
        clean = array.array('h'); clean.frombytes(files[case['clean_near_audio']])
        self.assertEqual(list(clean[24000:24240]),f.scale(pcm['near'],.25))
        self.assertEqual(len(clean),32320)
        self.assertEqual(list(clean[24240:]),[0]*8080)
        self.assertEqual(pcm['near'][-1],-32768)
        self.assertIsNone(case['render_audio'])
        self.assertFalse(case['dimensions']['real_array_recording'])

    def test_synthetic_mix_does_not_hide_overflow_or_change_scene(self):
        pcm = {'near':[32767]*160,'far':[32767]*160}
        originals = {key:{'frames':160} for key in pcm}
        schedule = {'speaker':2412,'ordinal':0,'far_speaker':2428,'near_member':'near','far_member':'far',
                    'scene':'doubletalk','samples_per_channel':32160,'frame_tail_padding_samples':0,
                    'structural_support':f.structural_support(160,160,'doubletalk')}
        with mock.patch.object(f,'echo_from_render',return_value=[30000]*32160):
            with self.assertRaisesRegex(ValueError,'clipping'): f.derive_case(schedule,originals,pcm,self.plan)
        schedule['scene'] = 'unregistered'
        with self.assertRaises(ValueError): f.derive_case(schedule,originals,pcm,self.plan)

    def test_primary_uses_only_fixed_160_and_full_mask(self):
        clean = [0]*20 + [((i*7919)%12001)-6000 for i in range(200)] + [0]*200
        delayed = [0]*160 + clean[:-160]
        with mock.patch.object(f.engine,'aligned_span',side_effect=AssertionError('target alignment forbidden')), \
             mock.patch.object(f.engine,'max_abs_corr',side_effect=AssertionError('correlation forbidden')):
            result = f.fixed_primary(clean,clean,{'call':delayed,'assistant':delayed},[20,220],{'raw':0,'call':160,'assistant':160})
        self.assertTrue(result['raw_near_reference_identical'])
        self.assertTrue(result['call_near_reference_identical'])
        self.assertEqual(result['call_minus_raw_db'],0)
        self.assertEqual(result['common_samples'],200)
        shifted = [0]*161 + clean[:-161]
        result = f.fixed_primary(clean,clean,{'call':shifted,'assistant':delayed},[20,220],{'raw':0,'call':160,'assistant':160})
        self.assertFalse(result['call_near_reference_identical'])
        self.assertLess(result['call_minus_raw_db'],0)
        self.assertEqual(result['fixed_delays_samples']['call'],160)

    def test_primary_short_tail_null_and_delay_change(self):
        delays = {'raw':0,'call':160,'assistant':160}
        zeros = [0]*400
        result = f.fixed_primary(zeros,zeros,{'call':zeros,'assistant':zeros},[20,220],delays)
        self.assertIsNone(result['raw_near_si_sdr_db'])
        self.assertIsNone(result['call_minus_raw_db'])
        with self.assertRaises(ValueError):
            f.fixed_primary(zeros,zeros,{'call':zeros[:379],'assistant':zeros},[20,220],delays)
        with self.assertRaises(ValueError):
            f.fixed_primary(zeros,zeros,{'call':zeros,'assistant':zeros},[20,220],{**delays,'call':159})

    def test_identity_negative_deltas_and_nulls_are_aggregated(self):
        rows = [{'speaker':speaker,'scene':scene,'raw_near_reference_identical':True,
                 'call_minus_raw_db':value,'assistant_minus_raw_db':value}
                for scene in f.SCENES for speaker in f.source.SELECTED for value in (-300.0,-100.0,None,0.0)]
        result = f.primary_summary(rows)
        self.assertTrue(result['output_views_are_correlated'])
        for group in result['groups']:
            self.assertEqual(group['median_speaker_mean_delta_db'],-400/3)
            self.assertEqual(group['speaker_results'][0]['null'],1)
            self.assertEqual(group['speaker_results'][0]['raw_reference_identical_utterances'],4)
            self.assertEqual(group['speaker_results'][0]['utterance_deltas_db'],[-300.0,-100.0,None,0.0])

    def test_strict_capture_render_lengths_and_settings(self):
        path, case = self.sample_case('doubletalk')
        f.check_case_streams(path,case)
        (path.parent/'render.s16').write_bytes(bytes(159*2))
        with self.assertRaisesRegex(ValueError,'length'): f.check_case_streams(path,case)
        (path.parent/'render.s16').write_bytes(bytes(160*2))
        for change in ({'control':{'echo_path_change_frame':0}},{'pipeline_profile':'other'},
                       {'echo_audio':'interference.s16'},{'render_audio':None}):
            with self.subTest(change=change), self.assertRaises(ValueError): f.check_case_streams(path,{**case,**change})

    def test_trace_rejects_missing_duplicate_nonfinite_truncated_and_flag_fields(self):
        path = self.root/'trace.jsonl'
        fake_api = types.SimpleNamespace(TRACE_KEYS=TRACE_KEYS)
        with mock.patch.object(f,'ap_module',return_value=fake_api):
            path.write_text(json.dumps(trace_row())+'\n')
            self.assertEqual(len(f.read_trace(path,1)),1)
            invalid = [json.dumps(trace_row()), json.dumps({**trace_row(),'frame':False})+'\n',
                       json.dumps({**trace_row(),'algorithmic_latency_ms':10.0})+'\n',
                       json.dumps({**trace_row(),'erle_db':float('nan')})+'\n',
                       json.dumps({**trace_row(),'erle_valid':2})+'\n',
                       json.dumps({**trace_row(),'vad_probability':'0.2'})+'\n',
                       json.dumps({**trace_row(),'extra':1})+'\n',
                       json.dumps({key:value for key,value in trace_row().items() if key!='erle_db'})+'\n',
                       '{"frame":0,'+json.dumps(trace_row())[1:]+'\n']
            for data in invalid:
                with self.subTest(data=data):
                    path.write_text(data)
                    with self.assertRaises(ValueError): f.read_trace(path,1)
            path.write_text(json.dumps(trace_row(1))+'\n')
            with self.assertRaises(ValueError): f.read_trace(path,1)

    def test_execution_environment_and_one_call_no_processor(self):
        path, case = self.sample_case()
        environment = {'PATH':'/synthetic-test-no-executable','LC_ALL':'C'}
        observed = []
        def fake_run(command, **kwargs):
            self.assertEqual(kwargs['env'],environment)
            self.assertEqual(kwargs['timeout'],30)
            observed.append(command)
            Path(command[-1]).write_bytes(bytes(320))
            Path(command[command.index('--metrics-jsonl')+1]).write_text(json.dumps(trace_row())+'\n')
            return subprocess.CompletedProcess(command,0,'tiny fake process\n','')
        guarded = lambda a,b,rate: 0.0
        semantics = f.execution_semantics(self.root/'replay',environment,guarded)
        self.assertIs(semantics.evaluation.max_abs_corr,guarded)
        with mock.patch.object(f.subprocess,'run',side_effect=fake_run):
            result = semantics.evaluation.invoke(Path('/no-real-processor'),case,path,self.root/'unused')
        self.assertEqual(len(observed),1)
        self.assertEqual(len(result[0]),160)
        self.assertIn('--strict-capture-frames',observed[0])
        self.assertNotIn('--aec-mu',observed[0])
        self.assertEqual(observed[0][observed[0].index('--profile')+1],'call')

    def test_recorded_commands_are_bound_to_binary_and_canonical_original_directory(self):
        _revision, bundle, _record = self.engineering_pair()
        report = {'execution_root':'/prior/fixed-output',
                  'processor_execution_path':'/prior/fixed-output/bundle/bin/ap_process_pcm'}
        f.check_execution_paths(report,bundle)
        for changed in ({**report,'processor_execution_path':'/other/binary'},
                        {**report,'execution_root':'relative'}, {**report,'execution_root':'/prior/../different'},
                        {**report,'execution_root':'/prior//fixed-output'}):
            with self.assertRaises(ValueError): f.check_execution_paths(changed,bundle)
        _path, case = self.sample_case('doubletalk','assistant')
        command = f.expected_command(report,case)
        self.assertEqual(command[0],report['processor_execution_path'])
        self.assertIn('assistant',command)
        self.assertNotIn('--capture-only',command)

    def test_engineering_hash_profile_and_latency_bound(self):
        revision,bundle,record = self.engineering_pair()
        f.check_engineering(record,bundle,revision)
        for key,value in [('processor_sha256','3'*64),('algorithmic_latency_samples',{'call':159,'assistant':160}),
                          ('implicit_default_equals_call',False),('source_revision','b'*40)]:
            with self.subTest(key=key),self.assertRaises(ValueError): f.check_engineering({**record,key:value},bundle,revision)

    def test_ci_native_transport_source_and_no_fallback_are_frozen(self):
        native = self.plan['measurement']['secondary_native_transport']
        self.assertEqual(native['source_files_sha256'],f.CORRELATION_FILES)
        self.assertIn('validation/tools/render_corr_exact.c',f.CORRELATION_FILES)
        for key,value in [('local_compilation_allowed',True),('implicit_compile_fallback_allowed',True),
                          ('scoring_factory','engine.max_abs_corr'),('search_id','legacy-sparse')]:
            changed = copy.deepcopy(self.plan)
            changed['measurement']['secondary_native_transport'][key] = value
            with self.subTest(key=key),self.assertRaises(ValueError): f.validate_plan(changed)

    def test_precompiled_binding_injects_guard_and_records_all_source_hashes(self):
        # Private metadata-only test double: these bytes are not an ELF and are
        # never loaded. Public AP bundle verification cannot admit this object.
        bundle_root = self.root/'bundle'; (bundle_root/'lib').mkdir(parents=True)
        binary = bundle_root/'lib/librender_corr_exact.so'; binary.write_bytes(b'TINY-NOT-ELF')
        digest = f.source.file_hash(binary)
        bundle = {'manifest':{'code_revision':'a'*40,'paths':{'render_corr':'lib/librender_corr_exact.so'},
                              'files':{'lib/librender_corr_exact.so':digest}}}
        binding = {'schema_version':1,'status':'BOUND_PREBUILT_VALIDATION_HELPER','code_revision':'a'*40,
            'search_id':'exact-all-integer-lags-stride4-v1','library':'lib/librender_corr_exact.so',
            'binary_sha256':digest,'source_sha256':f.CORRELATION_FILES['validation/tools/render_corr_exact.c'],
            'loader_sha256':f.CORRELATION_FILES['validation/tools/render_corr_exact.py'],
            'engine_sha256':f.CORRELATION_FILES['validation/tools/run_validation_engine.py'],
            'compiler':'TINY_NOT_A_COMPILER','abi':'TINY_METADATA_ONLY','local_compilation':False}
        guarded = mock.Mock(return_value=0.5)
        api = types.SimpleNamespace(bind_render_corr_native=mock.Mock(return_value=binding),
                                    build_bound_max_abs_corr=mock.Mock(return_value=guarded))
        with mock.patch.object(f.run_validation.render_corr_exact,'_load_native',side_effect=AssertionError('compiler path forbidden')):
            record, callback = f.precompiled_scoring(bundle_root,bundle,self.plan,api)
            semantics = f.execution_semantics(self.root/'unused',{},callback)
            self.assertEqual(semantics.evaluation.max_abs_corr([1],[2],16000),0.5)
        api.bind_render_corr_native.assert_called_once_with(bundle_root,module=f.run_validation.render_corr_exact)
        api.build_bound_max_abs_corr.assert_called_once_with(bundle_root,f.engine.normalized_corr,
                                                             module=f.run_validation.render_corr_exact)
        guarded.assert_called_once()
        self.assertEqual(record['source_files_sha256'],f.CORRELATION_FILES)
        self.assertEqual(record['binary_sha256'],digest)
        self.assertEqual(record['local_c_compilations'],0)
        self.assertFalse(record['implicit_compile_fallback_allowed'])

    def test_precompiled_missing_binary_or_dirty_state_fails_without_fallback(self):
        bundle_root = self.root/'bundle'; (bundle_root/'lib').mkdir(parents=True)
        binary = bundle_root/'lib/librender_corr_exact.so'; binary.write_bytes(b'TINY-NOT-ELF')
        digest = f.source.file_hash(binary)
        bundle = {'manifest':{'paths':{'render_corr':'lib/librender_corr_exact.so'},
                              'files':{'lib/librender_corr_exact.so':digest}}}
        api = types.SimpleNamespace(bind_render_corr_native=mock.Mock(side_effect=ValueError('prior automatic compiler state')),
                                    build_bound_max_abs_corr=mock.Mock())
        with mock.patch.object(f.run_validation.render_corr_exact,'_load_native',side_effect=AssertionError('compiler fallback forbidden')):
            with self.assertRaisesRegex(ValueError,'prior automatic'): f.precompiled_scoring(bundle_root,bundle,self.plan,api)
            api.build_bound_max_abs_corr.assert_not_called()
            binary.write_bytes(b'TINY-ALTERED')
            api.bind_render_corr_native.reset_mock()
            with self.assertRaisesRegex(ValueError,'binary drift'): f.precompiled_scoring(bundle_root,bundle,self.plan,api)
            api.bind_render_corr_native.assert_not_called()

    def test_measurement_math_host_matches_engineering_not_process_id_or_library_copy_path(self):
        # A transport fixture only; the real AP normalizer owns actual ldd schema.
        normalize = lambda row: {'host':row['host'],'libraries':row['libraries']}
        api = types.SimpleNamespace(normalize_render_corr_runtime=normalize)
        engineering = {'runtime_identity':{'render_corr':{'host':'HOST_A','libraries':{'libm':'a'*64},'path':'/original'}}}
        runtime = {'loader_environment':'CLEAN_AT_START_AND_NOW','pid':123,
            'parent_library_mappings':{'tiny':'opaque-not-real-maps'},
            'runtime_identity':{'host':'HOST_A','libraries':{'libm':'a'*64},'path':'/copied'}}
        f.check_math_runtime(runtime,engineering,api)
        for changed in ({**runtime,'loader_environment':'POLLUTED'},
                        {**runtime,'pid':False},
                        {**runtime,'runtime_identity':{'host':'HOST_B','libraries':{'libm':'a'*64}}},
                        {**runtime,'runtime_identity':{'host':'HOST_A','libraries':{'libm':'b'*64}}}):
            with self.assertRaises(ValueError): f.check_math_runtime(changed,engineering,api)

    def test_replay_has_exact_128_cases_seven_files_and_consistent_sequential_time(self):
        cases = self.replay()
        self.assertEqual(f.replay_layout(self.root,cases,40),32)
        with self.assertRaises(ValueError): f.replay_layout(self.root,cases,31.999)
        with self.assertRaises(ValueError): f.replay_layout(self.root,cases,600.001)
        extra = self.root/'replay/extra-129'; extra.mkdir()
        with self.assertRaises(ValueError): f.replay_layout(self.root,cases,40)
        extra.rmdir()
        extra = self.root/'replay/tiny-0/hidden-output.pcm'; extra.write_bytes(b'')
        with self.assertRaises(ValueError): f.replay_layout(self.root,cases,40)

    def test_failure_prefix_and_bool_returncode_cannot_be_resealed(self):
        cases = self.replay()
        for name in f.FAILURE_PREFIXES:
            path = self.root/name; path.write_text('{}')
            with self.assertRaises(ValueError): f.replay_layout(self.root,cases,40)
            path.unlink()
        f.write_json(self.root/'replay/tiny-0/execution.json',{'returncode':False,'elapsed_seconds':.25})
        with self.assertRaises(ValueError): f.replay_layout(self.root,cases,40)

    def test_engineering_copy_accepts_exact_ap_bound_and_refuses_513(self):
        original = self.root/'engineering'; original.mkdir()
        for index in range(512): (original/str(index)).write_bytes(b'x')
        f.copy_tree(original,self.root/'copy',self.plan,engineering=True)
        self.assertEqual(len(list((self.root/'copy').iterdir())),512)
        (original/'512').write_bytes(b'x')
        with self.assertRaises(ValueError): f.copy_tree(original,self.root/'refused',self.plan,engineering=True)
        self.assertFalse((self.root/'refused').exists())

    def test_manifest_rejects_symlinks_and_overlapping_input_output(self):
        original = self.root/'data'; original.mkdir(); (original/'x').write_bytes(b'x')
        (original/'link').symlink_to(original/'x')
        with self.assertRaises(ValueError): f.file_manifest(original,self.plan)
        for output,item in ((original,original),(original/'new',original),(original,original/'child')):
            with self.assertRaises(ValueError): f.disjoint_output(output,[item])
        f.disjoint_output(self.root/'other',[original])

    def test_late_failure_invalidates_success_keeps_prefix(self):
        report_bytes = b'{"status": "MEASUREMENT_COMPLETE_DESCRIPTIVE_ONLY", "actual": 0.25}\n\n'
        manifest_bytes = b'{ "schema_version": 1, "files": {} }\n'
        (self.root/'report.json').write_bytes(report_bytes)
        (self.root/'artifact-manifest.json').write_bytes(manifest_bytes)
        (self.root/'prefix.pcm').write_bytes(b'tiny-not-audio')
        f.fail_output(self.root,TimeoutError('late sealing'),'run',f.time.monotonic())
        self.assertFalse((self.root/'report.json').exists())
        self.assertFalse((self.root/'artifact-manifest.json').exists())
        self.assertEqual((self.root/'report-before-failure.json').read_bytes(),report_bytes)
        self.assertEqual((self.root/'artifact-manifest-before-failure.json').read_bytes(),manifest_bytes)
        self.assertEqual(f.load_json(self.root/'failed-report.json')['status'],'FAIL_MEASUREMENT_INTEGRITY')
        self.assertEqual(f.load_json(self.root/'failed-report.json')['original_report_sha256'],f.sha256(report_bytes))
        self.assertEqual((self.root/'prefix.pcm').read_bytes(),b'tiny-not-audio')
        self.assertEqual(f.load_json(self.root/'failure.json')['automatic_retries'],0)
        # Restoring apparent success and dropping explicit FAIL markers must not
        # hide the original late failure retained in the same evidence directory.
        (self.root/'report.json').write_bytes(report_bytes)
        (self.root/'artifact-manifest.json').write_bytes(manifest_bytes)
        (self.root/'failure.json').unlink(); (self.root/'failed-report.json').unlink()
        with self.assertRaisesRegex(ValueError,'failure prefix'):
            f.replay_layout(self.root,[],1)


if __name__ == '__main__':
    unittest.main()
