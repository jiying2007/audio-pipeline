#!/usr/bin/env python3
"""Apply one frozen stage source candidate to an exact working tree.

This tool is intentionally fail-closed: each candidate matches one exact source
shape and replaces it once. It is for non-shipping candidate evaluation only.
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path


VAD_PATH = Path("src/enhance/ap_vad.c")
AGC_PATH = Path("src/enhance/ap_agc.c")

VAD_DEFINE_OLD = """#define AP_VAD_STRONG_REFRESH_THRESHOLD 0.50f
#define AP_VAD_STRONG_HOLD_FRAMES 8u
#define AP_VAD_WEAK_HOLD_FRAMES 6u
"""
VAD_DEFINE_NEW = """#define AP_VAD_VERY_STRONG_REFRESH_THRESHOLD 0.70f
#define AP_VAD_STRONG_REFRESH_THRESHOLD 0.50f
#define AP_VAD_VERY_STRONG_HOLD_FRAMES 10u
#define AP_VAD_STRONG_HOLD_FRAMES 8u
#define AP_VAD_WEAK_HOLD_FRAMES 6u
"""
VAD_LOGIC_OLD = """    if (prob >= AP_VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = AP_VAD_STRONG_HOLD_FRAMES;
    } else if (prob > decision_threshold) {
"""
VAD_LOGIC_NEW = """    if (prob >= AP_VAD_VERY_STRONG_REFRESH_THRESHOLD) {
        state->hangover = AP_VAD_VERY_STRONG_HOLD_FRAMES;
    } else if (prob >= AP_VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = AP_VAD_STRONG_HOLD_FRAMES;
    } else if (prob > decision_threshold) {
"""

AGC_LOGIC_OLD = """    alpha = target_gain < state->gain ? 0.25f : 0.015f;
    state->gain += alpha * (target_gain - state->gain);
"""
AGC_LOGIC_NEW = """    if (target_gain < state->gain) {
        alpha = 0.25f;
    } else {
        const float gain_error_db =
            20.0f * log10f((target_gain + 1.0e-9f) /
                           (state->gain + 1.0e-9f));
        alpha = gain_error_db > 3.0f ? 0.05f : 0.015f;
    }
    state->gain += alpha * (target_gain - state->gain);
"""


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected exact source block once, found {count}")
    return text.replace(old, new, 1)


def apply_candidate(root: Path, candidate: str) -> Path:
    if candidate == "vad":
        path = root / VAD_PATH
        text = path.read_text(encoding="utf-8")
        text = replace_once(text, VAD_DEFINE_OLD, VAD_DEFINE_NEW, "vad defines")
        text = replace_once(text, VAD_LOGIC_OLD, VAD_LOGIC_NEW, "vad policy")
    elif candidate == "agc":
        path = root / AGC_PATH
        text = path.read_text(encoding="utf-8")
        text = replace_once(text, AGC_LOGIC_OLD, AGC_LOGIC_NEW, "agc release")
    else:
        raise ValueError(f"unsupported candidate: {candidate}")
    path.write_text(text, encoding="utf-8")
    return path


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-stage-source-patch-") as tmp:
        root = Path(tmp)
        (root / VAD_PATH.parent).mkdir(parents=True)
        (root / AGC_PATH.parent).mkdir(parents=True, exist_ok=True)
        (root / VAD_PATH).write_text(
            "prefix\n" + VAD_DEFINE_OLD + "middle\n" + VAD_LOGIC_OLD + "suffix\n",
            encoding="utf-8",
        )
        (root / AGC_PATH).write_text(
            "prefix\n" + AGC_LOGIC_OLD + "suffix\n", encoding="utf-8"
        )
        vad = apply_candidate(root, "vad").read_text(encoding="utf-8")
        assert VAD_DEFINE_NEW in vad and VAD_LOGIC_NEW in vad
        agc = apply_candidate(root, "agc").read_text(encoding="utf-8")
        assert AGC_LOGIC_NEW in agc
        try:
            apply_candidate(root, "agc")
        except ValueError as exc:
            assert "expected exact source block once" in str(exc)
        else:
            raise AssertionError("re-applying candidate did not fail closed")
    print("stage source candidate patch self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--candidate", choices=("vad", "agc"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.candidate is None:
        parser.error("--candidate is required")
    path = apply_candidate(args.root.resolve(), args.candidate)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
