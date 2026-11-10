#!/usr/bin/env python3
"""Synthetic metadata negatives; no artifact or scientific result is fabricated."""
import copy
import unittest
import dualmic_zero_d3_source as source

class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.lock = source.frozen_lock()
        s = self.lock["artifact"]
        self.run = dict(id=self.lock["run_id"], head_sha=self.lock["source_revision"],
                        run_attempt=1, status="completed", conclusion="success")
        self.item = dict(id=s["artifact_id"], name=s["name"], size_in_bytes=s["zip_bytes"],
                         digest="sha256:" + s["sha256"], expired=False,
                         workflow_run=dict(id=self.lock["run_id"], head_sha=self.lock["source_revision"]))
    def test_exact(self):
        source.metadata(self.run, dict(total_count=1, artifacts=[self.item]), self.lock)
    def test_wrong_run_and_attempt(self):
        for key, value in (("id", 0), ("head_sha", "0"*40), ("run_attempt", True),
                           ("run_attempt", 2), ("status", "in_progress"), ("conclusion", "failure")):
            r = dict(self.run); r[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                source.metadata(r, dict(total_count=1, artifacts=[self.item]), self.lock)
    def test_wrong_artifact(self):
        for key, value in (("id", 0), ("name", "other"), ("size_in_bytes", 1),
                           ("digest", "sha256:"+"0"*64), ("expired", True),
                           ("workflow_run", dict(id=1, head_sha="0"*40))):
            i = copy.deepcopy(self.item); i[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                source.metadata(self.run, dict(total_count=1, artifacts=[i]), self.lock)
    def test_absent_duplicate_and_incomplete(self):
        for listing in (dict(total_count=0, artifacts=[]),
                        dict(total_count=2, artifacts=[self.item, self.item]),
                        dict(total_count=2, artifacts=[self.item]),
                        dict(total_count=101, artifacts=[]),
                        dict(total_count=True, artifacts=[self.item])):
            with self.subTest(listing=listing), self.assertRaises(ValueError):
                source.metadata(self.run, listing, self.lock)
if __name__ == "__main__":
    unittest.main(verbosity=2)
