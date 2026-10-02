#!/usr/bin/env python3
"""Build deterministic candidate-zero AEC transition/decomposition corpus.

This corpus diagnoses talk-state, echo-path, loudspeaker-gain and nonlinear
playback transitions. It has no candidate, tuning, promotion or shipping
authority.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

from build_validation_corpus import (
    FRAME, RATE, add_case, clamp16, echo_from_render, mix, render_signal,
    scale, speech_like,
)

GENERATOR_VERSION = 1


def hard_clip(signal: list[int], limit: int) -> list[int]:
    return [max(-limit, min(limit, value)) for value in signal]


def soft_saturate(signal: list[int], drive: float) -> list[int]:
    denom = math.tanh(drive)
    return [
        clamp16(32767.0 * math.tanh(drive * value / 32767.0) / denom)
        for value in signal
    ]


def piecewise(first: list[int], second: list[int], split: int) -> list[int]:
    return first[:split] + second[split:]


def annotate(cases: list[dict], dimensions: dict) -> None:
    cases[-1]["dimensions"] = dimensions
    cases[-1]["source"].update({
        "authority": "candidate-zero-diagnostic",
        "generator": "build_aec_transition_corpus.py",
    })


def build(output: Path, seed: int, seconds: float) -> dict:
    frames = max(600, int(round(seconds * 100.0)))
    samples = frames * FRAME
    split_frame = frames // 2
    split = split_frame * FRAME
    active = [(0.55, 1.75), (2.35, min(seconds - 0.35, 4.55))]
    clean, labels = speech_like(frames, seed + 1, active)
    render = render_signal(samples, seed + 2)
    silent_render = [0] * samples

    echo_a = echo_from_render(render, [(320, 0.52), (704, 0.20), (1248, 0.08)])
    echo_b = echo_from_render(render, [(176, 0.45), (864, 0.28), (1488, 0.07)])
    cases: list[dict] = []

    add_case(
        cases, output, "far-end-static-a", "aec-transition-far-end-static",
        echo_a, 1, render=render, echo=echo_a,
    )
    annotate(cases, {"family": "talk_state", "talk_state": "far_end_only", "path": "a"})

    add_case(
        cases, output, "near-end-only", "aec-transition-near-end-only",
        clean, 1, clean=clean, render=silent_render, labels=labels,
    )
    annotate(cases, {"family": "talk_state", "talk_state": "near_end_only"})

    near = scale(clean, 0.90)
    add_case(
        cases, output, "double-talk", "aec-transition-double-talk",
        mix(near, echo_a), 1, clean=near, render=render, labels=labels,
    )
    annotate(cases, {"family": "talk_state", "talk_state": "double_talk", "path": "a"})

    changing_echo = piecewise(echo_a, echo_b, split)
    add_case(
        cases, output, "echo-path-change", "aec-transition-echo-path-change",
        changing_echo, 1, render=render, echo=changing_echo,
        control={"echo_path_change_frame": split_frame},
    )
    annotate(cases, {
        "family": "echo_path",
        "transition": "abrupt",
        "from": "a",
        "to": "b",
        "frame": split_frame,
    })

    low_echo = scale(echo_a, 0.45)
    high_echo = scale(echo_a, 1.30)
    speaker_step_echo = piecewise(low_echo, high_echo, split)
    add_case(
        cases, output, "speaker-acoustic-gain-step",
        "aec-transition-speaker-acoustic-gain-step",
        speaker_step_echo, 1, render=render, echo=speaker_step_echo,
        control={"echo_path_change_frame": split_frame},
    )
    annotate(cases, {
        "family": "speaker_level",
        "transition": "acoustic_gain_step",
        "gain_before": 0.45,
        "gain_after": 1.30,
        "frame": split_frame,
    })

    low_render = scale(render, 0.45)
    high_render = scale(render, 1.25)
    render_step = piecewise(low_render, high_render, split)
    render_step_echo = echo_from_render(
        render_step, [(320, 0.52), (704, 0.20), (1248, 0.08)]
    )
    add_case(
        cases, output, "render-level-step", "aec-transition-render-level-step",
        render_step_echo, 1, render=render_step, echo=render_step_echo,
    )
    annotate(cases, {
        "family": "speaker_level",
        "transition": "render_level_step",
        "gain_before": 0.45,
        "gain_after": 1.25,
        "frame": split_frame,
    })

    clipped_playback = hard_clip(scale(render, 1.8), 6500)
    clipped_echo = echo_from_render(
        clipped_playback, [(320, 0.52), (704, 0.20), (1248, 0.08)]
    )
    add_case(
        cases, output, "clipped-playback", "aec-transition-clipped-playback",
        clipped_echo, 1, render=render, echo=clipped_echo,
    )
    annotate(cases, {
        "family": "nonlinear_playback",
        "kind": "hard_clip",
        "clip_limit": 6500,
        "aec_render_reference": "pre_nonlinearity",
    })

    saturated_playback = soft_saturate(render, 3.0)
    saturated_echo = echo_from_render(
        saturated_playback, [(320, 0.52), (704, 0.20), (1248, 0.08)]
    )
    add_case(
        cases, output, "soft-saturated-playback",
        "aec-transition-soft-saturated-playback",
        saturated_echo, 1, render=render, echo=saturated_echo,
    )
    annotate(cases, {
        "family": "nonlinear_playback",
        "kind": "soft_saturation",
        "drive": 3.0,
        "aec_render_reference": "pre_nonlinearity",
    })

    corpus = {
        "schema_version": 1,
        "corpus_id": f"aec-transition-v{GENERATOR_VERSION}-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "build_aec_transition_corpus.py",
            "version": GENERATOR_VERSION,
            "seed": seed,
            "seconds": frames / 100.0,
        },
        "sources": ["deterministic-aec-transition-v1"],
        "sealed_data": True,
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "promotion_allowed": False,
        "shipping_change_allowed": False,
        "cases": cases,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-aec-transition-") as raw:
        root = Path(raw)
        a = build(root / "a", 6107, 6.0)
        b = build(root / "b", 6107, 6.0)
        c = build(root / "c", 6207, 6.0)
        assert len(a["cases"]) == len(b["cases"]) == len(c["cases"]) == 8
        assert a["candidate_limit"] == a["confirmation_limit"] == 0
        assert [x["dimensions"] for x in a["cases"]] == [x["dimensions"] for x in b["cases"]]
        assert {x["dimensions"]["family"] for x in a["cases"]} == {
            "talk_state", "echo_path", "speaker_level", "nonlinear_playback"
        }
        assert (root / "a" / "corpus.json").read_bytes() == (root / "b" / "corpus.json").read_bytes()
        assert (root / "a" / "corpus.json").read_bytes() != (root / "c" / "corpus.json").read_bytes()
    print("AEC transition candidate-zero corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=6107)
    parser.add_argument("--seconds", type=float, default=6.0)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    if not 6.0 <= args.seconds <= 20.0:
        parser.error("--seconds must be within 6..20")
    corpus = build(args.output, args.seed, args.seconds)
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "corpus_id": corpus["corpus_id"],
        "cases": len(corpus["cases"]),
        "seed": args.seed,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
