#!/usr/bin/env python3
"""Six fixed, disclosed post-AEC comparisons. No selection search or promotion."""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import resource
import shutil
import tempfile
from zipfile import ZipFile

import numpy as np
from contracts import ROOT, FrameContract, check_outputs, load_json, require, sha256
from libfvad_reference import write_json, seal_output
from speech_fir import verify_seal
from speexdsp_aec_reference import metrics
import external_source
from neural_pcm import MODELS, ONNXModel, run_pcm, quantize_s16
from test_neural_pcm import model_checks

HERE = Path(__file__).resolve().parent
PLAN = ROOT / '.github/research/frontend-evolution-v1/external-neural-v1.json'
CODE = ('external_neural.py', 'neural_pcm.py', 'external_source.py', 'test_neural_pcm.py',
        'contracts.py', 'libfvad_reference.py', 'speexdsp_aec_reference.py',
        'speech_spatial.py', 'bf_aec_order.py', 'speech_fir.py')
EVALUATOR = ROOT / 'validation/tools/run_validation_engine.py'


def source_hashes():
    return {**{name: sha256((HERE / name).read_bytes()) for name in CODE},
            'run_validation_engine.py': sha256(EVALUATOR.read_bytes())}


def dependency_inventory():
    records = {}
    for name in ('onnxruntime', 'onnx', 'numpy', 'protobuf', 'flatbuffers', 'coloredlogs',
                 'humanfriendly', 'sympy', 'mpmath', 'ml_dtypes', 'typing_extensions', 'packaging'):
        dist = importlib.metadata.distribution(name)
        selected = {}
        for path in dist.files or []:
            relative = str(path)
            if (relative.endswith(('.so', 'METADATA', 'RECORD')) or '.so.' in path.name or 'license' in relative.lower()
                    or relative.lower().endswith(('copying', 'notice'))):
                actual = Path(dist.locate_file(path))
                if actual.is_file():
                    selected[relative] = sha256(actual.read_bytes())
        records[name] = {'version': dist.version, 'binary_metadata_notice_sha256': selected,
                         'license_classifiers': [v for v in dist.metadata.get_all('Classifier', [])
                                                 if v.startswith('License')],
                         'license_expression': dist.metadata.get('License-Expression')}
    return {'python': platform.python_version(), 'platform': platform.platform(), 'packages': records,
            'scope': 'actual installed native binaries, wheel metadata/RECORD and notices; no shipping redistribution'}


def read_inputs(archive, plan):
    require(sha256(archive.read_bytes()) == plan['predecessor']['archive_sha256'],
            'wrong original predecessor ZIP')
    result = {}
    with ZipFile(archive) as zipped:
        names = zipped.namelist()
        require(len(names) == len(set(names)), 'duplicate predecessor members')
        manifest = json.loads(zipped.read('manifest.json'))
        require(sha256(zipped.read('manifest.json')) == plan['predecessor']['manifest_sha256'],
                'predecessor manifest drift')
        for name, digest in manifest['files'].items():
            require(sha256(zipped.read(name)) == digest, 'predecessor member drift: ' + name)
        prior = json.loads(zipped.read('result.json'))
        for key in ('experiment_id', 'execution_source_revision', 'data_role'):
            require(prior[key] == plan['predecessor'][key], 'predecessor authority drift: ' + key)
        require(prior['shipping_authority'] is False and prior['case_count'] == 6, 'predecessor count/promotion')
        for row in plan['cases']:
            case = {}
            for name, digest in row['members_sha256'].items():
                data = zipped.read('cases/' + row['case_id'] + '/' + name)
                require(sha256(data) == digest and len(data) == row['samples'] * 2,
                        'fixed input identity/count drift')
                case[name] = data
            result[row['case_id']] = case
    return result


def samples(data):
    return (np.frombuffer(data, dtype='<i2').astype(np.float32) / 32768).tolist()


def time_summary(trace):
    ns = np.asarray(trace['push_ns'], dtype=np.float64)
    return {'pcm_push_us': {name: float(value / 1000) for name, value in
                           zip(('p50', 'p95', 'p99', 'max'), (*np.percentile(ns, [50, 95, 99]), np.max(ns)))},
            '10ms_deadline_misses_host_only': int(np.count_nonzero(ns > 10000000)),
            'push_count': len(ns), 'flush_us': trace['flush_ns'] / 1000,
            'adapter_rtf_host_only': float((sum(trace['push_ns']) + trace['flush_ns']) / 1e9 / 16),
            'first_output_input_samples': trace['availability'][0]['input_samples'],
            'pcm_fifo_high_water_samples': trace['high_water_samples'],
            'network_frames_including_flush': trace['network_frames_including_flush'],
            'explicit_working_array_bytes_after_flush': trace['explicit_working_array_bytes_after_flush']}


def verify_trace(trace, samples_count, model):
    require(samples_count == 256000, 'unexpected frozen input length')
    require(len(trace['push_ns']) == samples_count // 160
            and all(type(t) is int and 0 <= t < 2**63 for t in trace['push_ns'])
            and type(trace['flush_ns']) is int and 0 <= trace['flush_ns'] < 2**63,
            'partial/invalid neural timing coverage')
    expected, last_output = [], 0
    for count in range(160, samples_count + 1, 160):
        available = max(0, count // 256 - 1) * 256
        if available > last_output:
            expected.append({'input_samples': count, 'output_samples': available})
            last_output = available
    caches = sum(math.prod(shape)*4 for shape in MODELS[model]['caches'].values())
    require(trace['availability'] == expected and trace['high_water_samples'] == 384
            and trace['network_frames_including_flush'] == 1001
            and trace['explicit_working_array_bytes_after_flush'] == 17408 + caches,
            'complete neural stream boundary drift')


def conclusions(cases, plan):
    result = {}
    rules = plan['quality']['diagnostic_shortlist_only']
    for name in MODELS:
        losses, gains = [], []
        for row in cases:
            before, after = row['arms']['passthrough']['metrics'], row['arms'][name]['metrics']
            for phase, value in before['phases_si_sdr_relative_to_quantized_bf_target_db'].items():
                candidate = after['phases_si_sdr_relative_to_quantized_bf_target_db'][phase]
                if value is not None and candidate is not None:
                    losses.append(float(value - candidate))
            if before['final_far_ratio_db'] is not None and after['final_far_ratio_db'] is not None:
                gains.append(float(after['final_far_ratio_db'] - before['final_far_ratio_db']))
        require(len(losses) == 24 and len(gains) == 6, 'partial quality comparisons')
        worst, mean = max(losses), sum(gains) / len(gains)
        shortlist = (worst <= rules['max_per_case_near_phase_si_sdr_loss_db']
                     and mean >= rules['min_mean_far_only_extra_attenuation_db'])
        result[name] = {'worst_near_phase_si_sdr_loss_db': worst,
                        'mean_far_only_extra_attenuation_db': mean,
                        'diagnostic_shortlist_rule_met': shortlist,
                        'disposition': 'RETAIN_FOR_INDEPENDENT_STUDY' if shortlist else 'REJECT_D0_POST_AEC_CONFIGURATION',
                        'shipping_authority': False}
    return result


def run(archive, source, root):
    require(not root.exists(), 'fresh result directory required')
    plan = load_json(PLAN)
    inputs = read_inputs(archive, plan)
    receipt = external_source.verify(source)
    for name in MODELS:
        external_source.admitted(source, name)
    root.mkdir(parents=True)
    write_json(root / 'experiment.json', plan)
    shutil.copyfile(external_source.ADMISSION, root / 'admission.json')
    write_json(root / 'source-receipt.json', receipt)
    (root / 'source').mkdir()
    for name in CODE:
        shutil.copyfile(HERE / name, root / 'source' / name)
    shutil.copyfile(EVALUATOR, root / 'source' / EVALUATOR.name)
    for name in MODELS:
        shutil.copyfile(source / name / 'LICENSE', root / (name + '-LICENSE'))
    dependencies = dependency_inventory()
    write_json(root / 'dependencies.json', dependencies)
    # Engineering checks do not score or select on the six speech cases.
    engineering = model_checks(source)
    models = {name: ONNXModel(source, name) for name in MODELS}
    rows = []
    for spec in plan['cases']:
        case_id = spec['case_id']
        directory = root / 'cases' / case_id
        directory.mkdir(parents=True)
        data = inputs[case_id]
        for name, value in data.items():
            (directory / name).write_bytes(value)
        observation = np.asarray(samples(data['ap.s16']), np.float32)
        target, echo = samples(data['target.s16']), samples(data['echo.s16'])
        row = {'case_id': case_id, 'input_sha256': spec['members_sha256']['ap.s16'], 'arms': {}}
        for name in plan['arms']:
            if name == 'passthrough':
                output = observation.copy()
                timing = None
            else:
                output, trace = run_pcm(models[name], MODELS[name]['window'], observation)
                write_json(directory / (name + '-trace.json'), trace)
                timing = time_summary(trace)
                # Same frozen real observation, reset, independent 37-sample partition.
                repeated, _ = run_pcm(models[name], MODELS[name]['window'], observation, chunk=37)
                require(output.tobytes() == repeated.tobytes(), 'speech repeat/partition drift')
                changed = observation.copy()
                prefix = plan['engineering']['future_prefix_samples']
                changed[prefix:] *= -1
                future, _ = run_pcm(models[name], MODELS[name]['window'], changed)
                cut = (prefix // 256 - 1) * 256
                require(output[:cut].tobytes() == future[:cut].tobytes()
                        and output[prefix:].tobytes() != future[prefix:].tobytes(), 'speech future causality')
            pcm, clips = quantize_s16(output)
            (directory / (name + '.f32')).write_bytes(output.astype('<f4').tobytes())
            (directory / (name + '.s16')).write_bytes(pcm.tobytes())
            row['arms'][name] = {'output_sha256': sha256(pcm.tobytes()), 'output_samples': len(pcm),
                                 'prequantization_clip_count': clips, 'timing': timing,
                                 'metrics': metrics(target, echo, samples(pcm.tobytes()))}
        rows.append(row)
        print('completed ' + case_id, flush=True)
    report = {'schema_version': 1, 'experiment_id': plan['experiment_id'], 'decision': plan['decision'],
              'base_revision': plan['base_revision'], 'shipping_authority': False, 'data_role': plan['data_role'],
              'plan_sha256': sha256(PLAN.read_bytes()), 'code_sha256': source_hashes(),
              'source_receipt_sha256': sha256((root / 'source-receipt.json').read_bytes()),
              'dependency_manifest_sha256': sha256((root / 'dependencies.json').read_bytes()),
              'models_sha256': {name: models[name].model_sha256 for name in MODELS},
              'host_process_peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'rss_scope': 'whole Python process with both ORT sessions and evaluator; not component or target SRAM',
              'engineering': engineering, 'cases': rows, 'conclusions': conclusions(rows, plan)}
    write_json(root / 'result.json', report)
    seal_output(root, report)
    return verify(root)


def verify(root):
    verify_seal(root)
    plan, report = load_json(PLAN), load_json(root / 'result.json')
    require(load_json(root / 'experiment.json') == plan and report['plan_sha256'] == sha256(PLAN.read_bytes()),
            'neural experiment drift')
    require(report['experiment_id'] == plan['experiment_id'] and report['decision'] == plan['decision']
            and report['base_revision'] == plan['base_revision'] and report['shipping_authority'] is False
            and report['data_role'] == plan['data_role'], 'neural authority drift')
    require(report['code_sha256'] == source_hashes(), 'processor/evaluator code drift')
    for name, digest in report['code_sha256'].items():
        require(sha256((root / 'source' / name).read_bytes()) == digest, 'processor snapshot mismatch')
    require((root / 'admission.json').read_bytes() == external_source.ADMISSION.read_bytes(), 'admission drift')
    require(report['source_receipt_sha256'] == sha256((root / 'source-receipt.json').read_bytes())
            and report['dependency_manifest_sha256'] == sha256((root / 'dependencies.json').read_bytes()), 'execution provenance drift')
    receipt = load_json(root / 'source-receipt.json')
    admitted = load_json(external_source.ADMISSION)
    require(receipt['sources'] == admitted['sources']
            and receipt['source_lock_sha256'] == sha256(external_source.LOCK.read_bytes())
            and receipt['shipping_authority'] is False
            and receipt['status'] == 'SOURCE_BYTES_VERIFIED_NOT_EXECUTED', 'unadmitted source materialization')
    engineering = {name: {'partition_and_reset_equal': True, 'causal_prefix_samples': 15616,
                           'future_changed': True, 'silence_pass': True,
                           'model_cache_bytes': sum(math.prod(shape)*4 for shape in spec['caches'].values()),
                           'high_water_samples': 384} for name, spec in MODELS.items()}
    require(report['engineering'] == engineering, 'missing/changed neural engineering evidence')
    rows = {r['case_id']: r for r in report['cases']}
    require(len(rows) == len(report['cases']) == len(plan['cases']) == 6, 'missing/duplicate case')
    contract = FrameContract(16000, 1, 0, 256, (0,))
    identities = {}
    for name in plan['arms']:
        identities[name] = {'source_sha': plan['base_revision'] if name == 'passthrough' else receipt['sources'][name]['source_commit'],
                            'config_sha256': report['plan_sha256'], 'evaluator_sha256': sha256(EVALUATOR.read_bytes()),
                            'processor_sha256': external_source.identity({'code': report['code_sha256'], 'arm': name,
                                                                          'model': report['models_sha256'].get(name)})}
    expected, outputs = {}, {name: [] for name in plan['arms']}
    for spec in plan['cases']:
        row, directory = rows[spec['case_id']], root / 'cases' / spec['case_id']
        require(set(row['arms']) == set(plan['arms']), 'missing/extra backend')
        for name, digest in spec['members_sha256'].items():
            require(sha256((directory / name).read_bytes()) == digest, 'predecessor observation byte drift')
        require(row['input_sha256'] == spec['members_sha256']['ap.s16'], 'input identity drift')
        target, echo = samples((directory / 'target.s16').read_bytes()), samples((directory / 'echo.s16').read_bytes())
        expected[row['case_id']] = {'input_sha256': row['input_sha256'], 'output_samples': spec['samples'], 'require_nonzero': True}
        for name, arm in row['arms'].items():
            data = (directory / (name + '.s16')).read_bytes()
            raw = np.frombuffer((directory / (name + '.f32')).read_bytes(), dtype='<f4')
            requantized, clips = quantize_s16(raw)
            require(len(raw) == spec['samples'] and requantized.tobytes() == data
                    and arm['prequantization_clip_count'] == clips, 'quantization/accounting drift')
            require(arm['metrics'] == metrics(target, echo, samples(data)), 'metric recomputation mismatch')
            if name == 'passthrough':
                require(data == (directory / 'ap.s16').read_bytes(), 'passthrough altered observation')
            else:
                require(report['models_sha256'][name] == receipt['sources'][name]['files_sha256'][MODELS[name]['path']],
                        'wrong model identity')
                trace = load_json(directory / (name + '-trace.json'))
                require(arm['timing'] == time_summary(trace), 'timing recomputation mismatch')
                verify_trace(trace, spec['samples'], name)
            outputs[name].append({'case_id': row['case_id'], 'status': 'SUCCESS', 'exit_code': 0,
                                  'identity': identities[name], 'input_sha256': row['input_sha256'],
                                  'output_path': f'cases/{row["case_id"]}/{name}.s16', 'output_sha256': arm['output_sha256']})
    for name in plan['arms']:
        check_outputs(expected, outputs[name], root, contract, identities[name])
    require(report['conclusions'] == conclusions(report['cases'], plan), 'shortlist decision drift')
    return {'status': 'VERIFIED_LOCAL_DIAGNOSTIC', 'cases': 6, 'mixed_arms': 18,
            'decision': plan['decision'], 'conclusions': report['conclusions']}


def negative(root):
    original = load_json(root / 'result.json')
    mutations = {'missing-case': lambda r: r['cases'].pop(),
                 'promotion': lambda r: r.update(shipping_authority=True),
                 'holdout-relabel': lambda r: r.update(data_role='INDEPENDENT_HOLDOUT'),
                 'wrong-model': lambda r: r['models_sha256'].update(gtcrn='0' * 64),
                 'wrong-score': lambda r: r['cases'][0]['arms']['gtcrn']['metrics'].update(final_far_ratio_db=999),
                 'wrong-conclusion': lambda r: r['conclusions']['gtcrn'].update(
                     diagnostic_shortlist_rule_met=not r['conclusions']['gtcrn']['diagnostic_shortlist_rule_met']),
                 'missing-engineering': lambda r: r['engineering'].pop('gtcrn')}
    rejected = []
    with tempfile.TemporaryDirectory(prefix='fe-neural-negative-') as temporary:
        scratch = Path(temporary) / 'evidence'
        shutil.copytree(root, scratch)
        for name, change in mutations.items():
            altered = copy.deepcopy(original)
            change(altered)
            write_json(scratch / 'result.json', altered)
            seal_output(scratch, altered)
            try:
                verify(scratch)
            except (ValueError, KeyError, AssertionError):
                rejected.append(name)
            else:
                raise ValueError('resealed semantic negative accepted: ' + name)
        trace_path = scratch / 'cases' / original['cases'][0]['case_id'] / 'gtcrn-trace.json'
        original_trace = load_json(trace_path)
        for name in ('partial-timing', 'partial-availability'):
            trace, altered = copy.deepcopy(original_trace), copy.deepcopy(original)
            trace['push_ns' if name == 'partial-timing' else 'availability'].pop()
            altered['cases'][0]['arms']['gtcrn']['timing'] = time_summary(trace)
            write_json(trace_path, trace)
            write_json(scratch / 'result.json', altered)
            seal_output(scratch, altered)
            try:
                verify(scratch)
            except (ValueError, KeyError, AssertionError):
                rejected.append(name)
            else:
                raise ValueError('neural partial trace accepted: ' + name)
    return {'status': 'PASS', 'rejected': rejected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--negative-evidence', action='store_true')
    args = parser.parse_args()
    existed = args.output.exists()
    try:
        if args.negative_evidence:
            result = negative(args.output)
        elif args.verify:
            result = verify(args.output)
        else:
            require(args.archive is not None and args.source is not None, 'archive/source required')
            result = run(args.archive, args.source, args.output)
    except Exception as error:
        if not existed and args.output.exists():
            write_json(args.output / 'failure.json', {'error': str(error), 'shipping_authority': False})
        raise
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
