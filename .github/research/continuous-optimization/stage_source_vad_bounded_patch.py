#!/usr/bin/env python3
"""Apply the frozen strong-origin bounded-hysteresis VAD source candidate."""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

HEADER = Path("src/enhance/ap_enhance.h")
VAD = Path("src/enhance/ap_vad.c")

HEADER_OLD = """typedef struct ap_vad_state {
    float noise_rms;
    uint32_t hangover;
} ap_vad_state_t;
"""
HEADER_NEW = """typedef struct ap_vad_state {
    float noise_rms;
    uint32_t hangover;
    uint32_t strong_origin_hysteresis_budget;
} ap_vad_state_t;
"""

DEFINES_OLD = """#define AP_VAD_STRONG_REFRESH_THRESHOLD 0.50f
#define AP_VAD_STRONG_HOLD_FRAMES 8u
#define AP_VAD_WEAK_HOLD_FRAMES 6u
"""
DEFINES_NEW = """#define AP_VAD_STRONG_REFRESH_THRESHOLD 0.50f
#define AP_VAD_STRONG_HOLD_FRAMES 8u
#define AP_VAD_WEAK_HOLD_FRAMES 6u
#define AP_VAD_STRONG_ORIGIN_HYSTERESIS_MARGIN 0.05f
#define AP_VAD_STRONG_ORIGIN_HYSTERESIS_BUDGET_FRAMES 2u
"""

DECL_OLD = """    float rms, ratio_db, crest_db, prob;
    float decision_threshold;
    int upstream_speech;
"""
DECL_NEW = """    float rms, ratio_db, crest_db, prob;
    float decision_threshold;
    float release_threshold;
    int upstream_speech;
"""

POLICY_OLD = """    decision_threshold = use_upstream_probability ?
                         AP_VAD_NS_DECISION_THRESHOLD :
                         AP_VAD_LOCAL_DECISION_THRESHOLD;
    if (prob >= AP_VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = AP_VAD_STRONG_HOLD_FRAMES;
    } else if (prob > decision_threshold) {
        if (state->hangover < AP_VAD_WEAK_HOLD_FRAMES)
            state->hangover = AP_VAD_WEAK_HOLD_FRAMES;
    } else if (state->hangover) {
        state->hangover--;
    }
"""
POLICY_NEW = """    decision_threshold = use_upstream_probability ?
                         AP_VAD_NS_DECISION_THRESHOLD :
                         AP_VAD_LOCAL_DECISION_THRESHOLD;
    release_threshold = decision_threshold -
                        AP_VAD_STRONG_ORIGIN_HYSTERESIS_MARGIN;
    if (prob >= AP_VAD_STRONG_REFRESH_THRESHOLD) {
        state->hangover = AP_VAD_STRONG_HOLD_FRAMES;
        state->strong_origin_hysteresis_budget =
            AP_VAD_STRONG_ORIGIN_HYSTERESIS_BUDGET_FRAMES;
    } else if (prob > decision_threshold) {
        if (state->hangover < AP_VAD_WEAK_HOLD_FRAMES)
            state->hangover = AP_VAD_WEAK_HOLD_FRAMES;
    } else if (state->hangover &&
               state->strong_origin_hysteresis_budget > 0u &&
               prob > release_threshold) {
        if (state->hangover < 2u)
            state->hangover = 2u;
        state->strong_origin_hysteresis_budget--;
    } else if (state->hangover) {
        state->hangover--;
    }
    if (state->hangover == 0u)
        state->strong_origin_hysteresis_budget = 0u;
"""


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected exact source block once, found {count}")
    return text.replace(old, new, 1)


def apply(root: Path) -> list[Path]:
    header = root / HEADER
    vad = root / VAD

    h = header.read_text(encoding="utf-8")
    h = replace_once(h, HEADER_OLD, HEADER_NEW, "VAD state")
    header.write_text(h, encoding="utf-8")

    text = vad.read_text(encoding="utf-8")
    text = replace_once(text, DEFINES_OLD, DEFINES_NEW, "VAD defines")
    text = replace_once(text, DECL_OLD, DECL_NEW, "VAD declarations")
    text = replace_once(text, POLICY_OLD, POLICY_NEW, "VAD policy")
    vad.write_text(text, encoding="utf-8")
    return [header, vad]


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-vad-bounded-source-") as tmp:
        root = Path(tmp)
        (root / HEADER.parent).mkdir(parents=True)
        (root / HEADER).write_text("prefix\n" + HEADER_OLD + "suffix\n", encoding="utf-8")
        (root / VAD).write_text(
            "prefix\n" + DEFINES_OLD + "middle\n" + DECL_OLD +
            "middle2\n" + POLICY_OLD + "suffix\n",
            encoding="utf-8",
        )
        apply(root)
        assert HEADER_NEW in (root / HEADER).read_text(encoding="utf-8")
        out = (root / VAD).read_text(encoding="utf-8")
        assert DEFINES_NEW in out and DECL_NEW in out and POLICY_NEW in out
        try:
            apply(root)
        except ValueError:
            pass
        else:
            raise AssertionError("re-applying exact VAD candidate did not fail closed")
    print("VAD bounded-hysteresis source patch self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    paths = apply(args.root.resolve())
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
