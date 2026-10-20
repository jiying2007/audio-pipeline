#!/usr/bin/env python3
"""Independent upstream FIR kernel + fixed coefficients, disclosed six-case BF."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

import numpy as np
from contracts import ROOT, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal
import external_source
import speech_spatial as speech
import speech_spatial_weights as spatial_speech
from array_qualification import FLAGS

HERE = Path(__file__).resolve().parent
PLAN = ROOT / '.github/research/frontend-evolution-v1/sof-fir-reference-v1.json'
SOURCE_NAMES = ('sof_fir_reference.py', 'sof_fir_runner.c', 'external_source.py',
                'array_native.c', 'array_native.h', 'array_runner.c', 'speech_render.c',
                'speech_spatial.py', 'speech_spatial_weights.py', 'spatial_weights.py',
                'array_qualification.py', 'array_fir_checks.py', 'contracts.py',
                'speech_source.py', 'speech_fir.py', 'libfvad_reference.py')
SHIMS = {
    'sof/common.h': '#ifndef FE_SOF_COMMON\n#define FE_SOF_COMMON\n#include <stdint.h>\n#include <limits.h>\n'
        '#define SOF_USE_HIFI(a,b) 1\n#define SOF_USE_ARM_SIMD(a) 0\n#define SOF_USE_RISCV_SIMD(a) 0\n'
        '#define MIN(a,b) ((a)<(b)?(a):(b))\n#define ASSUME_ALIGNED(p,a) __builtin_assume_aligned((p),(a))\n'
        'static inline int32_t sat_int32(int64_t x) { return x>INT32_MAX?INT32_MAX:x<INT32_MIN?INT32_MIN:(int32_t)x; }\n#endif\n',
    'sof/audio/buffer.h': '/* Host FIR kernel does not use SOF buffers. */\n',
    'sof/audio/audio_stream.h': '/* Host FIR kernel does not use SOF audio streams. */\n',
    'sof/audio/format.h': '#include <sof/common.h>\n',
    'rtos/symbol.h': '#define EXPORT_SYMBOL(x)\n',
}


def code_hashes():
    return {**{name: sha256((HERE / name).read_bytes()) for name in SOURCE_NAMES},
            'run_validation_engine.py': sha256((ROOT / 'validation/tools/run_validation_engine.py').read_bytes())}


def coefficient_bank(source, plan):
    receipt = external_source.admitted(source, 'sof')
    path = source / 'sof' / plan['coefficients']['upstream_blob_path']
    return decode_coefficients(path.read_bytes(), receipt, plan)


def decode_coefficients(content, receipt, plan):
    require(sha256(content) == plan['coefficients']['upstream_file_sha256'], 'wrong SOF coefficient source')
    blob = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]{2})', content.decode()))
    require(len(blob) == 1332 and blob[:4] == b'SOF\0', 'SOF coefficient ABI header')
    require(struct.unpack_from('<I6H', blob, 32) == (1300, 8, 2, 1, 4, 1, 0), 'SOF coefficient configuration')
    filters, encoded = [], bytearray()
    for index in plan['coefficients']['selected_filter_indices']:
        at = 60 + index * 148
        count, shift = struct.unpack_from('<hh', blob, at)
        require(count == 64 and shift == plan['coefficients']['out_shifts'][index], 'SOF taps/scaling drift')
        coefficients = list(struct.unpack_from('<64h', blob, at + 20))
        encoded.extend(blob[at:at + 4] + blob[at + 20:at + 148])
        filters.append({'out_shift': shift, 'coefficients_q15': coefficients})
    require(sha256(bytes(encoded)) == plan['coefficients']['coefficients_binary_sha256'], 'selected coefficient identity')
    metadata = {'filters': filters, 'selected_output': 0, 'nominal_positions_m': plan['geometry']['positions_m'],
                'upstream_location_q4_12': [list(struct.unpack_from('<hhhh', blob, 1300 + 8*i)) for i in range(4)],
                'source_materialized_sha256': receipt['materialized_source_sha256']}
    return bytes(encoded), metadata


def geometry(angle, plan):
    return {'positions_m': plan['geometry']['positions_m'], 'direction': [math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0.0],
            'sample_rate_hz': 16000, 'active_mask': 15, 'reference_mic': 0,
            'gains': [1] * 4, 'latency_samples': [0] * 4, 'channel_map': [0, 1, 2, 3]}


def reconstruct_inputs(data, source, spec, plan):
    """Full independent Python rendering of the fixed C stimulus recipe."""
    originals = [source['speaker_selection'][2*spec['pair']+i]['window_file'] for i in (0, 1)]
    pcm = [np.frombuffer((data / name).read_bytes(), dtype='<i2').astype(np.float64)/32768 for name in originals]
    gains = speech.gains(*[list(value) for value in pcm])
    raw, configurations = {}, {}
    for i, tag, angle in [(0, 'target', spec['target_degrees']), (1, 'interferer', spec['interferer_degrees'])]:
        configurations[tag] = speech.render_config(geometry(angle, plan), gains[i])
        advances = list(map(float, configurations[tag].decode().split()[2:]))
        scaled = pcm[i] * gains[i]
        rendered = np.zeros((64000, 4), np.float64)
        for mic, advance in enumerate(advances):
            for offset, weight in speech.sinc_taps(advance):
                begin, end = max(0, -offset), min(64000, 64000-offset)
                rendered[begin:end, mic] += weight * scaled[begin+offset:end+offset]
        raw[tag] = np.rint(rendered * 32768).astype(np.int64)
    raw['mixture'] = raw['target'] + raw['interferer']
    require(all(np.max(np.abs(value)) < 32760 for value in raw.values()), 'fixed renderer clips')
    return raw, configurations, gains


def build(root, source):
    shim = root / 'host-shims'
    for name, content in SHIMS.items():
        path = shim / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    upstream = source / 'sof'
    binaries = {}
    for label, flags in [('native', ['-O2']), ('sanitized', ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer'])]:
        binary = root / ('sof-' + label)
        command = ['cc', '-std=c11', *flags, '-Wall', '-Wextra', '-Werror', '-ffp-contract=off',
                   '-I' + str(shim), '-I' + str(upstream / 'src/include'),
                   HERE / 'sof_fir_runner.c', upstream / 'src/math/fir_generic.c', '-lm', '-o', binary]
        run_logged(command, root / (label + '-build.log'))
        binaries[label] = sha256(binary.read_bytes())
    for name, files in [('array', ['array_native.c', 'array_runner.c']), ('renderer', ['speech_render.c'])]:
        command = ['cc', *FLAGS, *(HERE / name for name in files), '-lm', '-o', root / name]
        run_logged(command, root / (name + '-build.log'))
        binaries[name] = sha256((root / name).read_bytes())
    run_logged(['cc', '--version'], root / 'compiler.txt')
    return binaries


def execute(root, label, inp, dest, chunk=160):
    run_logged([root / ('sof-' + label), root / 'coefficients.bin', inp,
                dest.with_suffix('.s32'), dest.with_suffix('.json'), str(chunk)], dest.with_suffix('.log'))
    return np.frombuffer(dest.with_suffix('.s32').read_bytes(), dtype='<i4')


def integer_oracle(raw, filters):
    # Independent direct integer convolution, no ported SOF loop/state.
    output = np.zeros(raw.shape[0], dtype=np.int64)
    for channel, entry in enumerate(filters):
        x = raw[:, channel].astype(np.int64) * 65536
        accumulator = np.convolve(x, np.asarray(entry['coefficients_q15'], np.int64))[:len(x)]
        y = np.clip(accumulator >> (15 + entry['out_shift']), -(2**31), 2**31 - 1)
        output += y >> 4
    return np.clip(output * 16, -(2**31), 2**31 - 1).astype('<i4')


def engineering(root, bank):
    directory = root / 'engineering'
    directory.mkdir()
    raw = np.random.default_rng(1709).integers(-4000, 4001, size=(3200, 4), dtype=np.int16)
    inp = directory / 'input.s16'
    inp.write_bytes(raw.astype('<i2').tobytes())
    expected = integer_oracle(raw, bank['filters'])
    results = {}
    for label in ('native', 'sanitized'):
        actual = execute(root, label, inp, directory / label)
        repeated = execute(root, label, inp, directory / (label + '-chunk2'), chunk=2)
        require(actual.tobytes() == expected.tobytes() == repeated.tobytes(), 'SOF integer oracle/chunk mismatch')
        results[label] = {'integer_oracle_q31_exact': True, 'chunk_2_vs_160_exact': True,
                          'output_sha256': sha256(actual.tobytes())}
    bad = directory / 'odd.s16'
    bad.write_bytes(raw[:1].astype('<i2').tobytes())
    failures = {}
    commands = {
        'odd-frames': [root / 'sof-native', root / 'coefficients.bin', bad, directory / 'bad.s32', directory / 'bad.json', '160'],
        'odd-chunk': [root / 'sof-native', root / 'coefficients.bin', inp, directory / 'badchunk.s32', directory / 'badchunk.json', '3'],
        'no-clobber': [root / 'sof-native', root / 'coefficients.bin', inp, directory / 'native.s32', directory / 'overwrite.json', '160'],
    }
    truncated = directory / 'partial-coefficients.bin'
    truncated.write_bytes((root / 'coefficients.bin').read_bytes()[:-1])
    commands['partial-coefficients'] = [root / 'sof-native', truncated, inp, directory / 'badcoeff.s32', directory / 'badcoeff.json', '160']
    for name, command in commands.items():
        p = subprocess.run(list(map(str, command)), capture_output=True, check=False)
        require(p.returncode != 0, 'invalid SOF input accepted: ' + name)
        failures[name] = p.returncode
    require((directory / 'native.s32').read_bytes() == expected.tobytes(), 'no-clobber altered audio')
    return {'status': 'PASS', 'modes': results, 'negative_return_codes': failures}


def verify_engineering(root, bank, report):
    directory = root / 'engineering'
    raw = np.random.default_rng(1709).integers(-4000, 4001, size=(3200, 4), dtype=np.int16)
    require((directory / 'input.s16').read_bytes() == raw.astype('<i2').tobytes(), 'SOF engineering input drift')
    expected = integer_oracle(raw, bank['filters']).tobytes()
    require(report['status'] == 'PASS' and set(report['modes']) == {'native', 'sanitized'}, 'SOF missing sanitizer evidence')
    for label in ('native', 'sanitized'):
        require(report['modes'][label] == {'integer_oracle_q31_exact': True, 'chunk_2_vs_160_exact': True,
                                         'output_sha256': sha256(expected)}, 'SOF engineering claim drift')
        for suffix in ('', '-chunk2'):
            prefix = directory / (label + suffix)
            require(prefix.with_suffix('.s32').read_bytes() == expected, 'SOF engineering oracle bytes')
            require(prefix.with_suffix('.log').read_bytes() == b'', 'SOF engineering diagnostic output')
            meta = load_json(prefix.with_suffix('.json'))
            require(meta['status'] == 'SUCCESS' and meta['samples'] == 3200 and meta['shipping_authority'] is False,
                    'SOF engineering execution contract')
    require(set(report['negative_return_codes']) == {'odd-frames', 'odd-chunk', 'no-clobber', 'partial-coefficients'}
            and all(value != 0 for value in report['negative_return_codes'].values()), 'SOF missing negative execution')


def response(kernels, g, plan):
    positions = np.asarray(g['positions_m'])
    tau = (positions - positions[0]) @ np.asarray(g['direction']) * 16000 / 343
    distances = np.linalg.norm(positions[:, None, :] - positions[None, :, :], axis=2)
    rows = []
    for frequency in plan['metrics']['frequency_grid_hz']:
        omega = 2 * np.pi * frequency / 16000
        h = np.asarray([sum(v * np.exp(-1j * omega * k) for k, v in row) for row in kernels])
        look = abs(sum(h * np.exp(1j * omega * tau)))**2
        white = float(sum(abs(h)**2))
        covariance = np.sinc(2 * frequency * distances / 343)
        diffuse = float((h @ covariance @ h.conj()).real)
        sectors = []
        for angle in range(-180, 181, 15):
            direction = np.array([math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0])
            advance = (positions - positions[0]) @ direction * 16000 / 343
            power = abs(sum(h * np.exp(1j * omega * advance)))**2
            sectors.append({'degrees': angle, 'gain_db': float(10*np.log10(max(power, 1e-30)))})
        rows.append({'frequency_hz': frequency, 'look_gain_db': float(10*np.log10(max(look, 1e-30))),
                     'wng_db': float(10*np.log10(max(look, 1e-30)/max(white, 1e-30))),
                     'diffuse_di_db': float(10*np.log10(max(look, 1e-30)/max(diffuse, 1e-30))),
                     'sectors': sectors})
    return rows


def summaries(rows):
    result = {}
    for arm in ('fir33', 'diffuse-0.1', 'diffuse-1.0', 'sof64'):
        result[arm] = {}
        for scene, angle, interferer in [('separated', 90, -90), ('co-located', 90, 90), ('look-mismatch', 60, -90)]:
            selected = [r['arms'][arm] for r in rows if r['target_degrees'] == angle and r['interferer_degrees'] == interferer]
            require(len(selected) == 2, 'partial SOF subgroup')
            result[arm][scene] = {key: sum(r[key] for r in selected)/2 for key in
                                  ('component_sir_gain_db', 'target_gain_db', 'canonical_si_sdr_db', 'target_relative_error_energy')}
    return result


def run(source, data, root):
    require(not root.exists(), 'fresh SOF evidence output required')
    plan = load_json(PLAN)
    speech_source = spatial_speech.source_check(data)
    require(speech_source['speaker_selection'][:4] == plan['speaker_selection'], 'fixed SOF speaker selection drift')
    encoded, bank = coefficient_bank(source, plan)
    root.mkdir(parents=True)
    shutil.copytree(data, root / 'data')
    shutil.copytree(source / 'sof', root / 'upstream')
    shutil.copyfile(source / 'source-receipt.json', root / 'source-receipt.json')
    shutil.copyfile(external_source.ADMISSION, root / 'admission.json')
    shutil.copyfile(PLAN, root / 'experiment.json')
    (root / 'coefficients.bin').write_bytes(encoded)
    write_json(root / 'coefficient-bank.json', bank)
    (root / 'source').mkdir()
    for name in SOURCE_NAMES:
        shutil.copyfile(HERE / name, root / 'source' / name)
    shutil.copyfile(ROOT / 'validation/tools/run_validation_engine.py', root / 'source/run_validation_engine.py')
    binaries = build(root, source)
    engineering_result = engineering(root, bank)
    g = geometry(plan['geometry']['look_degrees'], plan)
    configurations, responses = {}, {}
    for arm in plan['arms']:
        if arm == 'sof64':
            kernels = [[(k, v / 2**(15 + entry['out_shift'])) for k, v in enumerate(entry['coefficients_q15'])]
                       for entry in bank['filters']]
        else:
            cfg, coefficients, kernels = spatial_speech.filters(g, arm)
            configurations[arm] = cfg
            (root / (arm + '-geometry.txt')).write_bytes(cfg)
            if coefficients is not None:
                write_json(root / (arm + '-bank.json'), coefficients)
        responses[arm] = response(kernels, g, plan)
    write_json(root / 'frequency-responses.json', responses)
    rows = []
    for spec in plan['cases']:
        directory = root / 'cases' / spec['case_id']
        directory.mkdir(parents=True)
        original = [speech_source['speaker_selection'][2*spec['pair']+i]['window_file'] for i in (0, 1)]
        source_pcm = [np.frombuffer((data / name).read_bytes(), dtype='<i2').astype(np.float64)/32768 for name in original]
        gains = speech.gains(*[list(v) for v in source_pcm])
        raw = {}
        for i, tag, angle in [(0, 'target', spec['target_degrees']), (1, 'interferer', spec['interferer_degrees'])]:
            cfg = directory / (tag + '-render.txt')
            cfg.write_bytes(speech.render_config(geometry(angle, plan), gains[i]))
            rendered = directory / (tag + '.f64')
            run_logged([root / 'renderer', cfg, data / original[i], rendered], directory / (tag + '-render.log'))
            floating = np.frombuffer(rendered.read_bytes(), dtype='<f8')
            raw[tag] = np.rint(floating * 32768).astype(np.int64).reshape(-1, 4)
        raw['mixture'] = raw['target'] + raw['interferer']
        require(all(np.max(np.abs(value)) < 32760 for value in raw.values()), 'renderer clips; no rescale')
        for tag, values in raw.items():
            (directory / (tag + '.s16')).write_bytes(values.astype('<i2').tobytes())
        row = {**spec, 'gains': list(gains), 'inputs_sha256': {}, 'arms': {}}
        row['inputs_sha256'] = {tag: sha256((directory / (tag + '.s16')).read_bytes()) for tag in raw}
        target, interferer = [(raw[tag][:, 0]/32768).tolist() for tag in ('target', 'interferer')]
        for arm in plan['arms']:
            destination = directory / arm
            destination.mkdir()
            actual = {}
            for tag in ('target', 'interferer', 'mixture'):
                if arm == 'sof64':
                    q31 = execute(root, 'native', directory / (tag + '.s16'), destination / tag)
                    values = (q31.astype(np.float64)/2147483648).astype('<f4')
                    (destination / (tag + '.f32')).write_bytes(values.tobytes())
                else:
                    run_logged([root / 'array', root / (arm + '-geometry.txt'), directory / (tag + '.s16'),
                                destination / (tag + '.f32'), destination / (tag + '.json')], destination / (tag + '.log'))
                    values = np.frombuffer((destination / (tag + '.f32')).read_bytes(), dtype='<f4')
                actual[tag] = values.tolist()
            delay = 34 if arm == 'sof64' else 21
            row['arms'][arm] = {'fixed_delay_samples': delay,
                                **speech.metrics(target, interferer, actual['target'], actual['interferer'], actual['mixture'], delay)}
        # Stream partition and future causality are checked on the real mixture.
        repeated = execute(root, 'native', directory / 'mixture.s16', directory / 'sof-repeat', chunk=2)
        require(repeated.tobytes() == (directory / 'sof64/mixture.s32').read_bytes(), 'SOF speech repeat/chunk mismatch')
        changed = raw['mixture'].copy()
        changed[32000:] *= -1
        (directory / 'future.s16').write_bytes(changed.astype('<i2').tobytes())
        future = execute(root, 'native', directory / 'future.s16', directory / 'sof-future')
        require(future[:32000].tobytes() == repeated[:32000].tobytes()
                and future[32000:].tobytes() != repeated[32000:].tobytes(), 'SOF future causality')
        rows.append(row)
        print('completed ' + spec['case_id'], flush=True)
    report = {'schema_version': 1, 'experiment_id': plan['experiment_id'], 'decision': plan['decision'],
              'base_revision': plan['base_revision'], 'shipping_authority': False, 'data_role': plan['data_role'],
              'source_admission_sha256': plan['source_admission_sha256'], 'code_sha256': code_hashes(),
              'coefficients_sha256': sha256(encoded), 'binaries': binaries, 'engineering': engineering_result,
              'cases': rows, 'summary': summaries(rows), 'host_only': True, 'full_SOF_firmware': False}
    write_json(root / 'result.json', report)
    seal_output(root, report)
    return verify(root)


def verify(root):
    verify_seal(root)
    plan, report = load_json(PLAN), load_json(root / 'result.json')
    require(load_json(root / 'experiment.json') == plan and report['experiment_id'] == plan['experiment_id']
            and report['base_revision'] == plan['base_revision']
            and report['decision'] == plan['decision'] and report['shipping_authority'] is False
            and report['data_role'] == plan['data_role'] and report['host_only'] is True
            and report['full_SOF_firmware'] is False, 'SOF authority drift')
    source = spatial_speech.source_check(root / 'data')
    require(source['speaker_selection'][:4] == plan['speaker_selection'], 'SOF speaker role drift')
    require(sha256(spatial_speech.ADMISSION.read_bytes()) == report['source_admission_sha256'] == plan['source_admission_sha256'],
            'SOF speech admission drift')
    require(report['code_sha256'] == code_hashes(), 'SOF source/evaluator changed')
    for name, digest in report['code_sha256'].items():
        require(sha256((root / 'source' / name).read_bytes()) == digest, 'source snapshot drift')
    require(report['coefficients_sha256'] == sha256((root / 'coefficients.bin').read_bytes())
            == plan['coefficients']['coefficients_binary_sha256'], 'SOF coefficient drift')
    complete_receipt = load_json(root / 'source-receipt.json')
    admission = load_json(external_source.ADMISSION)
    require(load_json(root / 'admission.json') == admission
            and complete_receipt['sources'] == admission['sources']
            and complete_receipt['source_lock_sha256'] == sha256(external_source.LOCK.read_bytes())
            and complete_receipt['status'] == 'SOURCE_BYTES_VERIFIED_NOT_EXECUTED'
            and complete_receipt['shipping_authority'] is False, 'SOF code admission drift')
    receipt = complete_receipt['sources']['sof']
    for name, digest in receipt['files_sha256'].items():
        require(sha256((root / 'upstream' / name).read_bytes()) == digest, 'upstream source drift')
    encoded, bank = decode_coefficients((root / 'upstream' / plan['coefficients']['upstream_blob_path']).read_bytes(), receipt, plan)
    require(encoded == (root / 'coefficients.bin').read_bytes()
            and bank == load_json(root / 'coefficient-bank.json'), 'SOF parsed coefficient drift')
    verify_engineering(root, bank, report['engineering'])
    for name, content in SHIMS.items():
        require((root / 'host-shims' / name).read_text() == content, 'host shim drift')
    for name, digest in report['binaries'].items():
        path = root / (('sof-' + name) if name in ('native', 'sanitized') else name)
        require(sha256(path.read_bytes()) == digest and path.read_bytes()[:4] == b'\x7fELF', 'SOF processor identity drift')
    require(set(report['binaries']) == {'native', 'sanitized', 'array', 'renderer'}, 'SOF missing binary')
    g, responses = geometry(plan['geometry']['look_degrees'], plan), {}
    for arm in plan['arms']:
        if arm == 'sof64':
            kernels = [[(k, v / 2**(15 + entry['out_shift'])) for k, v in enumerate(entry['coefficients_q15'])]
                       for entry in bank['filters']]
        else:
            configuration, coefficients, kernels = spatial_speech.filters(g, arm)
            require((root / (arm + '-geometry.txt')).read_bytes() == configuration, 'first-party configuration drift')
            if coefficients is not None:
                require(load_json(root / (arm + '-bank.json')) == coefficients, 'first-party coefficient drift')
        responses[arm] = response(kernels, g, plan)
    require(load_json(root / 'frequency-responses.json') == responses, 'actual FIR frequency response drift')
    rows = {row['case_id']: row for row in report['cases']}
    require(len(rows) == len(report['cases']) == len(plan['cases']) == 6, 'SOF partial/duplicate cases')
    for spec in plan['cases']:
        row, directory = rows[spec['case_id']], root / 'cases' / spec['case_id']
        require(all(row[k] == v for k, v in spec.items()), 'SOF case selection drift')
        expected_raw, configurations, gains = reconstruct_inputs(root / 'data', source, spec, plan)
        require(row['gains'] == list(gains), 'SOF source gain drift')
        for tag, content in configurations.items():
            require((directory / (tag + '-render.txt')).read_bytes() == content, 'SOF scene geometry drift')
        raw = {}
        for tag in ('target', 'interferer', 'mixture'):
            content = (directory / (tag + '.s16')).read_bytes()
            require(len(content) == 64000*4*2 and sha256(content) == row['inputs_sha256'][tag], 'SOF input count/digest')
            require(content == expected_raw[tag].astype('<i2').tobytes(), 'SOF full recorded-source rendering mismatch')
            raw[tag] = np.frombuffer(content, dtype='<i2').reshape(-1, 4).astype(np.int64)
        require(np.array_equal(raw['mixture'], raw['target'] + raw['interferer']), 'SOF mixture composition')
        target, interferer = [(raw[tag][:, 0]/32768).tolist() for tag in ('target', 'interferer')]
        require(set(row['arms']) == set(plan['arms']), 'SOF missing/extra arm')
        for arm in plan['arms']:
            actual = {tag: speech.values((directory / arm / (tag + '.f32')).read_bytes(), 'f', 64000)
                      for tag in ('target', 'interferer', 'mixture')}
            delay = 34 if arm == 'sof64' else 21
            require(row['arms'][arm] == {'fixed_delay_samples': delay,
                                         **speech.metrics(target, interferer, actual['target'], actual['interferer'], actual['mixture'], delay)},
                    'SOF metric/fixed delay drift')
            for tag in actual:
                meta = load_json(directory / arm / (tag + '.json'))
                if arm == 'sof64':
                    require(meta['status'] == 'SUCCESS' and meta['shipping_authority'] is False and meta['samples'] == 64000
                            and meta['sample_rate_hz'] == 16000 and meta['fir_state_coefficient_delay_bytes'] <= 16384, 'SOF output contract')
                    q31 = np.frombuffer((directory / arm / (tag + '.s32')).read_bytes(), dtype='<i4')
                    require((q31.astype(np.float64)/2147483648).astype('<f4').tobytes()
                            == (directory / arm / (tag + '.f32')).read_bytes(), 'SOF output scale drift')
                    require(q31.tobytes() == integer_oracle(raw[tag], bank['filters']).tobytes(), 'SOF full integer convolution mismatch')
                else:
                    require(meta['status'] == 'PASS' and meta['interpolation'] == (3 if arm == 'fir33' else 4)
                            and meta['samples_processed'] == 64000 and meta['mic_count'] == 4 and meta['active_mask'] == 15
                            and meta['common_delay_samples'] == 21 and meta['sample_rate_hz'] == 16000
                            and meta['output_encoding'] == 'f32le-unclipped' and meta['direction'] == g['direction']
                            and meta['shipping_authority'] is False and meta['steering_accepted'] == 0,
                            'first-party native metadata identity')
        require((directory / 'sof-repeat.s32').read_bytes() == (directory / 'sof64/mixture.s32').read_bytes(), 'SOF repeat changed')
        future = (directory / 'sof-future.s32').read_bytes()
        original = (directory / 'sof64/mixture.s32').read_bytes()
        require(future[:32000*4] == original[:32000*4] and future[32000*4:] != original[32000*4:], 'SOF causal evidence changed')
    require(report['summary'] == summaries(report['cases']), 'SOF summary drift')
    return {'status': 'VERIFIED_LOCAL_DIAGNOSTIC', 'cases': 6, 'mixed_arms': 24,
            'decision': plan['decision'], 'summary': report['summary']}


def negative(root):
    original = load_json(root / 'result.json')
    changes = {'missing-case': lambda r: r['cases'].pop(), 'promotion': lambda r: r.update(shipping_authority=True),
               'wrong-base': lambda r: r.update(base_revision='0'*40),
               'holdout': lambda r: r.update(data_role='INDEPENDENT_HOLDOUT'),
               'full-firmware-claim': lambda r: r.update(full_SOF_firmware=True),
               'wrong-score': lambda r: r['cases'][0]['arms']['sof64'].update(canonical_si_sdr_db=999),
               'wrong-coefficients': lambda r: r.update(coefficients_sha256='0'*64),
               'missing-sanitizer': lambda r: r['engineering']['modes'].pop('sanitized')}
    rejected = []
    with tempfile.TemporaryDirectory(prefix='fe-sof-negative-') as temporary:
        scratch = Path(temporary) / 'evidence'
        shutil.copytree(root, scratch)
        for name, change in changes.items():
            report = copy.deepcopy(original)
            change(report)
            write_json(scratch / 'result.json', report)
            seal_output(scratch, report)
            try:
                verify(scratch)
            except (ValueError, KeyError, AssertionError):
                rejected.append(name)
            else:
                raise ValueError('SOF semantic negative accepted: ' + name)
        write_json(scratch / 'result.json', original)
        case = original['cases'][0]
        input_path = scratch / 'cases' / case['case_id'] / 'target.s16'
        altered = bytearray(input_path.read_bytes())
        altered[100] ^= 1
        input_path.write_bytes(altered)
        report = copy.deepcopy(original)
        report['cases'][0]['inputs_sha256']['target'] = sha256(bytes(altered))
        write_json(scratch / 'result.json', report)
        seal_output(scratch, report)
        try:
            verify(scratch)
        except (ValueError, KeyError, AssertionError):
            rejected.append('resealed-changed-source-pcm')
        else:
            raise ValueError('SOF source rendering negative accepted')
        input_path.write_bytes((root / 'cases' / case['case_id'] / 'target.s16').read_bytes())
        write_json(scratch / 'result.json', original)
        native_meta = scratch / 'cases' / case['case_id'] / 'fir33/mixture.json'
        meta = load_json(native_meta)
        write_json(native_meta, {**meta, 'status': 'FAIL'})
        seal_output(scratch, original)
        try:
            verify(scratch)
        except (ValueError, KeyError, AssertionError):
            rejected.append('failed-first-party-receipt')
        else:
            raise ValueError('SOF failed first-party metadata accepted')
        write_json(native_meta, meta)
        tail_path = scratch / 'cases' / case['case_id'] / 'fir33/mixture.f32'
        tail_path.write_bytes(tail_path.read_bytes()[:-4] + struct.pack('<f', float('nan')))
        seal_output(scratch, original)
        try:
            verify(scratch)
        except (ValueError, KeyError, AssertionError):
            rejected.append('nonfinite-unscored-tail')
        else:
            raise ValueError('SOF nonfinite unscored output accepted')
    return {'status': 'PASS', 'rejected': rejected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--data', type=Path)
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
            require(args.source is not None and args.data is not None, 'admitted code and speech source required')
            result = run(args.source, args.data, args.output)
    except Exception as error:
        if not existed and args.output.exists():
            write_json(args.output / 'failure.json', {'error': str(error), 'shipping_authority': False})
        raise
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
