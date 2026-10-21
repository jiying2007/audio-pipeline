"""D17 sample-coordinate diagnostics; no DSP search or acoustic qualification."""
from __future__ import annotations

import argparse
from array import array
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import (
    PLAN, bounded, intake, integer, require, sha, strict_json, summary,
)
from tools.codex_assets.device_replay import check_config, verify_binding

RECEIPT_SHA = '2a1ed561e142a991b9c5679b35df0e44f12ab32ecc6e3e67c42e4582377f85f2'
DECISION = 'ALIGNMENT_CONTRACT_DIAGNOSTIC_NO_PROMOTION'


def shifted(raw, delay):
    integer(delay, 0, 1600, 'delay')
    return [0 if j < delay else raw[j - delay] for j in range(len(raw))]


def buffered_reference(raw, delay):
    """Model HDI's 128-sample append / 256-sample consume, including pending mic."""
    integer(delay, 0, 1600, 'delay')
    require(len(raw) % 128 == 0, 'partial input hop')
    queue = [0] * delay
    output = []
    mic_pending = 0
    for offset in range(0, len(raw), 128):
        queue.extend(raw[offset:offset + 128])
        mic_pending += 128
        if mic_pending >= 256:
            require(len(queue) >= 256, 'reference queue underflow')
            output.extend(queue[:256])
            del queue[:256]
            mic_pending -= 256
    require(len(queue) == delay + mic_pending, 'queue conservation')
    return output, mic_pending


def s16_bytes(samples):
    values = array('h', samples)
    if sys.byteorder != 'little':
        values.byteswap()
    return values.tobytes()


def mismatch(a, b):
    require(len(a) == len(b), 'comparison length mismatch')
    return sum(x != y for x, y in zip(a, b))


def audit(root, receipt, plan_path=PLAN):
    data = bounded(receipt, 4 * 1024 * 1024)
    require(sha(data) == RECEIPT_SHA, 'D16 receipt identity drift')
    r = strict_json(data)
    p, captures = intake(root, plan_path)
    require(r['plan_sha256'] == sha(bounded(plan_path, 65536)) and
            r['input_lock_sha256'] == p['input_lock_sha256'], 'receipt plan/input lock drift')
    case_records = {c['case_id']: c for c in r['cases']}
    require(len(case_records) == len(r['cases']) == len(captures) == 16 and
            set(case_records) == {c['case_id'] for c in captures}, 'receipt case set drift')
    configs = {}
    for mode, record in r['configurations'].items():
        configs[mode] = strict_json(bounded(verify_binding(receipt.parent, record, 65536), 65536))
    for mode, cfg in configs.items():
        check_config(cfg, mode, configs['default'])
    rows = []
    for c in captures:
        require(c['session']['sample_rate'] == 16000, 'fixed coordinate rate mismatch')
        s = summary(c)
        record = case_records[c['case_id']]
        require(record['intake'] == s, 'receipt intake drift')
        raw = c['raw'].samples[::2]
        used = c['ref'].samples
        delay = c['session']['ref_delay_samples']
        reconstructed, pending = buffered_reference(raw, delay)
        require(len(reconstructed) == len(used) and pending == s['unpaired_raw_tail'], 'native pairing drift')
        require(reconstructed == list(used) and reconstructed == shifted(raw, delay)[:len(used)],
                'independent reference reconstruction mismatch')
        n = s['replay_samples']
        require(set(record['adapted_inputs']) == {'mic', 'render'}, 'adapted input set drift')
        mic_data = bounded(verify_binding(receipt.parent, record['adapted_inputs']['mic']), 3 * 1024 * 1024)
        render_data = bounded(verify_binding(receipt.parent, record['adapted_inputs']['render']), 3 * 1024 * 1024)
        require(mic_data == c['mic'].data[:n * 4] and render_data == s16_bytes(raw[:n]),
                'adapted bytes drift')
        comparisons = {}
        # Fixed preregistered coordinates, never searched or selected as a candidate.
        for label, candidate_delay in (('minus_one', max(0, delay - 1)), ('plus_one', delay + 1),
                                       ('fixed_1ms', 16), ('fixed_40ms', 640)):
            if candidate_delay > 1600:
                comparisons[label] = {'available': False}
                continue
            count = mismatch(shifted(raw, candidate_delay)[:n], used[:n])
            comparisons[label] = dict(available=True, raw_delay_samples=candidate_delay,
                                      mismatched_samples=count, distinguishable=count > 0)
        count = mismatch(shifted(used, delay)[:n], used[:n])
        comparisons['used_plus_capture_delay'] = dict(available=True, raw_delay_samples=2 * delay,
                                                       mismatched_samples=count, distinguishable=count > 0)
        rows.append(dict(case_id=c['case_id'], scene=c['session']['scene'], input_sha256=c['input_sha256'],
                         ref_delay_samples=delay, exact_delay_us=delay * 1000000 / 16000,
                         fixed_1ms_minus_capture_samples=16 - delay,
                         native_samples=len(used), replay_samples=n, pending_input_samples=pending,
                         native_tail_removed=s['replay_tail'], native_reference_sha256=sha(s16_bytes(reconstructed)),
                         used_reference_sha256=sha(c['ref'].data), adapted_render_sha256=sha(render_data),
                         reference_reconstruction_equal=True, fixed_coordinate_comparisons=comparisons))
    require(sha(bounded(receipt, 4 * 1024 * 1024)) == RECEIPT_SHA, 'receipt changed during audit')
    # Re-read the lock after measurement; receipt validation is deliberately input-only.
    _, final_captures = intake(root, plan_path)
    require([c['input_sha256'] for c in captures] == [c['input_sha256'] for c in final_captures],
            'input changed during audit')
    return dict(experiment='FE_DEVICE_ALIGNMENT_D17', decision=DECISION, status='SAMPLE_COORDINATE_AUDIT_PASS',
                data_role='development', promotion_allowed=False, shipping_approved=False, hil_pass=False,
                receipt_scope='D16 identity, configurations and adapted inputs; no new DSP/output qualification',
                receipt_sha256=RECEIPT_SHA, plan_sha256=sha(bounded(plan_path, 65536)),
                default_initial_samples=configs['default']['initial_delay_ms'] * 16,
                one_ms_initial_samples=configs['fixed1']['initial_delay_ms'] * 16,
                writes=False, cases=rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--plan', type=Path, default=PLAN)
    parser.add_argument('--dry-run', action='store_true', help='read-only full sample audit; no DSP or file writes')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(audit(args.root, args.receipt, args.plan), ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as exc:
        print('device_alignment: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
