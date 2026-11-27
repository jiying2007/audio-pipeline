#!/usr/bin/env python3
"""Exercise R11 dispatch while preserving the full R10 source-only selectors."""
import hashlib
import json
from pathlib import Path
import unittest

from test_fe09_runtime_2365_routes import selected

ROOT = Path(__file__).resolve().parents[3]
REL = "tests/validation/frontend_evolution/"
SNAPSHOT = "docs/research/frontend-evolution-v1/VALIDATION_2366_SOURCE_R11_20261128/ROUTE_SNAPSHOT.json"
SNAPSHOT_SHA256 = "32828806c085b3f49c94158bfa8480942e2fb3b23a304f3d45433fd992d4f318"


def region(text, revision, name):
    begin = "# " + revision + "_SELECTION_" + name + "_BEGIN"
    end = "# " + revision + "_SELECTION_" + name + "_END"
    if text.count(begin) != 1 or text.count(end) != 1:
        raise AssertionError("source dispatcher marker identity")
    return text.split(begin, 1)[1].split(end, 1)[0]


class Validation2366Routes(unittest.TestCase):
    def test_complete_r10_regions_and_unknown_version_rejection_are_preserved(self):
        raw = (ROOT / SNAPSHOT).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SNAPSHOT_SHA256)
        snapshot = json.loads(raw)
        self.assertEqual(set(snapshot), {"B3", "F0", "F1_A3"})
        for name, row in snapshot.items():
            body = region((ROOT / row["path"]).read_text(), "R10", name)
            self.assertEqual(body, row["body"])
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), row["sha256"])
            variable = "source_version" if name == "F1_A3" else "version"
            outputs = ("f1_source",) if name == "F1_A3" else ("script",)
            self.assertEqual(selected(body, variable, "2.3.66", outputs).returncode, 2)

    def test_full_b3_f0_r11_dispatchers(self):
        text = (ROOT / ".github/workflows/quality.yml").read_text()
        versions = [
            ("2.3.56", "", "original-v1"),
            ("2.3.57", "_r2", "forward-r2"),
            ("2.3.58", "_r2", "forward-r2"),
            ("2.3.59", "_r3", "forward-r3"),
            ("2.3.60", "_r4", "forward-r4"),
            ("2.3.61", "_r5_path_r1", "forward-r5-path-r1"),
            ("2.3.62", "_r6", "forward-r6-dualmic-v1"),
            ("2.3.63", "_r7", "forward-r7-dualmic-v1"),
            ("2.3.64", "_r9", "forward-r9-dualmic-v1"),
            ("2.3.65", "_r10", "forward-r10-runtime-v1"),
            ("2.3.66", "_r11", "forward-r11-validation-v1"),
        ]
        for tag, prefix in (("B3", "fe09_b3_f0_deadline"),
                            ("F0", "fe09_t3s3_f0_call_resource")):
            body = region(text, "R11", tag)
            for version, infix, kind in versions:
                if tag == "B3" and version == "2.3.56":
                    infix, kind = "_r1", "deadline-r1"
                with self.subTest(tag=tag, version=version):
                    result = selected(body, "version", version, ("script", "source_kind"))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines(),
                                     [REL + prefix + infix + "_qualification.py", kind])
            for version in ("2.3.67", "2.3.65-rc", "2.3.66-rc", "3.0.0", "unknown", ""):
                with self.subTest(tag=tag, unknown=version):
                    self.assertEqual(selected(body, "version", version, ("script",)).returncode, 2)
        for step in ("fe09_b3_f0", "fe09_t3s3_f0"):
            self.assertIn("steps." + step + ".outputs.source_kind == 'forward-r11-validation-v1'", text)
        self.assertEqual(text.count("forward-r11-validation-v1-${{ github.run_id }}-attempt-${{ github.run_attempt }}"), 2)

    def test_full_f1_a3_r11_dispatcher(self):
        text = (ROOT / ".github/scripts/verify-docs-gate.sh").read_text()
        body = region(text, "R11", "F1_A3")
        versions = [
            ("2.3.56", "r2", "r2"), ("2.3.57", "r2", "r2"),
            ("2.3.58", "r2", "r2"), ("2.3.59", "r2", "r2"),
            ("2.3.60", "r2", "r2"), ("2.3.61", "r2", "r2"),
            ("2.3.62", "r3", "r3"), ("2.3.63", "r4", "r4"),
            ("2.3.64", "r6", "r5"), ("2.3.65", "r7", "r6"),
            ("2.3.66", "r8", "r7"),
        ]
        for version, f1, a3 in versions:
            with self.subTest(version=version):
                result = selected(body, "source_version", version,
                                  ("f1_source", "f1_build", "a3_static", "f1_output", "a3_output"))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), [
                    REL + "fe09_f1_" + f1 + "_source_bridge.py",
                    REL + "fe09_f1_" + f1 + "_build.py",
                    REL + "fe09_a3_" + a3 + "_static_build.py",
                    "f1-" + f1 + "-t1", "a3-" + a3 + "-t1",
                ])
        for version in ("2.3.67", "2.3.65-rc", "2.3.66-rc", "3.0.0", "unknown", ""):
            self.assertEqual(selected(body, "source_version", version, ("f1_source",)).returncode, 2)
        self.assertIn("python3 " + REL + "test_fe09_r11_source_entries.py", text)
        self.assertIn("python3 " + REL + "test_fe09_r10_source_entries.py", text)
        self.assertIn("python3 " + REL + "fe09_b3_f0_r11_source_admission.py --check-current", text)


if __name__ == "__main__":
    unittest.main()
