#!/usr/bin/env python3
"""Repository-internal contract for public diagnostic event names.

The public numeric event enum is the source of truth.  apdiagnose.py keeps a
human-readable presentation map for APD header trigger context; this checker
fails closed if that map drifts from the public enum while preserving the
unknown-event fallback for forward/foreign numeric values.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from apdiagnose import EVENT_NAMES, recording_trigger_context


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HEADER = ROOT / "include/audio_pipeline/audio_diag.h"
AUTHORITY = "repository-internal-event-name-contract-only"
ENUM_RE = re.compile(
    r"typedef\s+enum\s+ap_event_kind\s*\{(?P<body>.*?)\}\s*ap_event_kind_t\s*;",
    re.DOTALL,
)
ENTRY_RE = re.compile(
    r"AP_EVENT_(?P<symbol>[A-Z0-9_]+)\s*=\s*"
    r"(?P<value>(?:0[xX][0-9A-Fa-f]+|[0-9]+)[uUlL]*)\s*"
)


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def parse_public_event_enum(path: Path) -> dict[int, str]:
    text = _strip_comments(path.read_text(encoding="utf-8"))
    match = ENUM_RE.search(text)
    if match is None:
        raise ValueError(f"{path}: ap_event_kind_t enum not found")

    events: dict[int, str] = {}
    names: set[str] = set()
    for raw_entry in match.group("body").split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        parsed = ENTRY_RE.fullmatch(entry)
        if parsed is None:
            raise ValueError(
                f"{path}: unsupported ap_event_kind_t entry {entry!r}; "
                "use an explicit integer literal or update the diagnostic parser"
            )
        value_text = re.sub(r"[uUlL]+$", "", parsed.group("value"))
        value = int(value_text, 0)
        name = parsed.group("symbol").lower()
        if value in events:
            raise ValueError(f"{path}: duplicate ap_event_kind_t value {value}")
        if name in names:
            raise ValueError(f"{path}: duplicate ap_event_kind_t name {name}")
        events[value] = name
        names.add(name)

    if not events:
        raise ValueError(f"{path}: ap_event_kind_t contains no events")
    return events


def evaluate_contract(
    public_events: dict[int, str],
    diagnostic_events: dict[int, str],
    header: Path,
) -> dict[str, Any]:
    public_values = set(public_events)
    diagnostic_values = set(diagnostic_events)
    missing = [
        {"event": value, "expected_name": public_events[value]}
        for value in sorted(public_values - diagnostic_values)
    ]
    extra = [
        {"event": value, "diagnostic_name": diagnostic_events[value]}
        for value in sorted(diagnostic_values - public_values)
    ]
    name_mismatches = [
        {
            "event": value,
            "expected_name": public_events[value],
            "diagnostic_name": diagnostic_events[value],
        }
        for value in sorted(public_values & diagnostic_values)
        if public_events[value] != diagnostic_events[value]
    ]

    context_mismatches: list[dict[str, Any]] = []
    for value in sorted(public_events):
        expected = public_events[value]
        context = recording_trigger_context(value)
        valid = (
            isinstance(context, dict)
            and context.get("event") == value
            and context.get("name") == expected
            and context.get("source") == "apd-header"
            and context.get("relation") == "recording-trigger-context-only"
            and context.get("causal_proof") is False
        )
        if not valid:
            context_mismatches.append(
                {"event": value, "expected_name": expected, "observed": context}
            )

    unknown_event = max(public_values | diagnostic_values) + 1000003
    while unknown_event in public_values or unknown_event in diagnostic_values:
        unknown_event += 1
    unknown_context = recording_trigger_context(unknown_event)
    unknown_expected_name = f"unknown_event_{unknown_event}"
    unknown_fallback_ok = (
        isinstance(unknown_context, dict)
        and unknown_context.get("event") == unknown_event
        and unknown_context.get("name") == unknown_expected_name
        and unknown_context.get("source") == "apd-header"
        and unknown_context.get("relation") == "recording-trigger-context-only"
        and unknown_context.get("causal_proof") is False
    )

    passed = not (
        missing
        or extra
        or name_mismatches
        or context_mismatches
        or not unknown_fallback_ok
    )
    return {
        "schema_version": 1,
        "authority": AUTHORITY,
        "status": "PASS" if passed else "FAIL",
        "public_header": str(header.relative_to(ROOT) if header.is_relative_to(ROOT) else header),
        "public_event_count": len(public_events),
        "diagnostic_event_count": len(diagnostic_events),
        "events": [
            {"event": value, "name": public_events[value]}
            for value in sorted(public_events)
        ],
        "missing_diagnostic_events": missing,
        "extra_diagnostic_events": extra,
        "name_mismatches": name_mismatches,
        "trigger_context_mismatches": context_mismatches,
        "unknown_event_fallback": {
            "event": unknown_event,
            "expected_name": unknown_expected_name,
            "observed_name": (
                unknown_context.get("name") if isinstance(unknown_context, dict) else None
            ),
            "checked": True,
            "pass": unknown_fallback_ok,
        },
        "claim_scope": (
            "repository-internal diagnostic presentation consistency only; "
            "does not change or qualify the public event enum, APD v1, runtime, or shipping behavior"
        ),
    }


def self_test(header: Path) -> None:
    public_events = parse_public_event_enum(header)
    good = evaluate_contract(public_events, dict(EVENT_NAMES), header)
    assert good["status"] == "PASS", good
    assert good["public_event_count"] == good["diagnostic_event_count"]
    assert good["unknown_event_fallback"]["pass"] is True

    mutated = dict(EVENT_NAMES)
    victim = min(public_events)
    mutated[victim] = public_events[victim] + "_intentional_drift"
    bad = evaluate_contract(public_events, mutated, header)
    assert bad["status"] == "FAIL", bad
    assert bad["name_mismatches"] == [
        {
            "event": victim,
            "expected_name": public_events[victim],
            "diagnostic_name": mutated[victim],
        }
    ]

    assert recording_trigger_context(0) is None
    print("repository diagnostic event-name contract self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--header", type=Path, default=DEFAULT_HEADER)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    try:
        if args.self_test:
            self_test(args.header)
            return 0
        result = evaluate_contract(
            parse_public_event_enum(args.header), dict(EVENT_NAMES), args.header
        )
    except (OSError, ValueError) as exc:
        print(f"event_contract: {exc}", file=__import__("sys").stderr)
        return 2

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
