#!/usr/bin/env python3
from pathlib import Path

path = Path('validation/tools/run_validation.py')
text = path.read_text(encoding='utf-8')
old = '''def max_abs_corr(a: Sequence[int], b: Sequence[int], sample_rate: int) -> float:\n    max_lag = max(1, sample_rate // 10)\n    step = max(1, max_lag // 60)\n    lags = list(range(-max_lag, max_lag + 1, step))\n    if 0 not in lags:\n        lags.append(0)\n    return max((normalized_corr(a, b, lag) for lag in lags), default=0.0)\n\n\n'''
new = '''def max_abs_corr(a: Sequence[int], b: Sequence[int], sample_rate: int) -> float:\n    max_lag = max(1, sample_rate // 10)\n    step = max(1, max_lag // 60)\n    lags = list(range(-max_lag, max_lag + 1, step))\n    if 0 not in lags:\n        lags.append(0)\n    return max((normalized_corr(a, b, lag) for lag in lags), default=0.0)\n\n\ndef aligned_si_sdr(reference: Sequence[int], estimate: Sequence[int],\n                   sample_rate: int, expected_delay_samples: int) -> tuple[float | None, int]:\n    """Calculate SI-SDR after bounded sample-exact latency refinement.\n\n    The search is anchored to the pipeline-declared algorithmic latency. Input\n    references use an expected delay of zero. A narrow +/-3 ms refinement\n    absorbs integer-ms latency reporting and filter rounding without turning\n    the evaluator into an unconstrained synchronizer that can search for a\n    favorable score.\n    """\n    radius = max(2, sample_rate * 3 // 1000)\n    center = -int(expected_delay_samples)\n    best_lag = center\n    best_corr = -1.0\n    for lag in range(center - radius, center + radius + 1):\n        corr = normalized_corr(reference, estimate, lag, stride=4)\n        if corr > best_corr:\n            best_corr = corr\n            best_lag = lag\n    if best_lag >= 0:\n        ref = reference[best_lag:]\n        est = estimate\n    else:\n        ref = reference\n        est = estimate[-best_lag:]\n    count = min(len(ref), len(est))\n    if count < 16:\n        return None, -best_lag\n    return si_sdr_db(ref[:count], est[:count]), -best_lag\n\n\n'''
if old not in text:
    raise SystemExit('correlation block not found')
text = text.replace(old, new, 1)
old = '''    if clean_path is not None:\n        clean, _ = read_audio(clean_path, rate, 1)\n        input_sdr = si_sdr_db(clean, mic0)\n        output_sdr = si_sdr_db(clean, output)\n        metrics["input_near_si_sdr_db"] = input_sdr\n        metrics["near_si_sdr_db"] = output_sdr\n        metrics["near_si_sdr_improvement_db"] = None if input_sdr is None or output_sdr is None else output_sdr - input_sdr\n'''
new = '''    if clean_path is not None:\n        clean, _ = read_audio(clean_path, rate, 1)\n        declared_latency_ms = int(trace[0].get("algorithmic_latency_ms", 0)) if trace else 0\n        expected_output_delay = declared_latency_ms * rate // 1000\n        input_sdr, input_alignment = aligned_si_sdr(clean, mic0, rate, 0)\n        output_sdr, output_alignment = aligned_si_sdr(clean, output, rate, expected_output_delay)\n        metrics["input_near_si_sdr_db"] = input_sdr\n        metrics["near_si_sdr_db"] = output_sdr\n        metrics["declared_algorithmic_latency_ms"] = declared_latency_ms\n        metrics["input_alignment_samples"] = input_alignment\n        metrics["output_alignment_samples"] = output_alignment\n        metrics["near_si_sdr_improvement_db"] = None if input_sdr is None or output_sdr is None else output_sdr - input_sdr\n'''
if old not in text:
    raise SystemExit('clean reference block not found')
text = text.replace(old, new, 1)
old = '''    assert (si_sdr_db(ref, ref) or 0) > 100\n    assert max_abs_corr(ref, ref, rate) > 0.99\n    assert vad_f1([0, 1, 1, 0], [{"vad_active": 0}, {"vad_active": 1}, {"vad_active": 1}, {"vad_active": 0}]) == 1.0\n'''
new = '''    assert (si_sdr_db(ref, ref) or 0) > 100\n    assert max_abs_corr(ref, ref, rate) > 0.99\n    state = 1\n    broadband = []\n    for _ in range(rate):\n        state = (1664525 * state + 1013904223) & 0xffffffff\n        broadband.append(((state >> 16) & 0xffff) - 32768)\n    delayed = [0] * 137 + broadband[:-137]\n    delayed_sdr, alignment = aligned_si_sdr(broadband, delayed, rate, 137)\n    assert alignment == 137\n    assert delayed_sdr is not None and delayed_sdr > 100\n    assert vad_f1([0, 1, 1, 0], [{"vad_active": 0}, {"vad_active": 1}, {"vad_active": 1}, {"vad_active": 0}]) == 1.0\n'''
if old not in text:
    raise SystemExit('self-test block not found')
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')

processor = Path('examples/process_pcm.c')
ptext = processor.read_text(encoding='utf-8')
old = '''                        "{\\\"frame\\\":%u,\\\"vad_probability\\\":%.7g,\\\"vad_active\\\":%u,"\n                        "\\\"far_end_active\\\":%u,\\\"double_talk_active\\\":%u,"\n'''
new = '''                        "{\\\"frame\\\":%u,\\\"algorithmic_latency_ms\\\":%u,"\n                        "\\\"vad_probability\\\":%.7g,\\\"vad_active\\\":%u,"\n                        "\\\"far_end_active\\\":%u,\\\"double_talk_active\\\":%u,"\n'''
if old not in ptext:
    raise SystemExit('processor metrics format block not found')
ptext = ptext.replace(old, new, 1)
old = '''                        frame_index,\n                        (double)metrics.vad_probability,\n'''
new = '''                        frame_index,\n                        ap_pipeline_algorithmic_latency_ms(pipeline),\n                        (double)metrics.vad_probability,\n'''
if old not in ptext:
    raise SystemExit('processor metrics arguments block not found')
ptext = ptext.replace(old, new, 1)
processor.write_text(ptext, encoding='utf-8')

Path('scripts/apply_validation_alignment.py').unlink()
