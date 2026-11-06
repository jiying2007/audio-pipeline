#!/usr/bin/env python3
"""Canonical source-bound ASR text and KWS event metrics.

This module neither invokes a model nor substitutes for acoustic evaluation.
Missing temporal labels/exposure produce null, never invented zero-error rates.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata

NORMALIZATION = "NFC-strip-whitespace-v1"
MAX_TEXT_UNITS = 4096
MAX_EVENTS = 10000


def require(value, message):
    if not value:
        raise ValueError(message)


def integer(value, name, minimum=0, maximum=None):
    require(type(value) is int and value >= minimum
            and (maximum is None or value <= maximum), "invalid " + name)
    return value


def hexdigest(value, name):
    require(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None,
            "invalid " + name)
    return value


def identifier(value, name):
    require(type(value) is str and 0 < len(value) <= 160 and value.strip() == value,
            "invalid " + name)
    return value


def normalize_text(text):
    require(type(text) is str and len(text) <= 65536, "invalid transcript text")
    # Punctuation/case/numerals and simplified/traditional characters are not
    # rewritten. This exact, deliberately small policy is part of the lock.
    return "".join(c for c in unicodedata.normalize("NFC", text) if not c.isspace())


def manifest_digest(manifest):
    return hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def edit_counts(reference, hypothesis):
    """Levenshtein counts; equal-cost alternatives prefer S, then D, then I."""
    require(isinstance(reference, (str, list, tuple)) and isinstance(hypothesis, (str, list, tuple)),
            "edit operands must be token sequences")
    require(len(reference) <= MAX_TEXT_UNITS and len(hypothesis) <= MAX_TEXT_UNITS,
            "text token bound exceeded")
    require(all(type(x) is str for x in reference) and all(type(x) is str for x in hypothesis),
            "edit tokens must be strings")
    # (distance, substitutions, deletions, insertions); memory is O(hypothesis).
    previous = [(j, 0, 0, j) for j in range(len(hypothesis) + 1)]
    for i, ref in enumerate(reference, 1):
        current = [(i, 0, i, 0)]
        for j, hyp in enumerate(hypothesis, 1):
            if ref == hyp:
                current.append(previous[j - 1])
                continue
            a, b, c = previous[j - 1], previous[j], current[j - 1]
            alternatives = [(a[0] + 1, a[1] + 1, a[2], a[3]),
                            (b[0] + 1, b[1], b[2] + 1, b[3]),
                            (c[0] + 1, c[1], c[2], c[3] + 1)]
            current.append(min(alternatives, key=lambda row: row[0]))
        previous = current
    distance, substitutions, deletions, insertions = previous[-1]
    return {"substitutions": substitutions, "deletions": deletions, "insertions": insertions,
            "distance": distance, "reference_units": len(reference), "hypothesis_units": len(hypothesis),
            "error_rate": distance / len(reference) if reference else None}


def score_transcript(reference_text, hypothesis_text, reference_words=None):
    reference, hypothesis = normalize_text(reference_text), normalize_text(hypothesis_text)
    cer = edit_counts(reference, hypothesis)
    wer = None
    if reference_words is not None:
        require(type(reference_words) is list and all(type(w) is str and w
                and w == unicodedata.normalize("NFC", w) and not any(c.isspace() for c in w)
                for w in reference_words), "invalid fixed reference word boundaries")
        require("".join(reference_words) == reference, "reference words do not reproduce reference text")
        words = unicodedata.normalize("NFC", hypothesis_text).split()
        wer = edit_counts(reference_words, words)
    return {"normalization": NORMALIZATION, "normalized_reference": reference,
            "normalized_hypothesis": hypothesis, "cer": cer, "wer": wer,
            "wer_tokenization": "NFC-whitespace-fixed-reference-v1" if reference_words is not None else None}


def pool_edit_counts(rows):
    """Sum edit/reference counts across presentations, never average rates."""
    require(type(rows) is list and rows, "nonempty edit count list required")
    names = ("substitutions", "deletions", "insertions", "distance", "reference_units", "hypothesis_units")
    totals = {name: 0 for name in names}
    for row in rows:
        require(type(row) is dict, "invalid edit count row")
        for name in names:
            totals[name] += integer(row.get(name), "edit " + name)
        require(row["distance"] == row["substitutions"] + row["deletions"] + row["insertions"],
                "inconsistent edit distance counts")
    totals["error_rate"] = totals["distance"] / totals["reference_units"] if totals["reference_units"] else None
    totals["presentations"] = len(rows)
    return totals


def _checked_events(events, maximum):
    require(type(events) is list and len(events) <= MAX_EVENTS, "invalid KWS events")
    seen, previous = set(), -1
    for event in events:
        require(type(event) is dict, "invalid KWS event object")
        key = identifier(event.get("event_id"), "KWS event id")
        require(key not in seen, "duplicate KWS event id")
        seen.add(key)
        identifier(event.get("keyword"), "KWS event keyword")
        when = integer(event.get("emitted_at_sample"), "KWS emission time", maximum=maximum)
        require(when >= previous, "KWS events must be in emission order")
        previous = when
        if "confidence" in event:
            value = event["confidence"]
            require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
                    "invalid KWS confidence")
    return events


def score_events(events, sample_rate_hz, samples, annotation=None, max_emitted_samples=None):
    rate = integer(sample_rate_hz, "sample rate", 1, 384000)
    count = integer(samples, "audio samples", 0, 384000 * 86400)
    maximum = count if max_emitted_samples is None else integer(max_emitted_samples, "maximum emission time", count)
    events = _checked_events(events, maximum)
    empty = {"emitted_events": len(events), "positive_events": None, "matched_events": None,
             "missed_events": None, "unmatched_events": None, "duplicate_target_triggers": None,
             "negative_false_alarms": None, "negative_exposure_samples": None,
             "negative_exposure_hours": None, "far_per_hour": None,
             "far_zero_event_one_sided_95_upper_per_hour": None, "frr": None,
             "latency_ms": None, "matches": None, "unscored_event_ids": None}
    if annotation is None:
        return {"annotation_status": "UNAVAILABLE", **empty}
    require(type(annotation) is dict, "invalid KWS annotation")
    positives = annotation.get("positive_events")
    negatives = annotation.get("negative_intervals")
    require(type(positives) is list and len(positives) <= MAX_EVENTS, "invalid positive event labels")
    require(type(negatives) is list and len(negatives) <= MAX_EVENTS, "invalid negative intervals")
    slack = integer(annotation.get("max_latency_samples"), "fixed KWS latency allowance", 0, maximum)
    seen, windows, last = set(), [], -1
    for row in positives:
        require(type(row) is dict, "invalid positive label")
        key = identifier(row.get("event_id"), "positive event id")
        require(key not in seen, "duplicate positive event id")
        seen.add(key)
        identifier(row.get("keyword"), "positive keyword")
        start = integer(row.get("start_sample"), "positive start", 0, count)
        end = integer(row.get("end_sample"), "positive end", start + 1, count)
        deadline = end + slack
        require(deadline <= maximum and start > last, "ambiguous/unsorted positive matching windows")
        last = deadline
        windows.append((start, deadline, row))
    last, exposure = -1, 0
    for interval in negatives:
        require(type(interval) is list and len(interval) == 2, "invalid negative interval")
        start = integer(interval[0], "negative start", 0, count)
        end = integer(interval[1], "negative end", start + 1, count)
        require(start >= last, "overlapping/unsorted negative intervals")
        require(all(end <= lo or start > hi for lo, hi, _ in windows),
                "negative exposure overlaps positive matching window")
        last, exposure = end, exposure + end - start
    matched, matches, unmatched, unscored = set(), [], [], []
    negative_false_alarms, duplicates = 0, 0
    for event in events:
        when = event["emitted_at_sample"]
        compatible = [row for lo, hi, row in windows if lo <= when <= hi and row["keyword"] == event["keyword"]]
        chosen = next((row for row in compatible if row["event_id"] not in matched), None)
        if chosen is not None:
            matched.add(chosen["event_id"])
            matches.append({"prediction_event_id": event["event_id"], "reference_event_id": chosen["event_id"],
                            "latency_ms": (when - chosen["end_sample"]) * 1000.0 / rate})
        else:
            unmatched.append(event["event_id"])
            duplicates += bool(compatible)
            if any(start <= when < end for start, end in negatives):
                negative_false_alarms += 1
            elif not any(lo <= when <= hi for lo, hi, _ in windows):
                unscored.append(event["event_id"])
    hours = exposure / rate / 3600.0
    return {"annotation_status": "AVAILABLE", "emitted_events": len(events),
            "positive_events": len(positives), "matched_events": len(matches),
            "missed_events": len(positives) - len(matches), "unmatched_events": len(unmatched),
            "duplicate_target_triggers": duplicates, "negative_false_alarms": negative_false_alarms,
            "negative_exposure_samples": exposure, "negative_exposure_hours": hours,
            "far_per_hour": negative_false_alarms / hours if exposure else None,
            # This specific bound is only defined for the zero-count Poisson
            # observation. It is not an independence claim or a passing gate.
            "far_zero_event_one_sided_95_upper_per_hour": -math.log(0.05) / hours
            if exposure and negative_false_alarms == 0 else None,
            "frr": (len(positives) - len(matches)) / len(positives) if positives else None,
            "latency_ms": [item["latency_ms"] for item in matches] if matches else None,
            "matches": matches, "unscored_event_ids": unscored}


def evaluate(manifest, predictions):
    """Reject incomplete or substituted model results before computing scores."""
    require(type(manifest) is dict and type(predictions) is dict, "manifest/predictions must be objects")
    require(type(manifest.get("schema_version")) is int and manifest["schema_version"] == 1,
            "manifest schema version")
    require(type(predictions.get("schema_version")) is int and predictions["schema_version"] == 1,
            "prediction schema version")
    require(manifest.get("normalization") == NORMALIZATION, "normalization policy drift")
    bindings = manifest.get("model_bindings")
    require(type(bindings) is dict and set(bindings) == {"asr", "kws"}, "exact model bindings required")
    for kind, value in bindings.items():
        hexdigest(value, kind + " model/settings digest")
    require(predictions.get("model_bindings") == bindings, "model/settings identity mismatch")
    require(predictions.get("manifest_digest") == manifest_digest(manifest), "label/manifest identity mismatch")
    labels, outputs = manifest.get("cases"), predictions.get("cases")
    require(type(labels) is list and 0 < len(labels) <= 10000 and type(outputs) is list,
            "invalid downstream cases")
    label_keys, prediction_keys = [], []
    for case in labels:
        require(type(case) is dict, "invalid labeled case")
        label_keys.append(identifier(case.get("case_id"), "labeled case id"))
    for case in outputs:
        require(type(case) is dict, "invalid predicted case")
        prediction_keys.append(identifier(case.get("case_id"), "predicted case id"))
    require(len(label_keys) == len(set(label_keys)) and len(prediction_keys) == len(set(prediction_keys)),
            "duplicate downstream case id")
    require(set(label_keys) == set(prediction_keys), "missing/extra downstream predictions")
    by_id = dict(zip(prediction_keys, outputs))
    scored = []
    for case in labels:
        result = by_id[case["case_id"]]
        hexdigest(case.get("pcm_sha256"), "labeled PCM digest")
        require(result.get("pcm_sha256") == case["pcm_sha256"], "predicted PCM identity mismatch")
        for kind in ("asr", "kws"):
            require(type(result.get(kind)) is dict and result[kind].get("status") == "ok",
                    kind + " model did not successfully execute")
        scored.append({"case_id": case["case_id"], "pcm_sha256": case["pcm_sha256"],
                       "asr": score_transcript(case.get("reference_text"), result["asr"].get("text"),
                                               case.get("reference_words")),
                       "kws": score_events(result["kws"].get("events"), case.get("sample_rate_hz"),
                                           case.get("samples"), case.get("kws_annotation"),
                                           case.get("max_emitted_samples"))})
    word_rows = [case["asr"]["wer"] for case in scored if case["asr"]["wer"] is not None]
    pooled = {"cer": pool_edit_counts([case["asr"]["cer"] for case in scored]),
              "wer": pool_edit_counts(word_rows) if word_rows else None,
              "independence_claim": False,
              "scope": "count accounting over presented views, not independent speakers or utterances"}
    return {"schema_version": 1, "manifest_digest": manifest_digest(manifest),
            "model_bindings": bindings, "normalization": NORMALIZATION, "cases": scored,
            "pooled_view_accounting": pooled, "quality_decision": "DESCRIPTIVE_ONLY", "promotion_allowed": False}
