#!/usr/bin/env python3
"""Fixed full-utterance F05 validation; no optimization or historical replay."""
from __future__ import annotations

import argparse
import array
from dataclasses import replace
import importlib
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

from contracts import ROOT, hex_digest, load_json, require, sha256
import f05_speech_source as source

for directory in (ROOT / 'validation/tools', ROOT / 'tests/validation'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from build_validation_corpus import echo_from_render, interleave, scale
from build_quality_validation_corpus import fractional_delay, physical_tdoa_samples
import dualmic_profile_support as support
from authority import load_authority
import run_validation
import run_validation_engine as engine

PLAN = ROOT / '.github/research/frontend-evolution-v1/f05-dualmic-validation-v1.json'
STUDY = 'F05-DUALMIC-RESERVED-VALIDATION-V1'
STATUS = 'MEASUREMENT_COMPLETE_DESCRIPTIVE_ONLY'
RATE, FRAME, LEAD, TAIL = 16000, 160, 24000, 8000
PROFILES, SCENES = ('call', 'assistant'), ('near-only', 'doubletalk')
SOURCE_RECEIPT = '35fb4797cf67d004ae1646d61b7905a85bf376f7abbd031d4b3d58531ca57e5c'
SOURCE_REVISION = 'a058b02582962875ac10e6bb42b928c46c405213'
BASE = '5dc7176e0dde61944ba141952af7a9d8978a61f7'
COMPONENTS = ('mic_audio', 'render_audio', 'clean_near_audio', 'interference_audio')
FAILURE_PREFIXES = ('failure.json','failed-report.json','report-before-failure.json',
                    'artifact-manifest-before-failure.json')
CORRELATION_FILES = {
    'validation/tools/render_corr_exact.c':'19cbf9af3b3e36c5ca88546b4a6ab091af0292cbb2bffd69ac121eda70be90ac',
    'validation/tools/render_corr_exact.py':'0a2f720e5b1eb29f7f4174bcadc8bca0d88bc5d0e34b9b19337c13d683127a81',
    'validation/tools/run_validation_engine.py':'9082b061e7e46aa1c48c82c0ec845524110e01e910aa51e5b83c2c9d9594789a',
}


def write_json(path: Path, record) -> None:
    path.write_text(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def pcm_bytes(values) -> bytes:
    data = array.array('h', values)
    if sys.byteorder != 'little':
        data.byteswap()
    return data.tobytes()


def structural_support(near_frames: int, far_frames: int, scene: str) -> dict:
    """Potential sample support from metadata/FIR, never measured VAD activity."""
    result = {'meaning':'metadata-structural-envelope-not-VAD', 'near_support':[LEAD,LEAD+near_frames],
              'mic0':None, 'mic1':None}
    if scene == 'doubletalk':
        for channel, support_range in (('mic0',[320,far_frames+1120]), ('mic1',[321,far_frames+1122])):
            begin, end = max(LEAD,support_range[0]), min(LEAD+near_frames,support_range[1])
            count = max(0,end-begin)
            result[channel] = {'echo_support':support_range, 'near_intersection':[begin,end] if count else None,
                               'intersection_samples':count, 'fraction_of_original_near':count/near_frames}
    return result


def metadata_schedule(originals: list[dict]) -> list[dict]:
    """Metadata arithmetic only; no audio reads or signal-dependent choices."""
    speakers = sorted({row['speaker'] for row in originals})
    require(speakers == source.SELECTED and len(originals) == 32, 'wrong reserved source set')
    lookup = {(row['speaker'], row['ordinal']): row for row in originals}
    require(len(lookup) == 32 and set(lookup) == {(s, i) for s in speakers for i in range(4)}, 'missing/duplicate source ordinal')
    result = []
    for index, speaker in enumerate(speakers):
        far_speaker = speakers[index ^ 1]
        for ordinal in range(4):
            near, far = lookup[speaker, ordinal], lookup[far_speaker, ordinal]
            require(all(type(row['frames']) is int and 0 < row['frames'] <= 60 * RATE for row in (near, far)), 'invalid native sample count')
            for scene in SCENES:
                natural = LEAD + near['frames'] + TAIL if scene == 'near-only' else max(LEAD + near['frames'], far['frames']) + TAIL
                count = ((natural + FRAME - 1) // FRAME) * FRAME
                result.append({'speaker': speaker, 'ordinal': ordinal, 'near_member': near['member'],
                    'far_speaker': far_speaker, 'far_member': far['member'], 'scene': scene,
                    'samples_per_channel': count, 'near_mask': [LEAD, LEAD + near['frames']],
                    'frame_tail_padding_samples': count - natural,
                    'structural_support':structural_support(near['frames'],far['frames'],scene)})
    return result


def validate_plan(plan: dict) -> None:
    require(type(plan.get('schema_version')) is int and plan['schema_version'] == 1 and plan['study_id'] == STUDY, 'wrong F05 measurement contract')
    require(plan['implementation_base'] == BASE, 'wrong measurement base')
    item = plan['source']
    require(item['source_receipt_sha256'] == SOURCE_RECEIPT and item['preparation_revision'] == SOURCE_REVISION, 'source receipt/revision drift')
    require(item['archive'] == source.ARCHIVE and item['use_complete_pcm'] is True and item['use_adapter_4s_windows'] is False, 'wrong original source asset')
    require(item['speakers'] == source.SELECTED and item['preparation_plan_sha256'] ==
            'cde46538288219a077927eada139fea62c2bc156fa9bd478626aae139e0db4d3', 'source selection/plan drift')
    originals = item['originals']
    require(sum(row['frames'] for row in originals) == 5241680 and item['original_samples'] == 5241680 and
            item['original_seconds'] == 327.605 and item['original_files'] == 32, 'source coverage drift')
    require(len({row['member'] for row in originals}) == len({row['pcm_file'] for row in originals}) == 32, 'duplicate source file identity')
    for row in originals:
        require(hex_digest(row['pcm_sha256']) and hex_digest(row['flac_sha256']), 'invalid source digest')
        require(source.PATTERN.fullmatch(row['member']) is not None, 'invalid original identity')
        require(row['flac_file'] == 'flac/' + Path(row['member']).name and
                row['pcm_file'] == 'pcm/' + Path(row['member']).stem + '.s16', 'source path mismatch')
    role = plan['data_use']
    require(role['corpus_tier'] == 'validation-grade' and role['sealed_data'] is True and role['split'] == 'validation' and
            role['blind_status'] == 'NOT_BLIND' and role['role'] == 'reserved-validation-visible-scope-separated', 'reserved validation role drift')
    for key in ('universal_independence_established', 'training_allowed', 'optimizer_selection_allowed', 'promotion_allowed'):
        require(role[key] is False, 'invalid data authority: ' + key)
    render = plan['renderer']
    require(render['schedule'] == metadata_schedule(originals), 'metadata schedule changed')
    require((render['sample_rate_hz'], render['sample_bits'], render['mic_channels'], render['frame_samples'],
             render['near_lead_samples'], render['tail_samples']) == (RATE, 16, 2, FRAME, LEAD, TAIL), 'format/timeline drift')
    require(render['profiles'] == list(PROFILES) and render['scenes'] == list(SCENES), 'profile/scene drift')
    require(render['speaker_pairs'] == [[2412,2428],[2803,2902],[3000,3081],[3170,3536]], 'pairing drift')
    require(render['near_source_gain'] == render['far_source_gain'] == .25 and
            render['echo_taps'] == [[320,.52],[640,.21],[1120,.09]], 'source gain/echo path drift')
    require((render['mic_spacing_mm'], render['target_angle_degrees'], render['echo_angle_degrees'], render['sound_speed_mm_per_second']) ==
            (35., 0., 60., 343000.), 'synthetic geometry drift')
    measurement, processor = plan['measurement'], plan['processor']
    delays = {'raw': 0, 'call': 160, 'assistant': 160}
    require(measurement['primary_delays_samples'] == processor['source_declared_algorithmic_latency_samples'] == delays,
            'fixed primary delay drift')
    require(measurement['primary_function'] == 'validation/tools/run_validation_engine.py:si_sdr_span_with_identity' and
            measurement['primary_target_lag_searches'] == measurement['parameter_searches'] == 0 and
            measurement['secondary_target_refinement_ms'] == 3 and
            measurement['secondary_render_interference_maxcorr_radius_ms'] == 100 and
            measurement['no_metric_cherry_pick'] is True,
            'primary/secondary metric contract drift')
    require(processor['bundle_kind'] == 'AP_CURRENT_PORTABLE_V1' and processor['bundle_status'] == 'PASS_ENGINEERING_ONLY' and
            processor['default_pipeline_only'] is True and processor['metadata_queries_during_matrix'] == 0, 'processor scope drift')
    require(processor['source_declared_algorithmic_latency_ms'] == {'raw':0,'call':10,'assistant':10}, 'declared source latency drift')
    require(processor['engineering_copy_bound'] == {'files':512,'bytes':67108864}, 'AP engineering copy bound drift')
    native = measurement['secondary_native_transport']
    require(native['search_id'] == 'exact-all-integer-lags-stride4-v1' and
            native['source_files_sha256'] == CORRELATION_FILES and
            native['bundle_path_key'] == 'render_corr' and native['bundle_relative_file'] == 'lib/librender_corr_exact.so' and
            native['build_location'] == 'github-actions-only' and native['local_compilation_allowed'] is False and
            native['implicit_compile_fallback_allowed'] is False and
            native['scoring_factory'] == 'ap_current_ci.build_bound_max_abs_corr', 'precompiled exact-correlation method drift')
    expected = dict(generator_wall_seconds=120, matrix_wall_seconds=600, independent_readback_wall_seconds=600,
                    processor_case_wall_seconds=30, planned_audio_processor_calls=128, maximum_audio_processor_calls=128,
                    automatic_retries=0, parameter_searches=0, parallel_processors=1, base_inputs=64,
                    source_original_samples=5241680, source_original_seconds=327.605, total_output_samples=28277760,
                    total_output_seconds=1767.36, maximum_case_samples=479840, maximum_case_seconds=29.99,
                    output_payload_bytes_maximum=1073741824, output_files_maximum=4000)
    require(plan['budgets'] == expected, 'measurement budget drift')
    require(all(type(plan['budgets'][key]) is type(value) for key,value in expected.items()), 'budget numeric type drift')
    require(2 * sum(row['samples_per_channel'] for row in render['schedule']) == expected['total_output_samples'] and
            max(row['samples_per_channel'] for row in render['schedule']) == expected['maximum_case_samples'], 'schedule budget mismatch')
    require(plan['success_status'] == STATUS and plan['quality_decision'] == 'NO_PROMOTION_DESCRIPTIVE_VALIDATION' and
            plan['shipping_authority'] is False, 'completion authority drift')


def read_plan(digest: str) -> dict:
    require(hex_digest(digest) and source.file_hash(PLAN) == digest, 'frozen measurement plan SHA256 mismatch')
    result = load_json(PLAN)
    validate_plan(result)
    return result


def ap_module():
    # The real bundle helper is supplied by the same publicly frozen CI change.
    # Missing helper/bundle is an error, never a fixture or executable fallback.
    return importlib.import_module('ap_current_ci')


def code_identity(revision: str, *, require_head: bool = True) -> dict:
    require(hex_digest(revision, 40), 'exact frozen harness revision required')
    ap = ap_module()
    def git(*args):
        return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True, timeout=15).stdout
    require(git('rev-parse', revision + '^{commit}').decode().strip() == revision, 'not an exact harness commit')
    if require_head:
        require(git('rev-parse', 'HEAD').decode().strip() == revision, 'execution HEAD differs from harness revision')
    git('merge-base', '--is-ancestor', BASE, revision)
    names = set(source.CONTROLS) | {PLAN.relative_to(ROOT).as_posix(), 'validation/research-authority.json',
                                   'tests/validation/frontend_evolution/f05_dualmic_validation.py',
                                   'tests/validation/frontend_evolution/test_f05_dualmic_validation.py'}
    names.update(ap.CONTROL_FILES)
    names.update(CORRELATION_FILES)  # The canonical native score helper is a separate C source file.
    # Close all actual first-party imports, including the AP bundle helper's
    # dependencies, instead of omitting a transitive evaluator/identity module.
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        try:
            relative = Path(filename).resolve().relative_to(ROOT)
        except ValueError:
            continue
        if relative.suffix == '.py':
            names.add(relative.as_posix())
    files = {}
    for name in sorted(names):
        data = source.safe_local(ROOT / name).read_bytes()
        require(data == git('show', revision + ':' + name), 'harness control drift: ' + name)
        files[name] = sha256(data)
    return {'commit': revision, 'tree': git('rev-parse', revision + '^{tree}').decode().strip(), 'files_sha256': files}


def admit_source(archive: Path, directory: Path, plan: dict) -> dict:
    require(source.file_hash(directory / 'source-receipt.json') == SOURCE_RECEIPT, 'original reserved source receipt mismatch')
    prepared_plan = source.read_plan(plan['source']['preparation_plan_sha256'])
    source.verify(archive, directory, prepared_plan, SOURCE_REVISION)  # No codec.
    record = load_json(directory / 'source-receipt.json')
    require(record['role'] == plan['source']['original_role_unchanged'], 'original source role changed')
    actual = []
    for row in record['sources']:
        for ordinal, item in enumerate(row['originals']):
            actual.append({'speaker': row['speaker'], 'ordinal': ordinal, 'member': item['member'],
                'flac_file': item['file'], 'flac_sha256': item['sha256'], 'pcm_file': item['pcm_file'],
                'pcm_sha256': item['pcm_sha256'], 'frames': item['frames']})
    require(actual == plan['source']['originals'], 'reserved full-utterance asset drift')
    return record


def stem(schedule: dict) -> str:
    return f"f05-s{schedule['speaker']}-u{schedule['ordinal']:02d}-{schedule['scene']}"


def derive_case(schedule: dict, originals: dict[str, dict], pcm: dict[str, list[int]], plan: dict) -> tuple[dict, dict[str, bytes]]:
    """One fixed synthetic input. Original full PCM is never rewritten/cropped."""
    count = schedule['samples_per_channel']
    require(schedule['scene'] in SCENES, 'unregistered scene')
    near_original = pcm[schedule['near_member']]
    far_original = pcm[schedule['far_member']]
    require(len(near_original) == originals[schedule['near_member']]['frames'] and
            len(far_original) == originals[schedule['far_member']]['frames'], 'native PCM sample mismatch')
    require(count % FRAME == 0 and count >= LEAD + len(near_original) + TAIL, 'invalid complete-frame timeline')
    near = [0] * LEAD + scale(near_original, .25)
    near += [0] * (count - len(near))
    render, echo = None, None
    left = right = near
    tdoa = physical_tdoa_samples(35., 60.)
    if schedule['scene'] == 'doubletalk':
        render = scale(far_original, .25) + [0] * (count - len(far_original))
        require(len(render) == count, 'render cannot be silently truncated/padded by processor')
        echo = echo_from_render(render, [(320,.52),(640,.21),(1120,.09)])
        echo_right = fractional_delay(echo, tdoa)
        require(all(-32768 <= a + b <= 32767 for a, b in zip(near, echo)) and
                all(-32768 <= a + b <= 32767 for a, b in zip(near, echo_right)), 'input mix clipping; no gain adjustment')
        left, right = [a+b for a,b in zip(near,echo)], [a+b for a,b in zip(near,echo_right)]
    require(len(left) == len(right) == count, 'microphone channel length mismatch')
    base = stem(schedule)
    components = {'mic_audio': ('mic.s16', interleave(left, right)), 'render_audio': ('render.s16', render),
                  'clean_near_audio': ('clean-near.s16', near), 'interference_audio': ('interference.s16', echo)}
    case = {'case_id': base, 'scenario': schedule['scene'], 'split': 'validation', 'sample_rate_hz': RATE,
            'mic_channels': 2, 'vad_labels': None, 'echo_audio': None, 'processor_profile': 'default',
            'control': {}, 'expected': {}, 'source': {'dataset_id': 'librispeech-dev-clean-f05-reserved-v1', 'source_id': base},
            'quality': {'ground_truth': True, 'role': 'reserved-validation-descriptive'},
            'structural_support':schedule['structural_support'],
            'dimensions': {'speaker': schedule['speaker'], 'utterance_ordinal': schedule['ordinal'],
                'far_speaker': schedule['far_speaker'], 'original_samples': len(near_original),
                'samples_per_channel': count, 'capture_frames': count // FRAME,
                'near_mask_start': LEAD, 'near_mask_stop': LEAD + len(near_original),
                'frame_tail_padding_samples': schedule['frame_tail_padding_samples'],
                'mic_spacing_mm': 35., 'target_tdoa_samples': 0., 'echo_tdoa_samples': tdoa,
                'data_role': 'reserved-validation-visible-scope-separated', 'blind_status': 'NOT_BLIND',
                'recorded_source': True, 'real_array_recording': False, 'synthetic_propagation': True,
                'human_vad_labels': False}}
    files = {}
    for field, (name, values) in components.items():
        case[field] = f'cases/{base}/{name}' if values is not None else None
        if values is not None:
            files[case[field]] = pcm_bytes(values)
    return case, files


def all_cases(directory: Path, plan: dict):
    originals = {row['member']: row for row in plan['source']['originals']}
    pcm = {}
    for member, item in originals.items():
        path = source.safe_local(directory / item['pcm_file'])
        require(source.file_hash(path) == item['pcm_sha256'] and path.stat().st_size == item['frames'] * 2, 'full PCM identity mismatch')
        pcm[member] = list(engine.read_raw_array(path))
    for item in plan['renderer']['schedule']:
        yield derive_case(item, originals, pcm, plan)


def file_manifest(directory: Path, plan: dict, *, exclude: tuple[str, ...] = ()) -> dict:
    files, total = {}, 0
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'symlink in evidence')
        if path.is_dir():
            continue
        require(path.is_file(), 'special evidence file')
        name = path.relative_to(directory).as_posix()
        if name in exclude:
            continue
        size = path.stat().st_size
        total += size
        require(len(files) < plan['budgets']['output_files_maximum'] and total <= plan['budgets']['output_payload_bytes_maximum'], 'evidence output bound')
        files[name] = {'bytes': size, 'sha256': source.file_hash(path)}
    return files


def build_corpus(archive: Path, directory: Path, output: Path, plan: dict, controls: dict) -> dict:
    admit_source(archive, directory, plan)
    shutil.copytree(directory, output / 'source')
    cases = []
    for case, files in all_cases(output / 'source', plan):
        for name, data in files.items():
            path = output / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        for profile in PROFILES:
            cases.append({**case, 'case_id': case['case_id'] + '-' + profile, 'pipeline_profile': profile,
                          'dimensions': {**case['dimensions'], 'pipeline_profile': profile}})
    manifest = {'schema_version': 1, 'study_id': STUDY, 'plan_sha256': source.file_hash(PLAN), 'controls': controls,
                'source_receipt_sha256': SOURCE_RECEIPT, 'data_use': plan['data_use'],
                'files': file_manifest(output, plan)}
    write_json(output / 'source-manifest.json', manifest)
    corpus = {'schema_version': 1, 'corpus_id': 'f05-reserved-dualmic-full-utterance-v1', 'experiment': STUDY,
              'tier': 'validation-grade', 'sealed_data': True, 'quality_decision': plan['quality_decision'],
              'data_use': plan['data_use'], 'sources': ['librispeech-dev-clean-f05-reserved-v1'],
              'source_manifest_sha256': source.file_hash(output / 'source-manifest.json'),
              'generator': {'name': Path(__file__).name, 'source_sha256': source.file_hash(Path(__file__)),
                            'plan_sha256': source.file_hash(PLAN)}, 'cases': cases}
    write_json(output / 'corpus.json', corpus)
    verify_corpus(archive, output / 'corpus.json', plan, controls)
    return corpus


def verify_corpus(archive: Path, path: Path, plan: dict, controls: dict) -> dict:
    require(path.name == 'corpus.json', 'wrong corpus entry')
    directory = source.safe_local(path.parent)
    corpus, manifest = load_json(path), load_json(directory / 'source-manifest.json')
    require(manifest['study_id'] == STUDY and manifest['controls'] == controls and
            manifest['plan_sha256'] == source.file_hash(PLAN) and manifest['source_receipt_sha256'] == SOURCE_RECEIPT and
            manifest['data_use'] == plan['data_use'], 'new corpus authority/source drift')
    require(corpus['experiment'] == STUDY and corpus['tier'] == 'validation-grade' and corpus['sealed_data'] is True and
            corpus['data_use'] == plan['data_use'] and corpus['quality_decision'] == plan['quality_decision'], 'corpus tier/role drift')
    require(corpus['source_manifest_sha256'] == source.file_hash(directory / 'source-manifest.json'), 'corpus manifest hash drift')
    require(file_manifest(directory, plan, exclude=('source-manifest.json','corpus.json')) == manifest['files'], 'corpus file closure drift')
    admit_source(archive, directory / 'source', plan)
    expected_cases = []
    expected_files = {'source/' + p.relative_to(directory / 'source').as_posix()
                      for p in (directory / 'source').rglob('*') if p.is_file()}
    for case, files in all_cases(directory / 'source', plan):
        for name, data in files.items():
            require((directory / name).read_bytes() == data, 'fixed derivative changed: ' + name)
            expected_files.add(name)
        for profile in PROFILES:
            expected_cases.append({**case, 'case_id': case['case_id'] + '-' + profile, 'pipeline_profile': profile,
                                   'dimensions': {**case['dimensions'], 'pipeline_profile': profile}})
    require(expected_cases == corpus['cases'] and len(expected_cases) == 128 and set(manifest['files']) == expected_files,
            'fixed case/source set changed')
    require(corpus['generator'] == {'name': Path(__file__).name, 'source_sha256': source.file_hash(Path(__file__)),
                                   'plan_sha256': source.file_hash(PLAN)}, 'generator identity drift')
    run_validation.validate_corpus_shape(corpus, load_authority())
    return corpus


def finite(value) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite(item) for item in value.values())
    if isinstance(value, list):
        return all(finite(item) for item in value)
    return True


def read_trace(path: Path, count: int) -> list[dict]:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate telemetry key')
            result[key] = value
        return result
    def constant(_value):
        raise ValueError('nonfinite telemetry')
    text = path.read_text(encoding='utf-8')
    require(text.endswith('\n') and type(count) is int and count > 0, 'truncated telemetry/invalid frame count')
    rows = [json.loads(line, object_pairs_hook=pairs, parse_constant=constant) for line in text.splitlines()]
    require(len(rows) == count and all(isinstance(row, dict) and set(row) == ap_module().TRACE_KEYS and finite(row) and
                        all(type(value) in (int,float) for value in row.values()) and
                        all(row[key] in (0,1) for key in ('vad_active','far_end_active','double_talk_active','erle_valid','aec_converged')) and
                        type(row.get('frame')) is int and row['frame'] == index and
                        type(row.get('algorithmic_latency_ms')) is int and row['algorithmic_latency_ms'] == 10
                        for index,row in enumerate(rows)), 'declared pipeline latency/telemetry changed')
    return rows


def check_case_streams(corpus_path: Path, case: dict) -> None:
    count = case['dimensions']['samples_per_channel']
    require(type(count) is int and count > 0 and count % FRAME == 0, 'invalid frame count')
    require(case['mic_channels'] == 2 and case['sample_rate_hz'] == RATE and
            case['pipeline_profile'] in PROFILES and case['processor_profile'] == 'default' and not case['control'] and
            case['scenario'] in SCENES and case.get('echo_audio') is None, 'non-frozen processor configuration')
    for field in COMPONENTS:
        name = case[field]
        present = field in ('mic_audio','clean_near_audio') or case['scenario'] == 'doubletalk'
        require((name is not None) == present, 'unexpected component presence')
        if present:
            path = source.safe_local(corpus_path.parent / name)
            require(source.safe_local(corpus_path.parent) in path.parents and
                    path.is_file() and path.stat().st_size == count * (4 if field == 'mic_audio' else 2),
                    'complete component frame/length mismatch: ' + field)


def fixed_primary(clean, raw, outputs: dict, mask: list[int], delays: dict) -> dict:
    """Only source-declared lags. Never call aligned_span/correlation here."""
    require(delays == {'raw':0,'call':160,'assistant':160} and set(outputs) == set(PROFILES), 'fixed primary lag/view drift')
    require(len(mask) == 2 and all(type(x) is int for x in mask) and 0 <= mask[0] < mask[1], 'invalid original-near mask')
    views = {'raw':raw, **outputs}
    start = max(mask[0], 0, *(-delays[name] for name in views))
    stop = min(mask[1], len(clean), *(len(values) - delays[name] for name, values in views.items()))
    require(start == mask[0] and stop == mask[1] and stop - start >= 16, 'entire native near support must survive common span')
    result = {'near_mask': mask, 'common_reference_start': start, 'common_reference_stop': stop,
              'common_samples': stop - start, 'fixed_delays_samples': delays, 'primary_target_lag_searches': 0}
    for name, values in views.items():
        score, identical = engine.si_sdr_span_with_identity(clean, values, start, start + delays[name], stop - start)
        result[name + '_near_si_sdr_db'] = score
        result[name + '_near_reference_identical'] = identical
    for profile in PROFILES:
        raw_score, score = result['raw_near_si_sdr_db'], result[profile + '_near_si_sdr_db']
        result[profile + '_minus_raw_db'] = None if raw_score is None or score is None else score - raw_score
    require(finite(result), 'nonfinite primary measurement')
    return result


def primary_records(root: Path, corpus: dict, plan: dict) -> list[dict]:
    cases = {row['case_id']:row for row in corpus['cases']}
    records = []
    for item in plan['renderer']['schedule']:
        base = stem(item)
        case = cases[base + '-call']
        clean = engine.read_raw_array(root / 'input' / case['clean_near_audio'])
        mic = engine.read_raw_array(root / 'input' / case['mic_audio'])
        raw = engine.mono_view(mic, 2)
        outputs = {profile:engine.read_raw_array(root / 'replay' / (base + '-' + profile) / 'out.pcm') for profile in PROFILES}
        measured = fixed_primary(clean, raw, outputs, item['near_mask'], plan['measurement']['primary_delays_samples'])
        records.append({'base_case_id':base, 'speaker':item['speaker'], 'ordinal':item['ordinal'], 'scene':item['scene'],
                        'near_member':item['near_member'], 'far_member':item['far_member'],
                        'structural_support':item['structural_support'], **measured})
    require(len(records) == 64, 'incomplete primary source/scenario set')
    return records


def primary_summary(records: list[dict]) -> dict:
    result = {'source_speakers': 8, 'original_utterances':32, 'speaker_pairs':4,
              'output_views_are_correlated':True, 'universal_independence_established':False, 'groups':[]}
    for scene in SCENES:
        for profile in PROFILES:
            speakers = []
            for speaker in source.SELECTED:
                rows = [row for row in records if row['scene'] == scene and row['speaker'] == speaker]
                require(len(rows) == 4, 'missing fixed speaker utterances')
                values = [row[profile + '_minus_raw_db'] for row in rows]
                valid = [value for value in values if value is not None]
                speakers.append({'speaker':speaker, 'utterance_deltas_db':values, 'valid':len(valid), 'null':4-len(valid),
                    'mean_delta_db':statistics.mean(valid) if valid else None,
                    'median_delta_db':statistics.median(valid) if valid else None,
                    'raw_reference_identical_utterances':sum(row['raw_near_reference_identical'] for row in rows)})
            means = [row['mean_delta_db'] for row in speakers if row['mean_delta_db'] is not None]
            result['groups'].append({'scene':scene, 'profile':profile, 'speaker_results':speakers,
                'median_speaker_mean_delta_db':statistics.median(means) if means else None,
                'min_speaker_mean_delta_db':min(means) if means else None,
                'max_speaker_mean_delta_db':max(means) if means else None, 'speakers_with_valid_metric':len(means)})
    return result


def secondary_summary(corpus: dict, results: list[dict]) -> dict:
    semantics = support.validation_semantics()
    policy = {'allowed_tiers':['validation-grade'], 'minimum_cases':128, 'required_scenarios':list(SCENES)}
    summary, violations = run_validation.policy_violations(policy, corpus, results, load_authority(),
        engine_policy_violations=semantics.engine_policy_violations)
    require(not violations, 'canonical structural/policy violations: ' + json.dumps(violations))
    return summary


def check_engineering(record: dict, bundle: dict, revision: str) -> None:
    manifest = bundle['manifest']
    require(manifest['kind'] == 'AP_CURRENT_PORTABLE_V1' and manifest['status'] == 'PASS_ENGINEERING_ONLY' and
            manifest['code_revision'] == revision, 'processor bundle/harness revision mismatch')
    require(record['status'] == 'PASS_ENGINEERING_ONLY' and record['source_revision'] == revision and
            record['processor_sha256'] == manifest['files'][manifest['paths']['processor']] and
            record['build_info_sha256'] == manifest['files'][manifest['paths']['build_info']], 'engineering/binary identity mismatch')
    require(record['algorithmic_latency_samples'] == {'call':160,'assistant':160} and
            record['algorithmic_latency_ms'] == {'call':10,'assistant':10}, 'engineering declared latency mismatch')
    require(record['implicit_default_equals_call'] is True and set(record['default_tuning']) == set(PROFILES), 'default tuning evidence missing')
    for tuning in record['default_tuning'].values():
        require(set(tuning) == {'aec_mu','ns_floor','agc_target_dbfs','limiter_dbfs'} and
                all(type(value) in (int,float) and math.isfinite(value) for value in tuning.values()), 'invalid default tuning')


def copy_tree(source_dir: Path, destination: Path, plan: dict, *, engineering: bool = False) -> None:
    source_dir = source.safe_local(source_dir)
    destination = source.safe_local(destination)
    disjoint_output(destination, [source_dir])
    files = file_manifest(source_dir, plan)
    if engineering:
        bound = plan['processor']['engineering_copy_bound']
        require(len(files) <= bound['files'] and sum(row['bytes'] for row in files.values()) <= bound['bytes'], 'host engineering directory bound')
    require(not destination.exists(), 'retained directory must be fresh')
    shutil.copytree(source_dir, destination)
    require(file_manifest(destination, plan) == files, 'retained copy drift')


def disjoint_output(output: Path, inputs: list[Path]) -> None:
    for item in inputs:
        require(output != item and output not in item.parents and item not in output.parents,
                'output/input directory overlap')


def check_execution_paths(report: dict, bundle: dict) -> None:
    value = report['execution_root']
    require(isinstance(value,str) and '\\' not in value, 'invalid original execution directory')
    root = Path(value)
    require(root.is_absolute() and str(root) == value and '..' not in root.parts, 'noncanonical original execution directory')
    require(report['processor_execution_path'] == str(root/'bundle'/bundle['manifest']['paths']['processor']),
            'recorded processor command is not the retained verified binary')


def expected_command(report: dict, case: dict) -> list[str]:
    original_root = Path(report['execution_root'])
    work = original_root / 'replay' / case['case_id']
    command = [report['processor_execution_path'], '--profile', case['pipeline_profile'], '--sample-rate', '16000',
               '--mic-channels', '2', '--strict-capture-frames', '--metrics-jsonl', str(work / 'metrics.jsonl')]
    mic = str(original_root / 'input' / case['mic_audio'])
    if case['render_audio'] is None:
        return command + ['--capture-profile','default','--capture-only',mic,str(work/'out.pcm')]
    return command + [mic,str(original_root/'input'/case['render_audio']),str(work/'out.pcm')]


def retained_case(root: Path, report: dict, case: dict):
    check_case_streams(root/'input/corpus.json', case)
    directory = root/'replay'/case['case_id']
    require(json.loads((directory/'command.json').read_text()) == expected_command(report, case), 'retained command differs from fixed profile/configuration')
    execution = load_json(directory/'execution.json')
    require(type(execution.get('returncode')) is int and execution['returncode'] == 0 and type(execution['elapsed_seconds']) in (int,float) and
            math.isfinite(execution['elapsed_seconds']) and 0 <= execution['elapsed_seconds'] <= 30, 'per-case execution failure/budget')
    output, trace = engine.read_raw_array(directory/'out.pcm'), read_trace(directory/'metrics.jsonl', case['dimensions']['capture_frames'])
    inputs = {'mic':engine.read_raw_array(root/'input'/case['mic_audio']),
              'render':engine.read_raw_array(root/'input'/case['render_audio']) if case['render_audio'] is not None else None}
    continuity = support.continuity(case, output, trace, inputs)
    require(continuity == load_json(directory/'continuity.json'), 'retained continuity changed')
    return output, trace, inputs


def replay_layout(root: Path, cases: list[dict], matrix_seconds: float | None = None) -> float:
    require(not any((root/name).exists() for name in FAILURE_PREFIXES), 'failure prefix cannot become a successful measurement')
    directory = root/'replay'
    children = list(directory.iterdir())
    require(all(path.is_dir() and not path.is_symlink() for path in children) and
            {path.name for path in children} == {case['case_id'] for case in cases} and len(children) == 128,
            'replay must contain exactly the frozen 128 case directories')
    expected = {'command.json','execution.json','stdout.txt','stderr.txt','out.pcm','metrics.jsonl','continuity.json'}
    times = []
    for path in children:
        members = list(path.iterdir())
        require({p.name for p in members} == expected and all(p.is_file() and not p.is_symlink() for p in members),
                'unexpected replay case payload')
        execution = load_json(path/'execution.json')
        value = execution['elapsed_seconds']
        require(type(execution.get('returncode')) is int and execution['returncode'] == 0 and type(value) in (int,float) and math.isfinite(value) and 0 <= value <= 30,
                'invalid sequential case timing')
        times.append(value)
    total = math.fsum(times)
    if matrix_seconds is not None:
        require(total <= matrix_seconds <= 600, 'sequential processor time exceeds recorded matrix wall time')
    return total


def precompiled_scoring(bundle_root: Path, bundle: dict, plan: dict, ap):
    """Load the CI helper explicitly, never the old automatic compiler path."""
    native = plan['measurement']['secondary_native_transport']
    for name,digest in CORRELATION_FILES.items():
        require(source.file_hash(ROOT/name) == digest, 'canonical correlation source/loader drift: ' + name)
    module = run_validation.render_corr_exact
    require(Path(module.__file__).resolve() == ROOT/'validation/tools/render_corr_exact.py' and
            module.SEARCH_ID == native['search_id'], 'wrong loaded canonical correlation module')
    relative = bundle['manifest']['paths'][native['bundle_path_key']]
    require(relative == native['bundle_relative_file'], 'wrong precompiled correlation artifact path')
    binary = source.safe_local(bundle_root/relative)
    require(source.file_hash(binary) == bundle['manifest']['files'][relative], 'precompiled correlation binary drift')
    binding = ap.bind_render_corr_native(bundle_root, module=module)
    require(isinstance(binding,dict) and finite(binding) and type(binding.get('schema_version')) is int and
            binding['schema_version'] == 1 and binding['status'] == 'BOUND_PREBUILT_VALIDATION_HELPER' and
            binding['code_revision'] == bundle['manifest']['code_revision'] and binding['search_id'] == native['search_id'] and
            binding['library'] == relative and binding['binary_sha256'] == source.file_hash(binary) and
            binding['source_sha256'] == CORRELATION_FILES['validation/tools/render_corr_exact.c'] and
            binding['loader_sha256'] == CORRELATION_FILES['validation/tools/render_corr_exact.py'] and
            binding['engine_sha256'] == CORRELATION_FILES['validation/tools/run_validation_engine.py'] and
            binding['compiler'] and binding['abi'] and binding['local_compilation'] is False,
            'invalid precompiled correlation binding')
    guarded = ap.build_bound_max_abs_corr(bundle_root, engine.normalized_corr, module=module)
    require(callable(guarded), 'missing guarded precompiled correlation scorer')
    record = {'search_id':native['search_id'], 'source_files_sha256':CORRELATION_FILES,
              'bundle_relative_file':relative, 'binary_sha256':source.file_hash(binary),
              'binding':binding, 'local_c_compilations':0, 'implicit_compile_fallback_allowed':False}
    return record, guarded


def check_math_runtime(runtime: dict, engineering: dict, ap) -> None:
    require(runtime['loader_environment'] == 'CLEAN_AT_START_AND_NOW' and
            type(runtime['pid']) is int and runtime['pid'] > 0 and runtime['parent_library_mappings'],
            'invalid math helper parent-process observation')
    require(ap.normalize_render_corr_runtime(runtime['runtime_identity']) ==
            ap.normalize_render_corr_runtime(engineering['runtime_identity']['render_corr']),
            'measurement math helper host/libraries differ from selected engineering')


def execution_semantics(retain_root: Path, environment: dict, max_abs_corr):
    """Bind actual invocation to the same environment used for host identity."""
    semantics = support.validation_semantics()
    def clean_run(command, **kwargs):
        require('env' not in kwargs, 'unexpected processor environment override')
        return subprocess.run(command, env=environment, **kwargs)
    return replace(semantics, evaluation=replace(semantics.evaluation,
        invoke=support.build_invoke(semantics.evaluation.invoke, retain_root=retain_root, run_command=clean_run),
        max_abs_corr=max_abs_corr))


def run_matrix(archive: Path, corpus_path: Path, bundle_root: Path, engineering_receipt: Path | None,
               output: Path, plan: dict, controls: dict, started: float) -> dict:
    corpus = verify_corpus(archive, corpus_path, plan, controls)
    ap = ap_module()
    bundle = ap.verify_bundle(bundle_root)
    host = ap.require_host_engineering(bundle_root, engineering_receipt)
    check_engineering(host['engineering'], bundle, controls['commit'])
    copy_tree(bundle_root, output/'bundle', plan)
    copy_tree(Path(host['receipt']).parent, output/'engineering-used', plan, engineering=True)
    used_receipt = output/'engineering-used'/Path(host['receipt']).name
    retained_bundle = ap.verify_bundle(output/'bundle')
    preserved_engineering = ap.verify_engineering(output/'bundle', used_receipt)
    require(preserved_engineering == host['engineering'], 'retained host engineering changed')
    copy_tree(corpus_path.parent, output/'input', plan)
    for name, digest in controls['files_sha256'].items():
        destination = output/'source-tree'/name; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/name, destination)
        require(source.file_hash(destination) == digest, 'source snapshot copy mismatch')
    processor = retained_bundle['paths']['processor']
    # Load only the retained copy. No library from the caller's input bundle is
    # loaded first, and no canonical score can fall back to host compilation.
    correlation, guarded_corr = precompiled_scoring(output/'bundle', retained_bundle, plan, ap)
    math_runtime = ap.render_corr_runtime_identity(output/'bundle', module=run_validation.render_corr_exact)
    check_math_runtime(math_runtime,host['engineering'],ap)
    report = {'schema_version':1, 'study_id':STUDY, 'status':'INCOMPLETE', 'harness_revision':controls['commit'],
        'processor_revision':bundle['manifest']['code_revision'], 'controls':controls, 'plan_sha256':source.file_hash(PLAN),
        'data_use':plan['data_use'], 'source_receipt_sha256':SOURCE_RECEIPT,
        'source_archive_sha256':plan['source']['archive']['sha256'], 'corpus_sha256':source.file_hash(corpus_path),
        'processor_sha256':source.file_hash(processor), 'bundle_manifest_sha256':source.file_hash(output/'bundle/bundle.json'),
        'engineering_receipt':used_receipt.relative_to(output).as_posix(), 'engineering_receipt_sha256':source.file_hash(used_receipt),
        'runtime_identity':host['runtime_identity'], 'default_tuning':host['engineering']['default_tuning'],
        'algorithmic_latency_samples':{'raw':0,'call':160,'assistant':160},
        'execution_root':str(output), 'processor_execution_path':str(processor), 'cases':[],
        'processor_calls_attempted':0, 'processor_calls_completed':0, 'metadata_queries_during_matrix':0,
        'automatic_retries':0, 'parameter_searches':0, 'primary_target_lag_searches':0,
        'secondary_target_refinement_ms':3, 'secondary_alignment_method':'existing-canonical-bounded-correlation',
        'secondary_render_interference_maxcorr_radius_ms':100,
        'secondary_native_correlation':correlation, 'local_c_compilations':0,
        'math_runtime_identity':math_runtime, 'math_runtime_observations':1,
        'math_runtime_observation_method':'read-only-ldd-and-proc-self-environ-maps',
        'shipping_authority':False, 'promotion_allowed':False, 'quality_decision':plan['quality_decision'],
        'not_run':plan['not_run']}
    check_execution_paths(report, retained_bundle)
    write_json(output/'progress.json', report)
    environment = ap.execution_environment()
    semantics = execution_semantics(output/'replay', environment, guarded_corr)
    require(support.PROCESS_TIMEOUT_SECONDS == plan['budgets']['processor_case_wall_seconds'], 'existing invocation timeout drift')
    for case in corpus['cases']:
        require(time.monotonic()-started < 600 and report['processor_calls_attempted'] < 128, 'matrix budget/call limit')
        check_case_streams(output/'input/corpus.json', case)
        report['processor_calls_attempted'] += 1
        write_json(output/'progress.json', report)
        result = semantics.evaluate_case(processor, output/'input/corpus.json', case, semantics.evaluation)
        retained_case(output, report, case)
        require(finite(result) and not any(key.startswith('vad_') for key in result['metrics']), 'invalid/unlabelled secondary metric')
        report['cases'].append(result)
        report['processor_calls_completed'] += 1
        write_json(output/'progress.json', report)
    require(report['processor_calls_attempted'] == report['processor_calls_completed'] == len(report['cases']) == 128, 'incomplete matrix')
    report['processor_wall_seconds_sum'] = replay_layout(output, corpus['cases'])
    report['primary'] = primary_records(output, corpus, plan)
    report['primary_summary'] = primary_summary(report['primary'])
    report['secondary_canonical_summary'] = secondary_summary(corpus, report['cases'])
    report['source_original_samples'] = 5241680
    report['total_output_samples'] = sum(case['dimensions']['samples_per_channel'] for case in corpus['cases'])
    require(report['total_output_samples'] == plan['budgets']['total_output_samples'], 'output duration budget mismatch')
    require(ap.require_host_engineering(output/'bundle', used_receipt)['runtime_identity'] == host['runtime_identity'], 'host/runtime changed during measurement')
    require(ap.verify_bundle(output/'bundle')['manifest'] == bundle['manifest'], 'processor bundle changed')
    require(precompiled_scoring(output/'bundle', retained_bundle, plan, ap)[0] == correlation, 'native correlation binding changed during measurement')
    report['math_runtime_identity_after'] = ap.render_corr_runtime_identity(output/'bundle', module=run_validation.render_corr_exact)
    report['math_runtime_observations'] = 2
    check_math_runtime(report['math_runtime_identity_after'],host['engineering'],ap)
    require(report['math_runtime_identity_after'] == math_runtime, 'math helper runtime changed during measurement')
    require(code_identity(controls['commit']) == controls, 'harness changed during measurement')
    require(file_manifest(output/'input', plan) == file_manifest(corpus_path.parent, plan), 'retained input changed during measurement')
    source.check_archive(archive, plan['source']['archive'])
    report['status'] = STATUS
    report['matrix_wall_seconds'] = time.monotonic()-started
    require(report['processor_wall_seconds_sum'] <= report['matrix_wall_seconds'] <= 600, 'matrix wall budget exceeded/inconsistent')
    return report


def seal_measurement(output: Path, report: dict, plan: dict, started: float) -> None:
    """All payload hashing is inside the same 600s timer as the real calls."""
    write_json(output/'report.json', report)
    phase = {'schema_version':1, 'status':'COMPLETE', 'returncode':0, 'matrix_wall_seconds':time.monotonic()-started,
             'budget_seconds':600, 'processor_calls':128, 'automatic_retries':0}
    write_json(output/'execution-phase.json', phase)
    manifest = {'schema_version':1, 'study_id':STUDY, 'files':file_manifest(output, plan, exclude=('artifact-manifest.json',))}
    elapsed = time.monotonic()-started
    require(elapsed <= 600, 'final payload sealing exceeds matrix wall budget')
    report['matrix_wall_seconds'] = phase['matrix_wall_seconds'] = elapsed
    write_json(output/'report.json', report)
    write_json(output/'execution-phase.json', phase)
    for name in ('report.json','execution-phase.json'):
        path = output/name
        manifest['files'][name] = {'bytes':path.stat().st_size, 'sha256':source.file_hash(path)}
    write_json(output/'artifact-manifest.json', manifest)
    require(time.monotonic()-started <= 600, 'late matrix finalization timeout')


def verify_measurement(archive: Path, output: Path, plan: dict, revision: str) -> dict:
    """Renderer/metric recomputation only; no decoder or measured processor."""
    started = time.monotonic()
    output = source.safe_local(output)
    report, phase = load_json(output/'report.json'), load_json(output/'execution-phase.json')
    require(not any((output/name).exists() for name in FAILURE_PREFIXES), 'failure prefix cannot pass readback')
    require(report['schema_version'] == 1 and report['study_id'] == STUDY and report['status'] == STATUS and
            report['harness_revision'] == report['processor_revision'] == revision and finite(report), 'measurement completion/identity drift')
    require(phase['status'] == 'COMPLETE' and type(phase['returncode']) is int and phase['returncode'] == 0 and phase['processor_calls'] == 128 and
            phase['automatic_retries'] == 0 and phase['budget_seconds'] == 600 and
            type(phase['matrix_wall_seconds']) in (int,float) and math.isfinite(phase['matrix_wall_seconds']) and
            0 < phase['matrix_wall_seconds'] <= 600 and report['matrix_wall_seconds'] == phase['matrix_wall_seconds'],
            'measurement process/budget mismatch')
    require(report['processor_calls_attempted'] == report['processor_calls_completed'] == len(report['cases']) == 128 and
            report['metadata_queries_during_matrix'] == report['automatic_retries'] == report['parameter_searches'] ==
            report['primary_target_lag_searches'] == report['local_c_compilations'] == 0, 'non-frozen call/search/compile counts')
    require(report['data_use'] == plan['data_use'] and report['not_run'] == plan['not_run'] and
            report['source_receipt_sha256'] == SOURCE_RECEIPT and report['source_archive_sha256'] == plan['source']['archive']['sha256'] and
            report['shipping_authority'] is False and report['promotion_allowed'] is False and
            report['quality_decision'] == plan['quality_decision'], 'measurement data/authority drift')
    require(report['plan_sha256'] == source.file_hash(PLAN) and report['algorithmic_latency_samples'] == {'raw':0,'call':160,'assistant':160} and
            report['secondary_target_refinement_ms'] == 3 and report['secondary_render_interference_maxcorr_radius_ms'] == 100 and
            report['secondary_alignment_method'] == 'existing-canonical-bounded-correlation', 'metric method drift')
    manifest = load_json(output/'artifact-manifest.json')
    require(manifest['schema_version'] == 1 and manifest['study_id'] == STUDY and
            file_manifest(output, plan, exclude=('artifact-manifest.json',)) == manifest['files'], 'measurement artifact closure mismatch')
    controls = code_identity(revision, require_head=False)
    require(controls == report['controls'], 'frozen harness control mismatch')
    for name, digest in controls['files_sha256'].items():
        require(source.file_hash(output/'source-tree'/name) == digest, 'retained harness source drift')
    ap = ap_module()
    bundle = ap.verify_bundle(output/'bundle')
    check_execution_paths(report, bundle)
    require(source.file_hash(output/'bundle/bundle.json') == report['bundle_manifest_sha256'] and
            source.file_hash(bundle['paths']['processor']) == report['processor_sha256'], 'retained bundle/binary drift')
    engineering_path = source.safe_local(output/report['engineering_receipt'])
    require(output in engineering_path.parents and source.file_hash(engineering_path) == report['engineering_receipt_sha256'], 'retained engineering path/hash drift')
    engineering = ap.verify_engineering(output/'bundle', engineering_path)
    check_engineering(engineering, bundle, revision)
    require(ap.normalize_runtime(engineering['runtime_identity']) == ap.normalize_runtime(report['runtime_identity']) and
            engineering['default_tuning'] == report['default_tuning'], 'recorded host/default tuning drift')
    correlation, guarded_corr = precompiled_scoring(output/'bundle', bundle, plan, ap)
    require(correlation == report['secondary_native_correlation'], 'recorded native correlation binding drift')
    require(report['math_runtime_observations'] == 2 and
            report['math_runtime_observation_method'] == 'read-only-ldd-and-proc-self-environ-maps' and
            report['math_runtime_identity'] == report['math_runtime_identity_after'],
            'recorded measurement math runtime changed')
    check_math_runtime(report['math_runtime_identity'],engineering,ap)
    reader_math_runtime = ap.render_corr_runtime_identity(output/'bundle', module=run_validation.render_corr_exact)
    corpus = verify_corpus(archive, output/'input/corpus.json', plan, controls)
    require(source.file_hash(output/'input/corpus.json') == report['corpus_sha256'], 'retained corpus identity changed')
    require(replay_layout(output, corpus['cases'], report['matrix_wall_seconds']) == report['processor_wall_seconds_sum'], 'sequential timing readback changed')
    semantics = support.validation_semantics()
    def no_processor(_processor, case, _corpus_path, _temporary):
        return retained_case(output, report, case)
    evaluation = replace(semantics.evaluation, invoke=no_processor, max_abs_corr=guarded_corr)
    measured = [semantics.evaluate_case(Path('unused-no-processor'), output/'input/corpus.json', case, evaluation)
                for case in corpus['cases']]
    require(measured == report['cases'] and finite(measured), 'canonical secondary readback changed')
    primary = primary_records(output, corpus, plan)
    require(primary == report['primary'] and primary_summary(primary) == report['primary_summary'], 'fixed-delay primary readback changed')
    require(secondary_summary(corpus, measured) == report['secondary_canonical_summary'], 'canonical secondary summary changed')
    total = sum(case['dimensions']['samples_per_channel'] for case in corpus['cases'])
    require(total == report['total_output_samples'] == 28277760 and report['source_original_samples'] == 5241680, 'coverage/duration drift')
    require(precompiled_scoring(output/'bundle', bundle, plan, ap)[0] == correlation, 'native correlation binding changed during readback')
    reader_math_runtime_after = ap.render_corr_runtime_identity(output/'bundle', module=run_validation.render_corr_exact)
    require(reader_math_runtime_after == reader_math_runtime, 'reader math helper runtime changed')
    require(code_identity(revision, require_head=False) == controls, 'reader control drift')
    elapsed = time.monotonic()-started
    require(elapsed <= 600, 'independent readback wall budget exceeded')
    return {'schema_version':1, 'study_id':STUDY, 'status':'DESCRIPTIVE_MEASUREMENT_READBACK_VERIFIED',
            'harness_revision':revision, 'report_sha256':source.file_hash(output/'report.json'),
            'artifact_manifest_sha256':source.file_hash(output/'artifact-manifest.json'),
            'cases':128, 'original_utterances':32, 'source_speakers':8, 'source_original_seconds':327.605,
            'output_seconds':total/RATE, 'processor_invocations':0, 'decoder_invocations':0,
            'local_c_compilations':0, 'secondary_native_correlation':correlation,
            'reader_math_runtime_identity':reader_math_runtime, 'reader_math_runtime_identity_after':reader_math_runtime_after,
            'math_runtime_observations':2, 'runtime_observation_method':'read-only-ldd-and-proc-self-environ-maps',
            'subprocess_policy':'Git identity and read-only ldd observations allowed; no SDK, codec or compiler execution',
            'renderer_reconstruction':True, 'primary_target_lag_searches':0, 'secondary_target_refinement_ms':3,
            'secondary_render_interference_maxcorr_radius_ms':100, 'elapsed_seconds':elapsed,
            'quality_decision':plan['quality_decision'], 'promotion_allowed':False}


def fail_output(output: Path, error: BaseException, command: str, started: float) -> None:
    report_path = output/'report.json'
    original_report = None
    if report_path.is_file() and not report_path.is_symlink():
        original_report = output/'report-before-failure.json'
        require(not original_report.exists(), 'prior failure report must never be overwritten')
        report_path.rename(original_report)
    manifest_path = output/'artifact-manifest.json'
    if manifest_path.is_file() and not manifest_path.is_symlink():
        preserved = output/'artifact-manifest-before-failure.json'
        require(not preserved.exists(), 'prior failure manifest must never be overwritten')
        manifest_path.rename(preserved)
    if original_report is not None:
        try:
            report = load_json(original_report)
        except (ValueError, UnicodeError):
            report = {}
        report['status'] = 'FAIL_MEASUREMENT_INTEGRITY'
        report['failure'] = type(error).__name__ + ': ' + str(error)
        report['original_report_sha256'] = source.file_hash(original_report)
        write_json(output/'failed-report.json', report)
    record = {'schema_version':1, 'study_id':STUDY, 'status':'FAIL_METHOD_OR_EXECUTION', 'command':command,
              'error':type(error).__name__ + ': ' + str(error), 'elapsed_seconds':time.monotonic()-started,
              'automatic_retries':0, 'promotion_allowed':False}
    if isinstance(error, (subprocess.CalledProcessError,subprocess.TimeoutExpired)):
        record['child_command'] = error.cmd
        record['child_returncode'] = getattr(error,'returncode',None)
        stderr = error.stderr or b''
        record['child_stderr_tail'] = stderr[-65536:].decode('utf-8',errors='replace') if isinstance(stderr,bytes) else stderr[-65536:]
    write_json(output/'failure.json', record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build','run','verify'))
    parser.add_argument('--source-archive', required=True, type=Path)
    parser.add_argument('--source', type=Path, help='Prepared original source for build')
    parser.add_argument('--corpus', type=Path, help='Frozen generated corpus.json for run')
    parser.add_argument('--bundle', type=Path, help='Verified real AP portable bundle for run')
    parser.add_argument('--engineering-receipt', type=Path, help='Already executed engineering receipt on this host')
    parser.add_argument('--output', required=True, type=Path, help='Fresh stage output, or existing result for verify')
    parser.add_argument('--harness-revision', required=True)
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    owned, started, output = False, time.monotonic(), args.output
    try:
        plan = read_plan(args.plan_sha256)
        archive, output = source.safe_local(args.source_archive), source.safe_local(args.output)
        if args.command == 'verify':
            with source.wall_limit(600, 'F05 independent readback'):
                result = verify_measurement(archive, output, plan, args.harness_revision)
        else:
            require(not output.exists() and ROOT not in output.parents, 'new stage output must be fresh and outside checkout')
            require(output != archive and output not in archive.parents, 'source archive/output overlap')
            if args.command == 'build':
                require(args.source is not None, '--source required')
                disjoint_output(output, [source.safe_local(args.source)])
            else:
                require(args.corpus is not None and args.bundle is not None, '--corpus and --bundle required')
                inputs = [source.safe_local(args.corpus).parent, source.safe_local(args.bundle)]
                if args.engineering_receipt is not None:
                    inputs.append(source.safe_local(args.engineering_receipt).parent)
                disjoint_output(output, inputs)
            # Controls are checked before data effects; all heavy preparation and
            # final evidence work share one frozen stage timer.
            controls = code_identity(args.harness_revision)
            output.mkdir(parents=True); owned = True; started = time.monotonic()
            budget = 120 if args.command == 'build' else 600
            with source.wall_limit(budget, 'F05 ' + args.command):
                if args.command == 'build':
                    corpus = build_corpus(archive, source.safe_local(args.source), output, plan, controls)
                    require(code_identity(args.harness_revision) == controls, 'generator controls changed')
                    require(time.monotonic()-started <= 120, 'generation wall budget exceeded')
                    result = {'status':'HASH_FROZEN_RESERVED_CORPUS_PREPARED_NOT_BLIND','study_id':STUDY,
                              'corpus_sha256':source.file_hash(output/'corpus.json'),'cases':len(corpus['cases']),
                              'elapsed_seconds':time.monotonic()-started,'processor_calls':0,'decoder_calls':0}
                else:
                    report = run_matrix(archive, source.safe_local(args.corpus), source.safe_local(args.bundle),
                                        args.engineering_receipt, output, plan, controls, started)
                    seal_measurement(output, report, plan, started)
                    result = {'status':report['status'],'study_id':STUDY,'processor_calls':128,
                              'matrix_wall_seconds':report['matrix_wall_seconds'],'promotion_allowed':False}
        print(json.dumps(result,sort_keys=True,allow_nan=False))
        return 0
    except (Exception,KeyboardInterrupt) as error:
        if owned:
            fail_output(output,error,args.command,started)
        print(json.dumps({'status':'FAIL_METHOD_OR_EXECUTION','error':type(error).__name__+': '+str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
