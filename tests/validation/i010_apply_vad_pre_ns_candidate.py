#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

RELATIVE_PATH = Path("src/core/ap_pipeline.c")
OLD = """#if AP_BUILD_STAGE_VAD
    if (AP_HAS_STAGE(pipeline, AP_STAGE_VAD)) {
        ap_vad_result_t vad_result;
        ap_vad_process(&pipeline->vad,
                       pipeline->processed,
                       pipeline->internal_frame,
                       ns_speech_probability,
                       AP_HAS_STAGE(pipeline, AP_STAGE_NS),
                       &vad_result);
"""
NEW = """#if AP_BUILD_STAGE_VAD
    if (AP_HAS_STAGE(pipeline, AP_STAGE_VAD)) {
        ap_vad_result_t vad_result;
        const float *vad_local_samples = pipeline->processed;
#if AP_BUILD_STAGE_NS
        if (AP_HAS_STAGE(pipeline, AP_STAGE_NS))
            vad_local_samples = pipeline->aec_out;
#endif
        ap_vad_process(&pipeline->vad,
                       vad_local_samples,
                       pipeline->internal_frame,
                       ns_speech_probability,
                       AP_HAS_STAGE(pipeline, AP_STAGE_NS),
                       &vad_result);
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply(root: Path, manifest: Path | None = None) -> dict:
    path = root / RELATIVE_PATH
    before = path.read_text(encoding="utf-8")
    if before.count(OLD) != 1:
        raise ValueError("candidate patch anchor must occur exactly once")
    if "vad_local_samples = pipeline->aec_out" in before:
        raise ValueError("candidate patch already present")
    after = before.replace(OLD, NEW, 1)
    path.write_text(after, encoding="utf-8")
    result = {
        "schema_version": 1,
        "candidate_id": "vad-pre-ns-local-observation-v1",
        "path": RELATIVE_PATH.as_posix(),
        "before_sha256": sha256_bytes(before.encode()),
        "after_sha256": sha256_bytes(after.encode()),
        "changed_lines_only": [
            "introduce vad_local_samples alias",
            "route NS-enabled local VAD samples to pipeline->aec_out",
            "preserve NS-disabled local VAD samples as pipeline->processed",
            "preserve ns_speech_probability and VAD thresholds",
        ],
    }
    if manifest is not None:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-i010-vad-pre-ns-patch-") as tmp:
        root = Path(tmp)
        path = root / RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text("prefix\n" + OLD + "suffix\n", encoding="utf-8")
        result = apply(root)
        text = path.read_text(encoding="utf-8")
        assert OLD not in text
        assert NEW in text
        assert result["before_sha256"] != result["after_sha256"]
        try:
            apply(root)
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate candidate patch application was accepted")
    print("I010 pre-NS VAD candidate patch self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.root is None:
        parser.error("--root is required")
    result = apply(args.root.resolve(), args.manifest.resolve() if args.manifest else None)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
