#!/usr/bin/env python3
"""FE09 A3-R2-T2-S0: bounded metadata JSON syntax only; no source admission.

This standalone derivative must never import or execute archived A3 source.
Its syntax result is not a provider, external freeze or experiment authority.
"""
from __future__ import annotations

import json
import math
from typing import Any

DEFAULT_CAP = 131072
MAX_CAP = 1048576
NUMBER_TOKEN_CAP = 128
MAX_NESTING = 64
STATUS = "A3_R2_T2_S0_STRICT_METADATA_SYNTAX_ONLY_NO_ADMISSION"
DENIALS = (
    "provider_metadata_observed",
    "source_admission_granted",
    "external_freeze_verified",
    "formal_controls_qualified",
    "a3_target_executed",
    "a3_worker_executed",
    "rolling_33_49_qualified",
    "rss_measured",
    "public_sdk_qualified",
    "ssc305_hil_qualified",
    "shipping_authority",
)


class MetadataRejected(ValueError):
    """A bounded, non-sensitive reason code; never embed input payloads."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise MetadataRejected(reason)


def _pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in rows:
        need(name not in result, "A3_METADATA_DUPLICATE_KEY")
        result[name] = value
    return result


def _constant(_value: str) -> Any:
    raise MetadataRejected("A3_METADATA_NONFINITE_NUMBER")


def _int(token: str) -> int:
    need(len(token) <= NUMBER_TOKEN_CAP, "A3_METADATA_NUMBER_TOKEN_BOUND")
    return int(token)


def _finite_float(token: str) -> float:
    need(len(token) <= NUMBER_TOKEN_CAP, "A3_METADATA_NUMBER_TOKEN_BOUND")
    number = float(token)
    need(math.isfinite(number), "A3_METADATA_NONFINITE_NUMBER")
    mantissa = token.split("e", 1)[0].split("E", 1)[0]
    need(not (number == 0.0 and any("1" <= c <= "9" for c in mantissa)),
         "A3_METADATA_FLOAT_UNDERFLOW")
    return number


def _check_unicode_scalars(value: Any) -> None:
    # Iterative and independent of the runner's Python recursion limit.
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if type(item) is str:
            need(not any(0xD800 <= ord(c) <= 0xDFFF for c in item),
                 "A3_METADATA_UNPAIRED_SURROGATE")
        elif type(item) is dict:
            need(depth < MAX_NESTING, "A3_METADATA_NESTING_BOUND")
            for key, nested in item.items():
                need(type(key) is str, "A3_METADATA_KEY_NOT_STRING")
                pending.append((key, depth + 1))
                pending.append((nested, depth + 1))
        elif type(item) is list:
            need(depth < MAX_NESTING, "A3_METADATA_NESTING_BOUND")
            pending.extend((nested, depth + 1) for nested in item)
        else:
            need(item is None or type(item) in (bool, int, float),
                 "A3_METADATA_UNKNOWN_VALUE")


def parse_metadata_json(raw: bytes, *, cap: int = DEFAULT_CAP) -> Any:
    """Parse bytes with no I/O, execution, source trust or admission side effect.

    Duplicate keys (including escaped equivalents), special nonfinite values,
    float overflow, nonzero float underflow and lone surrogates are rejected.
    """
    need(type(raw) is bytes, "A3_METADATA_BYTES_REQUIRED")
    need(type(cap) is int and 0 < cap <= MAX_CAP, "A3_METADATA_INVALID_CAP")
    need(0 < len(raw) <= cap, "A3_METADATA_BODY_BOUND")
    try:
        decoded = raw.decode("utf-8", errors="strict")
        need(not decoded.startswith("\ufeff"), "A3_METADATA_UTF8_BOM")
        value = json.loads(decoded, object_pairs_hook=_pairs,
                           parse_constant=_constant, parse_int=_int,
                           parse_float=_finite_float)
    except (UnicodeError, json.JSONDecodeError, OverflowError,
            RecursionError) as exc:
        raise MetadataRejected("A3_METADATA_INVALID_JSON") from exc
    _check_unicode_scalars(value)
    return value


def authority_boundary() -> dict[str, Any]:
    """Nonpromotional read-only descriptor. Never a source admission receipt."""
    return {"schema_version": 1, "status": STATUS,
            "syntax_only": True, **{field: False for field in DENIALS}}
