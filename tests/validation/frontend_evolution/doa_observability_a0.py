#!/usr/bin/env python3
"""FE03 A0: fixed ideal geometry observability, NOT a DOA/audio evaluator.

Preregistered: https://github.com/jiying2007/audio-pipeline/issues/657#issuecomment-6077581740
No source downloads, audio processing, shipping API, learned models or site effects.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / '.github/research/frontend-evolution-v1/doa-observability-a0.json'
FE02 = ROOT / '.github/research/frontend-evolution-v1/array-native-v1.json'
DECISION = 'FE03_DOA_GEOMETRY_OBSERVABILITY_A0_NO_PROMOTION'
EXPERIMENT = 'FE03-DOA-GEOMETRY-OBSERVABILITY-A0'
# Exact frozen research contract digest. Deliberate amendments need review and
# a new pre-registration; an arbitrary edited JSON cannot silently self-admit.
EXPECTED_PLAN_SHA256 = 'ee99a791f368eecb44a1754a405cb1c9c14a4eab1676313a4d0ba38014b50f1c'
EXPECTED_GEOMETRIES = {
    'ULA4': ((0., 0., 0.), (.035, 0., 0.), (.070, 0., 0.), (.105, 0., 0.)),
    'UCA4': ((.035, 0., 0.), (0., .035, 0.), (-.035, 0., 0.), (0., -.035, 0.)),
}
EXPECTED_GEOMETRY_IDS = {'ULA4': 'ula4-broadside', 'UCA4': 'uca4-offaxis'}
EXPECTED_RANKS = (
    ('ula4-all', 'ULA4', 15, 1), ('uca4-all', 'UCA4', 15, 2),
    ('uca4-three', 'UCA4', 14, 2), ('uca4-opposite-pair', 'UCA4', 5, 1),
    ('uca4-single', 'UCA4', 1, 0), ('ula4-three', 'ULA4', 7, 1),
)
EXPECTED_CONTRASTS = (
    ('ula4-azimuth-mirror', 'ULA4', 15, (30., 0.), (-30., 0.), 'same', 1e-12),
    ('uca4-azimuth-mirror', 'UCA4', 15, (30., 0.), (-30., 0.), 'distinct', .25),
    ('uca4-elevation-mirror', 'UCA4', 15, (30., 20.), (30., -20.), 'same', 1e-12),
)


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError('FE03 A0: ' + message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_object(path: Path) -> dict:
    def pairs(items: list) -> dict:
        obj: dict = {}
        for k, v in items:
            require(k not in obj, 'duplicate JSON key ' + str(k))
            obj[k] = v
        return obj

    def reject_nonfinite(token: str) -> None:
        raise ValueError('FE03 A0: nonfinite JSON token ' + token)

    value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                       parse_constant=reject_nonfinite)
    require(isinstance(value, dict), 'expected JSON object')
    return value


def check_angle(angle: list) -> tuple[float, float]:
    require(isinstance(angle, list) and len(angle) == 2, 'angle must be [azimuth, elevation]')
    azimuth, elevation = angle
    for v in (azimuth, elevation):
        require(type(v) in (int, float) and math.isfinite(v), 'nonfinite/non-numeric angle')
    require(-180. <= azimuth <= 180. and -90. <= elevation <= 90., 'out-of-range angle')
    return float(azimuth), float(elevation)


def validate_plan(p: dict) -> dict:
    required = {'schema_version', 'experiment_id', 'stage', 'status', 'preregistration',
                'decision', 'source_role', 'data_role', 'shipping_authority',
                'product_qualification', 'sample_rate_hz', 'speed_of_sound_m_per_s',
                'source_direction', 'reference_rule', 'rank_space', 'geometries',
                'rank_cases', 'contrast_cases', 'no_doa_estimator',
                'no_acoustic_score', 'no_new_sdk_api'}
    require(set(p) == required, 'contract field set changed')
    require(p['schema_version'] == 1 and type(p['schema_version']) is int and
            p['experiment_id'] == EXPERIMENT and p['stage'] == 'frontend-evolution-v1' and
            p['status'] == 'PREREGISTERED_ANALYTIC_ENGINEERING' and
            p['preregistration'] ==
            'https://github.com/jiying2007/audio-pipeline/issues/657#issuecomment-6077581740' and
            p['decision'] == DECISION and
            p['source_role'] == 'first-party-analytic' and
            p['data_role'] == 'ideal-plane-wave-geometry-only' and
            p['shipping_authority'] is False and p['product_qualification'] is False and
            type(p['sample_rate_hz']) is int and p['sample_rate_hz'] == 16000 and
            type(p['speed_of_sound_m_per_s']) in (int, float) and
            p['speed_of_sound_m_per_s'] == 343. and
            p['source_direction'] == 'array-to-source' and
            p['reference_rule'] == 'first-active-physical-microphone' and
            p['rank_space'] == 'xy-baseline' and
            p['no_doa_estimator'] is True and p['no_acoustic_score'] is True and
            p['no_new_sdk_api'] is True, 'authority or physical model changed')
    geometries = p['geometries']
    require(isinstance(geometries, list) and len(geometries) == 2, 'geometry coverage changed')
    seen = set()
    for g in geometries:
        require(isinstance(g, dict) and set(g) == {'id', 'fe02_geometry_id', 'positions_m'},
                'geometry schema changed')
        name = g['id']
        require(name in EXPECTED_GEOMETRIES and name not in seen, 'unknown/duplicate geometry')
        seen.add(name)
        require(g['fe02_geometry_id'] == EXPECTED_GEOMETRY_IDS[name], 'FE02 link changed')
        coords = g['positions_m']
        require(isinstance(coords, list) and len(coords) == 4, 'geometry mic count changed')
        for actual, expected in zip(coords, EXPECTED_GEOMETRIES[name]):
            require(isinstance(actual, list) and len(actual) == 3, 'invalid XYZ vector')
            require(all(type(x) in (int, float) and math.isfinite(x) for x in actual),
                    'nonfinite/invalid mic position')
            require(all(abs(x-y) <= 1e-15 for x, y in zip(actual, expected)),
                    'preregistered geometry changed')
    require(seen == set(EXPECTED_GEOMETRIES), 'missing geometry')
    ranks = p['rank_cases']
    require(isinstance(ranks, list) and len(ranks) == len(EXPECTED_RANKS),
            'rank case count changed')
    for row, (caseid, name, mask, rank) in zip(ranks, EXPECTED_RANKS):
        require(isinstance(row, dict) and set(row) ==
                {'id', 'geometry', 'active_mask', 'expected_rank_xy'} and
                row['id'] == caseid and row['geometry'] == name and
                type(row['active_mask']) is int and row['active_mask'] == mask and
                type(row['expected_rank_xy']) is int and row['expected_rank_xy'] == rank,
                'rank case preregistration changed')
    contrasts = p['contrast_cases']
    require(isinstance(contrasts, list) and len(contrasts) == len(EXPECTED_CONTRASTS),
            'contrast case count changed')
    for row, (caseid, name, mask, a, b, relation, limit) in zip(contrasts, EXPECTED_CONTRASTS):
        bound = 'max_difference_samples' if relation == 'same' else 'min_difference_samples'
        keys = {'id', 'geometry', 'active_mask', 'a_deg', 'b_deg', 'relation', bound}
        require(isinstance(row, dict) and set(row) == keys and row['id'] == caseid and
                row['geometry'] == name and type(row['active_mask']) is int and
                row['active_mask'] == mask and row['relation'] == relation and
                check_angle(row['a_deg']) == a and check_angle(row['b_deg']) == b and
                type(row[bound]) in (int, float) and row[bound] == limit,
                'contrast preregistration changed')
    return p


def check_fe02_link(p: dict, source: dict) -> None:
    all_geometries = source.get('geometries')
    require(source.get('experiment_id') == 'FE02-03-NATIVE-ARRAY-V1' and
            source.get('source_direction') == 'array-to-source' and
            source.get('speed_of_sound_m_per_s') == 343. and
            source.get('shipping_authority') is False and
            isinstance(all_geometries, list), 'FE02 baseline authority drift')
    index = {g['id']: g for g in all_geometries}
    for g in p['geometries']:
        src = index.get(g['fe02_geometry_id'])
        require(isinstance(src, dict) and src.get('sample_rate_hz') == 16000 and
                src.get('channel_map') == [0, 1, 2, 3] and
                src.get('latency_samples') == [0.0] * 4 and
                src.get('gains') == [1.0] * 4 and
                src.get('active_mask') == 15, 'FE02 source controls drift')
        coords = src['positions_m']
        require(isinstance(coords, list) and len(coords) == 4 and
                all(len(x) == 3 for x in coords), 'FE02 source geometry invalid')
        require(all(type(x) in (int, float) and math.isfinite(x) for pos in coords for x in pos),
                'FE02 nonfinite geometry')
        require(all(abs(x-y) <= 1e-15 for pos, expected in zip(coords, g['positions_m'])
                    for x, y in zip(pos, expected)), 'FE02 actual geometry does not match preregistration')


def active_indices(mask: int, mic_count: int = 4) -> tuple[int, ...]:
    require(type(mask) is int and 0 < mask < (1 << mic_count), 'invalid active physical mask')
    return tuple(i for i in range(mic_count) if mask & (1 << i))


def rank_xy(positions: tuple, mask: int) -> int:
    channels = active_indices(mask)
    ref = positions[channels[0]]
    vectors = [(positions[i][0] - ref[0], positions[i][1] - ref[1])
               for i in channels[1:]]
    nonzero = [v for v in vectors if math.hypot(*v) > 1e-12]
    if not nonzero:
        return 0
    x, y = nonzero[0]
    for vx, vy in nonzero[1:]:
        area = abs(x * vy - y * vx)
        if area > math.hypot(x, y) * math.hypot(vx, vy) * 1e-12:
            return 2
    return 1


def ideal_tdoa_samples(positions: tuple, mask: int, angles: list,
                       sample_rate_hz: int, sound_speed: float) -> tuple[int, tuple[float, ...]]:
    """Difference w.r.t first active physical mic; exclude that mic (zero TDOA)."""
    ids = active_indices(mask)
    azimuth, elevation = check_angle(angles)
    az, el = math.radians(azimuth), math.radians(elevation)
    direction = (math.cos(el) * math.cos(az),
                 math.cos(el) * math.sin(az), math.sin(el))
    origin = positions[ids[0]]
    values = tuple(sum((positions[i][axis] - origin[axis]) * direction[axis]
                       for axis in range(3)) * sample_rate_hz / sound_speed
                   for i in ids[1:])
    require(all(math.isfinite(v) for v in values), 'nonfinite ideal TDOA')
    return ids[0], values


def evaluate(p: dict) -> dict:
    validate_plan(p)
    geometries = {g['id']: tuple(tuple(x) for x in g['positions_m'])
                  for g in p['geometries']}
    ranks = []
    for row in p['rank_cases']:
        rank = rank_xy(geometries[row['geometry']], row['active_mask'])
        require(rank == row['expected_rank_xy'], 'analytical baseline rank mismatch')
        ranks.append({'id': row['id'], 'active_mask': row['active_mask'],
                      'reference_mic': active_indices(row['active_mask'])[0], 'rank_xy': rank})
    comparisons = []
    for row in p['contrast_cases']:
        positions = geometries[row['geometry']]
        ra, a = ideal_tdoa_samples(positions, row['active_mask'], row['a_deg'],
                                   p['sample_rate_hz'], p['speed_of_sound_m_per_s'])
        rb, b = ideal_tdoa_samples(positions, row['active_mask'], row['b_deg'],
                                   p['sample_rate_hz'], p['speed_of_sound_m_per_s'])
        require(ra == rb and len(a) == len(b), 'inconsistent reference/active set')
        contrast = max((abs(x-y) for x, y in zip(a, b)), default=0.0)
        if row['relation'] == 'same':
            require(contrast <= row['max_difference_samples'],
                    'mirror-nonidentifiability violated')
        else:
            require(contrast >= row['min_difference_samples'],
                    'distinct-bearing observability missing')
        comparisons.append({'id': row['id'], 'reference_mic': ra,
                            'difference_samples': contrast, 'relation': row['relation']})
    return {'schema_version': 1, 'experiment_id': EXPERIMENT,
            'decision': DECISION, 'shipping_authority': False,
            'source_role': 'analytic-noiseless-geometry',
            'no_doa_estimator': True, 'no_acoustic_score': True,
            'geometric_upper_bound_only': True,
            'rank_cases': ranks, 'contrast_cases': comparisons}


def render_json(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False,
                       separators=(',', ':')) + '\n').encode('utf-8')


def authoritative_plan() -> dict:
    require(sha256(PLAN.read_bytes()) == EXPECTED_PLAN_SHA256,
            'frozen experiment JSON SHA-256 mismatch')
    p = read_object(PLAN)
    validate_plan(p)
    check_fe02_link(p, read_object(FE02))
    return p


def build_receipt(revision: str) -> dict:
    require(re.fullmatch('[0-9a-f]{40}', revision) is not None,
            'exact 40-hex source revision required')
    p = authoritative_plan()
    return {'receipt_version': 1, 'source_revision': revision,
            'experiment_sha256': EXPECTED_PLAN_SHA256,
            'fe02_source_sha256': sha256(FE02.read_bytes()),
            'oracle_sha256': sha256(Path(__file__).read_bytes()),
            'result': evaluate(p)}


def verify(path: Path, revision: str) -> dict:
    require(path.is_file() and not path.is_symlink(), 'missing/unsafe receipt')
    actual = read_object(path)
    expect = build_receipt(revision)
    require(actual == expect, 'actual receipt mismatches exact-source oracle')
    require(path.read_bytes() == render_json(expect), 'receipt not canonical/exact bytes')
    return actual['result']


def run(path: Path, revision: str) -> dict:
    data = build_receipt(revision)
    # 'xb' never overwrites another experiment or failed receipt.
    with path.open('xb') as file:
        file.write(render_json(data))
    verify(path, revision)
    return data['result']


def self_test() -> None:
    p = authoritative_plan()
    result = evaluate(p)
    require(len(result['rank_cases']) == 6 and len(result['contrast_cases']) == 3,
            'expected exact analytic case set')
    require(result['rank_cases'][2]['reference_mic'] == 1,
            'mask 0xe reference must be physical mic 1')
    # Preregistered 'any three-active ULA4' statement covers all four masks.
    ula = EXPECTED_GEOMETRIES['ULA4']
    require(all(rank_xy(ula, mask) == 1 for mask in (0x7, 0xb, 0xd, 0xe)),
            'three-active ULA geometry unexpectedly noncollinear')
    require(result['contrast_cases'][0]['difference_samples'] <= 1e-12 and
            result['contrast_cases'][1]['difference_samples'] >= .25 and
            result['contrast_cases'][2]['difference_samples'] <= 1e-12,
            'pre-registered mirror/observability control failed')
    for change in (
        lambda q: q.update(shipping_authority=True),
        lambda q: q.update(decision='PROMOTED'),
        lambda q: q['geometries'][0]['positions_m'][3].__setitem__(0, .120),
        lambda q: q['geometries'][1]['positions_m'][0].__setitem__(1, float('nan')),
        lambda q: q['rank_cases'][2].update(active_mask=15),
        lambda q: q['rank_cases'][2].update(expected_rank_xy=1),
        lambda q: q['contrast_cases'][1].update(min_difference_samples=.01),
        lambda q: q['contrast_cases'][0].update(a_deg=[float('inf'), 0.]),
        lambda q: q['contrast_cases'][0].update(relation='distinct'),
        lambda q: q['contrast_cases'].pop(),
        lambda q: q.update(sample_rate_hz=8000),
        lambda q: q.update(reference_rule='arbitrary-mic'),
    ):
        mutant = copy.deepcopy(p)
        change(mutant)
        try:
            evaluate(mutant)
        except (ValueError, TypeError, KeyError, IndexError):
            pass
        else:
            raise AssertionError('mutated contract accepted')
    for badmask in (0, 16, -1, 1.5, True):
        try:
            active_indices(badmask)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid physical mask accepted')
    for badangle in ([float('nan'), 0], [30, float('inf')], [181, 0], [30, -91],
                     [True, 0], [30]):
        try:
            check_angle(badangle)
        except ValueError:
            pass
        else:
            raise AssertionError('nonfinite/out-of-range angle accepted')
    # Reference-source coordinate edits cannot be silently tolerated either.
    changed = read_object(FE02)
    victim = next(g for g in changed['geometries'] if g['id'] == 'uca4-offaxis')
    victim['positions_m'][0][0] = .05
    try:
        check_fe02_link(p, changed)
    except ValueError:
        pass
    else:
        raise AssertionError('FE02 geometric source drift accepted')
    with tempfile.TemporaryDirectory(prefix='fe03-a0-test-') as temp:
        path = Path(temp) / 'result.json'
        first = run(path, 'a'*40)
        require(first == verify(path, 'a'*40), 'round-trip equality broken')
        require(build_receipt('a'*40) == build_receipt('a'*40),
                'non-deterministic receipt')
        try:
            run(path, 'a'*40)
        except FileExistsError:
            pass
        else:
            raise AssertionError('existing output overwritten')
        fake = read_object(path)
        fake['result']['rank_cases'][0]['rank_xy'] = 2
        path.write_bytes(render_json(fake))
        try:
            verify(path, 'a'*40)
        except ValueError:
            pass
        else:
            raise AssertionError('tampered receipt accepted')
    print(json.dumps({'status': 'FE03_A0_GEOMETRY_SELF_TEST_PASS',
                      'rank_cases': result['rank_cases'],
                      'contrast_cases': result['contrast_cases'],
                      'plan_sha256': EXPECTED_PLAN_SHA256,
                      'fe02_sha256': sha256(FE02.read_bytes()),
                      'oracle_sha256': sha256(Path(__file__).read_bytes()),
                      'mutations_rejected': 12,
                      'invalid_masks_rejected': 5,
                      'invalid_angles_rejected': 6,
                      'decision': DECISION, 'shipping_authority': False}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--execution-source')
    args = parser.parse_args()
    if args.self_test:
        require(args.output is None and args.execution_source is None and not args.verify,
                'self-test must not mix with execution flags')
        self_test()
        return 0
    require(args.output is not None and args.execution_source is not None,
            '--output and --execution-source required')
    result = (verify(args.output, args.execution_source) if args.verify
              else run(args.output, args.execution_source))
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
