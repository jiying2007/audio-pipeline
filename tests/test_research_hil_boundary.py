#!/usr/bin/env python3
"""Research HIL cannot regain product publication or automatic authority.

Offline, source-only, Python 3.8+: does not run hardware or create evidence.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def require_research_hil(text):
    if "  schedule:" in text or "  repository_dispatch:" in text:
        raise ValueError("automatic or release HIL event reintroduced")
    if "hil-post-release" in text:
        raise ValueError("post-release HIL listener reintroduced")
    if "  workflow_dispatch:" not in text or "source_sha:" not in text:
        raise ValueError("no explicit SHA-bound research experiment")
    if "ref: ${{ inputs.source_sha }}" not in text:
        raise ValueError("HIL source not bound to manual input")
    if "HIL_RESEARCH_MANUAL_ONLY" not in text:
        raise ValueError("manual-only guard missing")
    if "HIL_REQUIRED_BUT_DISABLED" not in text or "HIL_ENABLED" not in text:
        raise ValueError("fail-visible hardware boundary missing")
    if "runs-on: [self-hosted, linux, audio-target]" not in text:
        raise ValueError("real target runner required")
    if "certification-72h" in text or "release-8h" in text:
        raise ValueError("commercial HIL tier reintroduced")
    for tier in ("accelerated-pr", "research-1h", "research-8h",
                 "research-24h", "research-72h"):
        if tier not in text:
            raise ValueError("missing research duration: " + tier)
    if "seconds=259200" not in text:
        raise ValueError("optional 72-hour scientific measurement was weakened")


class ResearchHILBoundaryTests(unittest.TestCase):
    def test_actual_workflow_is_manual_source_bound(self):
        text = (ROOT / ".github/workflows/hil-soak.yml").read_text(encoding="utf-8")
        require_research_hil(text)

    def test_rejected_reintroduction_of_commercial_triggers(self):
        source = (ROOT / ".github/workflows/hil-soak.yml").read_text(encoding="utf-8")
        for mutation in (
            source.replace("  workflow_dispatch:",
                           "  schedule:\n    - cron: '0 0 * * *'\n  workflow_dispatch:", 1),
            source.replace("  workflow_dispatch:",
                           "  repository_dispatch:\n    types: [hil-post-release]\n  workflow_dispatch:", 1),
            source.replace("research-72h", "certification-72h"),
            source.replace("HIL_REQUIRED_BUT_DISABLED", "HIL_DISABLED"),
            source.replace("ref: ${{ inputs.source_sha }}", "ref: ${{ github.sha }}"),
        ):
            with self.subTest(mutation=mutation[:96]):
                with self.assertRaises(ValueError):
                    require_research_hil(mutation)

    def test_historical_e001_is_not_laboratory_admission(self):
        e001 = (ROOT / ".github/program/e001_hardware_readiness.py").read_text(encoding="utf-8")
        self.assertIn("72h remains a voluntary scientific duration", e001)
        self.assertIn("historical E001 soak duration evidence drift", e001)
        maintenance = (ROOT / ".github/program/maintenance_workflow_contract.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("research HIL must not have an autonomous schedule", maintenance)
        self.assertIn("manual HIL disabled must fail visibly", maintenance)
        self.assertNotIn("HIL_SOAK_WORKFLOW: ('43", maintenance)
        docs = (ROOT / "hil/README.md").read_text(encoding="utf-8")
        self.assertIn("HIL_ENABLED=true", docs)
        self.assertIn("fails visibly", docs)


if __name__ == "__main__":
    unittest.main()
