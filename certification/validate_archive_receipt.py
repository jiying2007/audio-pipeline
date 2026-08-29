#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate(receipt: dict, bundle_hash: str) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version", "archive_id", "bundle_sha256", "stored_at",
        "retention_class", "immutable",
    }
    missing = sorted(required - receipt.keys())
    if missing:
        return ["receipt: missing " + ", ".join(missing)]
    if receipt["schema_version"] != 1:
        errors.append("schema_version: expected 1")
    if not str(receipt["archive_id"]).strip():
        errors.append("archive_id: must be non-empty")
    if not HEX64.fullmatch(str(receipt["bundle_sha256"])):
        errors.append("bundle_sha256: invalid")
    elif str(receipt["bundle_sha256"]).lower() != bundle_hash.lower():
        errors.append("bundle_sha256: does not match archived bundle")
    if receipt["retention_class"] != "product-lifecycle":
        errors.append("retention_class: must be product-lifecycle")
    if receipt["immutable"] is not True:
        errors.append("immutable: archive backend must assert immutable storage")
    if "T" not in str(receipt["stored_at"]):
        errors.append("stored_at: expected ISO-8601 date-time")
    return errors


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-archive-receipt-") as temporary:
        bundle = Path(temporary) / "bundle.tar.gz"
        bundle.write_bytes(b"evidence")
        good = {
            "schema_version": 1,
            "archive_id": "archive/test/1",
            "bundle_sha256": sha256(bundle),
            "stored_at": "2026-08-29T00:00:00Z",
            "retention_class": "product-lifecycle",
            "immutable": True,
        }
        assert not validate(good, sha256(bundle))
        bad = dict(good, immutable=False)
        assert validate(bad, sha256(bundle))
    print("archive receipt self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.receipt or not args.bundle:
        parser.error("--receipt and --bundle are required")
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    errors = validate(receipt, sha256(args.bundle))
    if errors:
        for error in errors:
            print(error)
        return 1
    print("archive receipt: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
