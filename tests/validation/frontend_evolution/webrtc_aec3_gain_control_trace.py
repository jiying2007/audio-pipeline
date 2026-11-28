#!/usr/bin/env python3
"""Strict raw binary32 readback of the frozen gain-control arms; no DSP."""
from __future__ import annotations

import json
import math
import struct

from contracts import require
import webrtc_aec3_gain_control_source as gain
import webrtc_aec3_selection_source as selection

UNITY = 0x3f800000
CNG_FIELDS = ("cng_low_re", "cng_low_im", "cng_high_re", "cng_high_im")
UPSTREAM_FIELDS = ("residual_power", "unbounded_residual_power", "nearend_spectrum",
                   "echo_spectrum", "cng_noise_spectrum", "selected_input_re", "selected_input_im")
LOW_FIELDS = ("estimated_low_bits", "applied_low_bits")
HIGH_FIELDS = ("estimated_high_bits", "applied_high_bits")
FIELDS = {"kind", "block_index", "support", "forced", *CNG_FIELDS, *UPSTREAM_FIELDS,
          *LOW_FIELDS, *HIGH_FIELDS}
MUTABLE = {"forced", "applied_low_bits", "applied_high_bits"}


def binary32(bits, unit_interval=False):
    require(type(bits) is int and 0 <= bits <= 0xffffffff, "invalid binary32 word")
    value = struct.unpack("<f", struct.pack("<I", bits))[0]
    require(math.isfinite(value) and (not unit_interval or 0 <= value <= 1),
            "nonfinite/out-of-domain binary32 word")
    return value


def validate_row(row, index, mode):
    require(mode in gain.MODES and type(index) is int and 0 <= index < 4000, "gain trace mode/index")
    require(type(row) is dict and set(row) == FIELDS and row["kind"] == gain.TRACE_KIND,
            "gain trace fields differ")
    require(type(row["block_index"]) is int and row["block_index"] == index,
            "gain block missing, reordered, duplicate or reset")
    support = gain.SUPPORT[0] <= index < gain.SUPPORT[1]
    forced = mode == "gain-unity" and support
    require(type(row["support"]) is bool and row["support"] == support and
            type(row["forced"]) is bool and row["forced"] == forced, "gain support/force drift")
    for field in CNG_FIELDS + UPSTREAM_FIELDS + LOW_FIELDS:
        words = row[field]
        require(type(words) is list and len(words) == 65, "trace vector cardinality: " + field)
        for word in words:
            binary32(word, field in LOW_FIELDS)
    for field in HIGH_FIELDS:
        binary32(row[field], True)
    expected_low = [UNITY] * 65 if forced else row["estimated_low_bits"]
    expected_high = UNITY if forced else row["estimated_high_bits"]
    require(row["applied_low_bits"] == expected_low and row["applied_high_bits"] == expected_high,
            "applied gain is not exact support-local unity substitution")
    return row


def distinct(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate gain trace field")
        result[key] = value
    return result


def parse_trace(data: bytes, samples: int, mode: str) -> dict:
    require(type(data) is bytes and len(data) <= 64 * 1024 * 1024 and
            type(samples) is int and samples in (128000, 256000) and mode in gain.MODES,
            "gain trace input scope")
    rows, old_lines = [], []
    for line in data.splitlines(keepends=True):
        if gain.TRACE_KIND.encode() in line:
            require(len(line) <= 20000 and line.endswith(b"\n"), "gain trace line bound/framing")
            row = json.loads(line, object_pairs_hook=distinct)
            rows.append(validate_row(row, len(rows), mode))
        elif selection.TRACE_KIND.encode() in line:
            old_lines.append(line)
    require(len(rows) == samples // 64, "gain trace block coverage")
    prior = selection.parse_trace(b"".join(old_lines), samples, "observe")
    for row, old in zip(rows, prior):
        require(row["estimated_low_bits"] == old["gain_bits"] and
                row["estimated_high_bits"] == old["high_bands_gain_bits"],
                "gain trace disagrees with original estimator witness")
    return {"gain": rows, "selector": prior}


def compare_arms(neutral, intervention):
    require(neutral["selector"] == intervention["selector"], "selector or estimated gain changed")
    a, b = neutral["gain"], intervention["gain"]
    require(len(a) == len(b) and len(a) in (2000, 4000), "paired gain block cardinality")
    nonunity = 0
    for i, (left, right) in enumerate(zip(a, b)):
        validate_row(left, i, "gain-observe")
        validate_row(right, i, "gain-unity")
        require(all(left[key] == right[key] for key in FIELDS - MUTABLE),
                "paired estimated gain/CNG/upstream witness differs at block " + str(i))
        if right["forced"] and (left["estimated_low_bits"] != [UNITY] * 65 or
                                left["estimated_high_bits"] != UNITY):
            nonunity += 1
    require(sum(r["forced"] for r in b) == gain.SUPPORT[1] - gain.SUPPORT[0],
            "force coverage drift")
    return {"blocks": len(a), "forced_blocks": 451, "nonunity_support_blocks": nonunity,
            "upstream_and_cng_words_equal": True,
            "ola_history_equality_claimed": False, "promotion_allowed": False}
