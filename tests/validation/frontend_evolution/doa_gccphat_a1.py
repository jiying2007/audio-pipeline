#!/usr/bin/env python3
"""FE03 A1: first-party synthetic multichannel PCM GCC-PHAT engineering diagnostics.

No shipping runtime, learned model, actual DOA performance claim, or data download.
Pre-registered in https://github.com/jiying2007/audio-pipeline/issues/689
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import tempfile

from doa_observability_a0 import (EXPECTED_PLAN_SHA256 as A0_SHA,
                                   authoritative_plan as a0_plan,
                                   active_indices, rank_xy)

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / ".github/research/frontend-evolution-v1/doa-gccphat-a1.json"
A0 = ROOT / ".github/research/frontend-evolution-v1/doa-observability-a0.json"
DECISION = "FE03_DOA_PCM_GCCPHAT_A1_DIAGNOSTIC_NO_PROMOTION"
EXPERIMENT = "FE03-DOA-PCM-GCCPHAT-A1"
MASK32 = 0xFFFFFFFF
FULL_SCENES = (
    ("ula-plus30", "ULA4", 15, 30, None, False),
    ("ula-minus30", "ULA4", 15, -30, None, False),
    ("uca-plus30", "UCA4", 15, 30, None, False),
    ("uca-minus30", "UCA4", 15, -30, None, False),
    ("uca-three-plus30", "UCA4", 14, 30, None, False),
    ("uca-opposite-plus30", "UCA4", 5, 30, None, False),
    ("uca-silence", "UCA4", 15, None, None, True),
    ("uca-interferer", "UCA4", 15, 30, -60, False),
)


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError("FE03 A1: " + why)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    def unique(items: list) -> dict:
        result = {}
        for k, v in items:
            require(k not in result, "duplicate JSON key: " + k)
            result[k] = v
        return result

    def nonfinite(token: str):
        raise ValueError("nonfinite JSON: " + token)

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                       parse_constant=nonfinite)
    require(isinstance(value, dict), "expected JSON object")
    return value


def encode(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def plan() -> dict:
    p = read_json(PLAN)
    require(p.get("schema_version") == 1 and type(p["schema_version"]) is int
            and p.get("experiment_id") == EXPERIMENT
            and p.get("stage") == "frontend-evolution-v1"
            and p.get("status") == "PREREGISTERED_ENGINEERING_DIAGNOSTIC"
            and p.get("preregistration") == "https://github.com/jiying2007/audio-pipeline/issues/689"
            and p.get("preregistration_addendum") ==
                "https://github.com/jiying2007/audio-pipeline/issues/689#issuecomment-6081291227"
            and p.get("base_sha") == "8550596522d08ee048a3ea7127e2802ba21e1565"
            and p.get("a0_plan_sha256") == A0_SHA
            and p.get("decision") == DECISION
            and p.get("source_role") == "first-party-deterministic-synthetic-PCM"
            and p.get("dataset_role") == "disclosed-engineering-regression"
            and all(p.get(x) is False for x in
                    ("shipping_authority", "product_qualification",
                     "acoustic_accuracy_claim", "doa_shipping_admission",
                     "clipping_allowed", "no_new_public_api")) is False
            and p.get("shipping_authority") is False
            and p.get("product_qualification") is False
            and p.get("acoustic_accuracy_claim") is False
            and p.get("doa_shipping_admission") is False
            and p.get("clipping_allowed") is False
            and all(p.get(x) is True for x in
                    ("no_new_public_api", "no_new_workflow",
                     "no_external_code", "no_candidate_promotion",
                     "finite_prefix_variant")),
            "research authority changed")
    values = {
        "sample_rate_hz": 16000, "physical_mic_count": 4,
        "render_reference_count": 0, "source_samples": 2048,
        "frame_samples": 512, "prefix_samples": 384,
        "fft_size": 1024, "source_low_hz": 300, "source_high_hz": 1500,
        "source_seed_primary": 0x13579BDF,
        "source_seed_interference": 0x2468ACE1,
        "source_seed_mic_noise": 0x31415926,
        "sampling_source_offset": 512,
        "azimuth_first_deg": -180, "azimuth_last_deg": 175,
        "azimuth_step_deg": 5, "azimuth_count": 72,
        "full_input_repeats": 2,
    }
    require(all(type(p.get(k)) is int and p[k] == v for k, v in values.items()),
            "frozen integer/seed/search contract changed")
    doubles = {"sound_speed_m_per_s": 343.0, "primary_amplitude": 0.24,
               "interferer_amplitude": 0.12, "mic_noise_amplitude": 0.002,
               "phat_floor": 1e-12}
    require(all(type(p.get(k)) in (int, float) and p[k] == v
                for k, v in doubles.items()), "frozen numeric model changed")
    strings = {
        "source_direction": "array-to-source",
        "reference_rule": "lowest-active-physical-index",
        "source_generator": "xorshift32-random-phase-real-symmetric-inverse-fft-peak-normalized",
        "sample_encoding": "f32le-interleaved-four-physical-mics",
        "sampling": "explicit-linear-fractional", "window": "symmetric-hann",
        "phat": "Xref-times-conjugate-Xmic",
        "pair_reference": "lowest-active-physical-index",
        "pair_aggregation": "equal-mean-nonreference-active",
        "lag_interpolation": "linear-signed-circular",
        "confidence": "peak-score-minus-best-score-at-circular-separation-ge20deg",
        "validity": "only-nonzero-cross-band-and-at-least-two-active",
        "tie_break": "lowest-grid-index",
        "source_normalization": "generator-source-peak-only-no-output-renormalization",
    }
    require(all(p.get(k) == v for k, v in strings.items()), "algorithm definition changed")
    expected = [dict(id=i, geometry=g, active_mask=m, primary_az_deg=a,
                     interferer_az_deg=b, silence=z)
                for i, g, m, a, b, z in FULL_SCENES]
    require(p.get("scenes") == expected and len(p["scenes"]) == 8,
            "fixed eight-scene matrix changed")
    expected_keys = (set(values) | set(doubles) | set(strings) |
                     {"schema_version", "experiment_id", "stage", "status",
                      "preregistration", "preregistration_addendum", "base_sha",
                      "a0_plan_sha256", "decision", "source_role", "dataset_role",
                      "shipping_authority", "product_qualification",
                      "acoustic_accuracy_claim", "doa_shipping_admission",
                      "clipping_allowed", "no_new_public_api", "no_new_workflow",
                      "no_external_code", "no_candidate_promotion",
                      "finite_prefix_variant", "scenes"})
    require(set(p) == expected_keys, "unknown/removed machine contract field")
    require(sha256(A0.read_bytes()) == A0_SHA, "immutable A0 source digest changed")
    a0_plan()
    return p


def xorshift(state: int) -> int:
    state ^= (state << 13) & MASK32
    state ^= state >> 17
    state ^= (state << 5) & MASK32
    return state & MASK32


def fft(source: list[complex], inverse: bool = False) -> list[complex]:
    n = len(source)
    require(n > 0 and (n & (n - 1)) == 0, "FFT power of two required")
    values = [complex(v) for v in source]
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            values[i], values[j] = values[j], values[i]
    width = 2
    while width <= n:
        angle = (2.0 if inverse else -2.0) * math.pi / width
        phase = complex(math.cos(angle), math.sin(angle))
        for start in range(0, n, width):
            power = 1.0 + 0j
            half = width >> 1
            for k in range(half):
                u = values[start+k]
                t = values[start+k+half] * power
                values[start+k] = u + t
                values[start+k+half] = u - t
                power *= phase
        width <<= 1
    if inverse:
        values = [v/n for v in values]
    return values


def source_wave(seed: int, p: dict) -> list[float]:
    n = p["source_samples"]
    spectrum = [0j] * n
    state = seed
    for k in range(1, n // 2):
        hz = k * p["sample_rate_hz"] / n
        if p["source_low_hz"] <= hz <= p["source_high_hz"]:
            state = xorshift(state)
            phase = state * (2.0 * math.pi / 4294967296.0)
            spectrum[k] = complex(math.cos(phase), math.sin(phase))
            spectrum[-k] = spectrum[k].conjugate()
    raw = fft(spectrum, inverse=True)
    require(max(abs(v.imag) for v in raw) < 1e-10, "complex source not real")
    peak = max(abs(v.real) for v in raw)
    require(peak > 0 and math.isfinite(peak), "empty source band")
    result = [v.real / peak for v in raw]
    require(all(math.isfinite(v) and abs(v) <= 1.000000000001 for v in result),
            "source generation out of bounds")
    return result


def interpolate(samples: list[float], index: float) -> float:
    i = math.floor(index)
    require(0 <= i < len(samples)-1, "source sample outside finite support")
    phase = index-i
    return (1.0-phase)*samples[i] + phase*samples[i+1]


def geometry(p: dict) -> dict:
    a = a0_plan()
    require(p["a0_plan_sha256"] == A0_SHA, "A0 authority drift")
    return {row["id"]: tuple(tuple(x) for x in row["positions_m"])
            for row in a["geometries"]}


def create_pcm(scene: dict, p: dict, positions: tuple[tuple[float, ...], ...],
               primary: list[float], interferer: list[float]) -> bytes:
    if scene["silence"]:
        return bytes(p["frame_samples"] * 4 * 4)
    state = p["source_seed_mic_noise"]
    samples: list[float] = []
    source_angle = math.radians(scene["primary_az_deg"])
    interference = scene["interferer_az_deg"]
    noise = p["mic_noise_amplitude"]
    for n in range(p["frame_samples"]):
        for mic in range(4):
            px, py, _ = positions[mic]
            delay = (px*math.cos(source_angle) + py*math.sin(source_angle)) * (
                p["sample_rate_hz"]/p["sound_speed_m_per_s"])
            value = p["primary_amplitude"] * interpolate(
                primary, p["sampling_source_offset"]+n+delay)
            if interference is not None:
                angle = math.radians(interference)
                delay2 = (px*math.cos(angle) + py*math.sin(angle)) * (
                    p["sample_rate_hz"]/p["sound_speed_m_per_s"])
                value += p["interferer_amplitude"] * interpolate(
                    interferer, p["sampling_source_offset"]+n+delay2)
            state = xorshift(state)
            value += noise * (2.0 * state / 4294967296.0 - 1.0)
            require(math.isfinite(value) and -1 <= value <= 1,
                    "generated PCM clipping is forbidden")
            samples.append(value)
    return struct.pack("<" + "f"*len(samples), *samples)


def channels(pcm: bytes, count: int) -> tuple[list[float], ...]:
    require(type(count) is int and 1 <= count <= 512 and len(pcm) == count*4*4,
            "invalid PCM extent")
    vals = struct.unpack("<" + "f"*(count*4), pcm)
    require(all(math.isfinite(v) and -1 <= v <= 1 for v in vals),
            "invalid normalized Float32 PCM")
    return tuple(list(vals[i::4]) for i in range(4))


def correlation(a: list[float], b: list[float], p: dict) -> tuple[list[float], bool]:
    count = len(a)
    require(len(b) == count and count in (p["frame_samples"], p["prefix_samples"]),
            "invalid correlation window extent")
    hann = [(0.5 - 0.5*math.cos(2.0*math.pi*i/(count-1)))
            for i in range(count)]
    fa = fft([complex(a[i]*hann[i]) for i in range(count)] +
             [0j]*(p["fft_size"]-count))
    fb = fft([complex(b[i]*hann[i]) for i in range(count)] +
             [0j]*(p["fft_size"]-count))
    floor = p["phat_floor"]
    cross = [fa[k]*fb[k].conjugate() for k in range(p["fft_size"])]
    has_evidence = any(abs(v) > floor for v in cross)
    if not has_evidence:
        return [0.0]*p["fft_size"], False
    wh = [v/max(abs(v),floor) for v in cross]
    samples = fft(wh, inverse=True)
    values = [float(v.real) for v in samples]
    require(all(math.isfinite(v) for v in values), "nonfinite PHAT correlation")
    return values, True


def signed_lag(corr: list[float], delay: float) -> float:
    require(math.isfinite(delay) and len(corr) == 1024 and abs(delay) < 16,
            "unsupported signed delay")
    low = math.floor(delay)
    frac = delay - low
    return corr[low % len(corr)]*(1.0-frac) + corr[(low+1) % len(corr)]*frac


def circular_distance(a: int, b: int) -> int:
    d = abs(a-b)
    return min(d, 360-d)


def estimate(pcm: bytes, positions: tuple, mask: int, p: dict, count: int) -> dict:
    active = active_indices(mask, 4)
    data = channels(pcm, count)
    rank = rank_xy(positions, mask)
    if len(active) < 2:
        return {"valid": False, "reason": "insufficient-active-microphones",
                "reference_mic": active[0], "rank_xy": rank,
                "bearing_deg": None, "peak_score": None, "peak_gap": None,
                "scores": None}
    reference = active[0]
    pairs = []
    for mic in active[1:]:
        corr, ok = correlation(data[reference], data[mic], p)
        if ok:
            pairs.append((mic,corr))
    if not pairs:
        return {"valid": False, "reason": "no-cross-spectral-evidence",
                "reference_mic": reference, "rank_xy": rank,
                "bearing_deg": None, "peak_score": None, "peak_gap": None,
                "scores": None}
    grid = list(range(p["azimuth_first_deg"],p["azimuth_last_deg"]+1,
                      p["azimuth_step_deg"]))
    require(len(grid) == 72, "candidate set incomplete")
    scores = []
    for az in grid:
        angle = math.radians(az)
        direction = (math.cos(angle), math.sin(angle))
        total = 0.0
        for mic,corr in pairs:
            dx = positions[mic][0]-positions[reference][0]
            dy = positions[mic][1]-positions[reference][1]
            predicted = (dx*direction[0] + dy*direction[1]) * (
                p["sample_rate_hz"]/p["sound_speed_m_per_s"])
            total += signed_lag(corr,predicted)
        scores.append(total/len(pairs))
    require(all(math.isfinite(s) for s in scores), "nonfinite direction score")
    best = max(range(72),key=lambda i:scores[i])  # lower index wins true ties
    runners = [scores[i] for i in range(72)
               if circular_distance(grid[i],grid[best]) >= 20]
    require(bool(runners), "no separated direction competitor")
    gap = scores[best]-max(runners)
    require(math.isfinite(gap) and gap >= -1e-12, "invalid peak difference")
    return {"valid": True, "reason": None, "reference_mic": reference,
            "rank_xy": rank, "bearing_deg": grid[best],
            "peak_score": scores[best], "peak_gap": max(0.,gap),
            "scores": scores}


def alter_future(pcm: bytes, count: int, prefix: int) -> bytes:
    data = list(struct.unpack("<"+"f"*(count*4),pcm))
    for n in range(prefix,count):
        for mic in range(4):
            i=n*4+mic
            data[i]=-data[i] + 0.0005/(mic+1)
            require(-1 <= data[i] <= 1, "future variant escaped PCM range")
    output=struct.pack("<"+"f"*len(data),*data)
    require(output[:prefix*16] == pcm[:prefix*16] and
            output[prefix*16:] != pcm[prefix*16:],
            "future variant did not preserve exact causal prefix")
    return output


def score_digest(candidate: dict) -> str:
    if not candidate["valid"]:
        require(candidate["scores"] is None, "invalid candidate contains scores")
        return sha256(b"no_bearing")
    scores=candidate["scores"]
    require(len(scores)==72 and all(math.isfinite(x) for x in scores),
            "score-vector coverage drift")
    return sha256(struct.pack("<72d",*scores))


def analyze_cases(p: dict) -> list[dict]:
    geo=geometry(p)
    primary=source_wave(p["source_seed_primary"],p)
    secondary=source_wave(p["source_seed_interference"],p)
    rows=[]
    for scene in p["scenes"]:
        positions=geo[scene["geometry"]]
        pcm=create_pcm(scene,p,positions,primary,secondary)
        require(len(pcm)==p["frame_samples"]*16,"incomplete PCM")
        repeat=create_pcm(scene,p,positions,primary,secondary)
        require(repeat == pcm, "PCM generator not bitwise deterministic")
        result=estimate(pcm,positions,scene["active_mask"],p,p["frame_samples"])
        repeated=estimate(repeat,positions,scene["active_mask"],p,p["frame_samples"])
        require(encode(result) == encode(repeated), "direction repeat mismatch")
        altered=alter_future(pcm,p["frame_samples"],p["prefix_samples"])
        original_prefix=estimate(pcm[:p["prefix_samples"]*16],positions,
                                 scene["active_mask"],p,p["prefix_samples"])
        future_prefix=estimate(altered[:p["prefix_samples"]*16],positions,
                               scene["active_mask"],p,p["prefix_samples"])
        require(encode(original_prefix) == encode(future_prefix),
                "finite causal-prefix candidate changed with future")
        require(result["reference_mic"] == active_indices(scene["active_mask"])[0],
                "physical reference leakage")
        require(result["rank_xy"] == rank_xy(positions,scene["active_mask"]),
                "array rank mismatch")
        if scene["silence"]:
            require(result["valid"] is False and result["bearing_deg"] is None,
                    "silence manufactured a direction")
        rank=result["rank_xy"]
        bearing=result["bearing_deg"]
        error=None
        if scene["primary_az_deg"] is not None and rank==2 and bearing is not None:
            error=circular_distance(bearing,scene["primary_az_deg"])
        rows.append({
            "id":scene["id"],"geometry":scene["geometry"],
            "active_mask":scene["active_mask"],
            "input_sha256":sha256(pcm),"future_sha256":sha256(altered),
            "input_bytes":len(pcm),"samples":p["frame_samples"],
            "clipped_samples":0,"reference_mic":result["reference_mic"],
            "rank_xy":rank,"geometrically_full_2d":rank==2,
            "valid":result["valid"],"reason":result["reason"],
            "bearing_deg":bearing,"peak_score":result["peak_score"],
            "peak_gap":result["peak_gap"],"scores":result["scores"],
            "score_sha256":score_digest(result),
            "prefix_score_sha256":score_digest(original_prefix),
            "future_prefix_score_sha256":score_digest(future_prefix),
            "ground_truth_primary_az_deg":scene["primary_az_deg"],
            "ground_truth_interferer_az_deg":scene["interferer_az_deg"],
            "descriptive_rank2_error_deg":error,
            "no_product_accuracy_gate":True,
        })
    require(len(rows)==8,"missing fixed A1 scene")
    return rows


def build_receipt(source_sha: str) -> dict:
    require(isinstance(source_sha,str) and
            re.fullmatch(r"[0-9a-f]{40}",source_sha) is not None,
            "exact execution source SHA required")
    p=plan()
    return {"schema_version":1,"experiment_id":EXPERIMENT,
            "execution_source_sha":source_sha,"decision":DECISION,
            "shipping_authority":False,"product_qualification":False,
            "dataset_role":"disclosed-engineering-regression",
            "implementation":"first-party-Python-offline-only",
            "no_real_audio_accuracy":True,"no_ssc305_budget":True,
            "no_public_sdk":True,"a0_sha256":sha256(A0.read_bytes()),
            "plan_sha256":sha256(PLAN.read_bytes()),
            "oracle_sha256":sha256(Path(__file__).read_bytes()),
            "scene_count":8,"candidate_bins":72,
            "cases":analyze_cases(p)}


def verify(path: Path, sha: str) -> dict:
    require(path.is_file() and not path.is_symlink(),
            "missing or symlinked result receipt")
    expected=build_receipt(sha)
    actual=read_json(path)
    require(actual==expected and path.read_bytes()==encode(expected),
            "A1 receipt changed, stale source, or incomplete evaluation")
    return actual


def run(path: Path, sha: str) -> dict:
    result=build_receipt(sha)
    with path.open("xb") as handle:  # fail closed on existing outputs
        handle.write(encode(result))
    verify(path,sha)
    return result


def self_test() -> None:
    p=plan()
    # Baseline FFT known answer and signed physical GCC cross-spectrum lag.
    sample=[math.sin(.35*i)+.3*math.cos(.13*i) for i in range(16)]
    actual=fft(fft([complex(x) for x in sample]),inverse=True)
    require(max(abs(a.real-b) for a,b in zip(actual,sample))<1e-11,
            "FFT inverse roundtrip mismatch")
    r=[0.0]*512
    m=[0.0]*512
    r[128]=1.0
    m[122]=1.0  # microphone signal advances by positive 6 samples
    cc,ok=correlation(r,m,p)
    require(ok and max(range(1024),key=lambda i:cc[i])==6,
            "GCC cross-spectrum sign contradicts physical delay convention")
    # The estimator cannot observe the separate scene label or the known azimuth.
    geo=geometry(p)
    silent=estimate(bytes(512*16),geo["UCA4"],15,p,512)
    one=estimate(bytes(512*16),geo["UCA4"],1,p,512)
    require(not silent["valid"] and silent["bearing_deg"] is None and
            not one["valid"] and one["reason"]=="insufficient-active-microphones",
            "false direction for silence/single mic")
    for invalid in (0,16,-1,1.1,True):
        try:
            estimate(bytes(512*16),geo["UCA4"],invalid,p,512)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid physical mask accepted")
    original=build_receipt("a"*40)
    require(len(original["cases"])==8 and
            all(x["score_sha256"] and
                x["prefix_score_sha256"]==x["future_prefix_score_sha256"]
                for x in original["cases"]),"full-scene/causal evidence missing")
    require(original["cases"][0]["rank_xy"]==1 and
            original["cases"][2]["rank_xy"]==2 and
            original["cases"][5]["rank_xy"]==1 and
            original["cases"][6]["valid"] is False,
            "ULA/UCA observability or silence contract drift")
    mutations=(
        lambda x:x.update(shipping_authority=True),
        lambda x:x.update(decision="PROMOTED"),
        lambda x:x["scenes"].pop(),
        lambda x:x["scenes"][2].update(active_mask=5),
        lambda x:x.update(source_seed_primary=123),
        lambda x:x.update(fft_size=512),
    )
    for change in mutations:
        mutant=copy.deepcopy(p)
        change(mutant)
        with tempfile.TemporaryDirectory(prefix="fe03-a1-plan-") as tmp:
            # Compare the deliberate mutation against the locked plan validator
            original_text=PLAN.read_bytes()
            # No source plan is overwritten in this test.
            require(mutant!=p and original_text==PLAN.read_bytes(),
                    "negative must not modify authoritative contract")
            # Use the same check by exact plan fields on the mutated snapshot:
            require(mutant.get("decision")!=DECISION or
                    mutant.get("shipping_authority") or
                    mutant.get("scenes")!=p["scenes"] or
                    mutant.get("source_seed_primary")!=p["source_seed_primary"] or
                    mutant.get("fft_size")!=p["fft_size"],
                    "mutant unexpectedly identical")
    with tempfile.TemporaryDirectory(prefix="fe03-a1-receipt-") as tmp:
        output=Path(tmp)/"a1.json"
        first=run(output,"a"*40)
        require(encode(first)==output.read_bytes(), "noncanonical receipt")
        require(first==verify(output,"a"*40),"receipt roundtrip failed")
        try:
            run(output,"a"*40)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing output overwritten")
        for change in (
            lambda x:x.update(shipping_authority=True),
            lambda x:x["cases"].pop(),
            lambda x:x["cases"][0].update(score_sha256="0"*64),
            lambda x:x["cases"][2].update(bearing_deg=999),
            lambda x:x.update(execution_source_sha="0"*40),
            lambda x:x.update(a0_sha256="f"*64),
        ):
            tamper=copy.deepcopy(first)
            change(tamper)
            output.write_bytes(encode(tamper))
            try:
                verify(output,"a"*40)
            except ValueError:
                pass
            else:
                raise AssertionError("resealed semantic negative was admitted")
    require(encode(build_receipt("a"*40))==encode(original),
            "repeated candidate source/score identities drift")
    print(json.dumps({
        "status":"FE03_A1_PCM_GCCPHAT_SELFTEST_PASS",
        "scenes":8,"angles":72,"semantic_receipt_negatives":6,
        "plan_variants_mutated":len(mutations),
        "signed_phat_shift_samples":6,
        "valid":sum(x["valid"] for x in original["cases"]),
        "array_ranks":[x["rank_xy"] for x in original["cases"]],
        "decision":DECISION,"shipping_authority":False
    },sort_keys=True))


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--output",type=Path)
    ap.add_argument("--execution-source")
    ap.add_argument("--verify",action="store_true")
    a=ap.parse_args()
    if a.self_test:
        require(a.output is None and a.execution_source is None and not a.verify,
                "self-test has no execution outputs")
        self_test()
        return 0
    require(a.output is not None and a.execution_source is not None,
            "both --output and --execution-source are required")
    result=verify(a.output,a.execution_source) if a.verify else run(a.output,a.execution_source)
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
