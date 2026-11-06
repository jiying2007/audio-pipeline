#!/usr/bin/env python3
"""Default research verification must never depend on shipping approval.

Runs offline under Python 3.8+; intentionally checks only active required
entrypoints. Historic standalone release/certification documents are not
source of truth for research eligibility and are retired separately.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def live_publication_violations(source):
    """Detect executable product-release authority in any active Actions workflow.

    Historical documentation and negative source checks remain intact.  This
    static contract does not execute a publisher, runner, or physical device.
    """
    header = source.split("\njobs:\n", 1)[0]
    issues = []
    for pattern, label in (
        (r"(?m)^  release:\s*$", "release event"),
        (r"(?m)^  repository_dispatch:\s*$", "repository-dispatch event"),
        (r"(?m)^    tags:\s*$", "tag push"),
        (r"(?m)^\s+workflows:\s*\[?\s*['\"]?Release\b", "release workflow-run"),
    ):
        if re.search(pattern, header):
            issues.append(label)
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for pattern, label in (
            (r"\bgh\s+release\s+(?:create|upload|download|view|edit|delete|publish)\b",
             "GitHub Release CLI"),
            (r"\bgh\s+api\b[^\n]*?/releases(?:/|\b)", "GitHub Release API"),
            (r"\b(?:python(?:3)?|bash|sh)\s+(?:-B\s+)?(?:certification/|"
             r"tools/(?:ap_certify|certification_provenance)\.py|"
             r"scripts/verify-shipping-toolchain\.sh)",
             "product certificate/toolchain execution"),
            (r"^(?:-\s*)?uses:\s*(?:softprops/action-gh-release|"
             r"actions/create-release|actions/upload-release-asset)(?:@|\b)",
             "GitHub Release publisher action"),
        ):
            if re.search(pattern, line):
                issues.append(label)
    return issues


class ResearchCIBoundaryTests(unittest.TestCase):
    def test_current_research_guides_do_not_restore_retired_approval(self):
        for name in ('docs/ARCHITECTURE.md', 'docs/AUDIO_QUALITY_EVALUATION.md', 'docs/EXTENDED_REAL_VALIDATION.zh-CN.md', 'docs/PERFORMANCE.md', 'docs/PLATFORM_SUPPORT.md', 'docs/PORTING.md', 'docs/SSC305_DELIVERY.md', 'docs/SSC305_DELIVERY.zh-CN.md', 'docs/TRUSTED_AUDIO_VALIDATION_BLIND_RUNNER.md', 'docs/TUNING.md'):
            with self.subTest(path=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                self.assertTrue("Current research scope" in text or "当前研究范围" in text)
                self.assertIn("RESEARCH_ONLY_EXECUTION.md", text)
        for name, required in (("CONTRIBUTING.md", "technical research only"),
                               ("CONTRIBUTING.zh-CN.md", "纯技术研究")):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(required, text)
            self.assertIn("validation/research-authority.json", text)
            self.assertNotIn("software-commercial-ready", text)
            self.assertNotIn("validation/authority.json", text)
        for name, retired in (("docs/PERFORMANCE.md", "The checked-in Cortex-A32 LOW shipping policy requires 72 hours"),
                              ("docs/PORTING.md", "Formal shipping acceptance uses schema-v4"),
                              ("docs/SSC305_DELIVERY.md", "Beginning with v2.3.55, Release downloads"),
                              ("docs/EXTENDED_REAL_VALIDATION.zh-CN.md", "EXTENDED_REAL_ENABLED=true")):
            self.assertNotIn(retired, (ROOT / name).read_text(encoding="utf-8"))

    def test_all_active_workflows_exclude_product_publication_commands(self):
        workflows = sorted((ROOT / ".github/workflows").glob("*.yml"))
        self.assertGreaterEqual(len(workflows), 60)
        for name in ("verify.yml", "nightly.yml", "audio-quality-gates.yml",
                     "lab-user-mode.yml", "hil-soak.yml"):
            self.assertTrue((ROOT / ".github/workflows" / name).is_file())
        for workflow in workflows:
            with self.subTest(workflow=workflow.name):
                source = workflow.read_text(encoding="utf-8")
                self.assertEqual(live_publication_violations(source), [],
                                 workflow.as_posix())

    def test_active_workflow_publisher_counterexamples_are_rejected(self):
        fixtures = (
            "on:\n  release:\n    types: [published]\njobs:\n",
            "on:\n  repository_dispatch:\n    types: [hil-post-release]\njobs:\n",
            "on:\n  push:\n    tags:\n      - 'v*'\njobs:\n",
            "on:\n  workflow_run:\n    workflows: [Release]\njobs:\n",
            "on:\n  workflow_dispatch:\njobs:\n  x:\n    steps:\n"
            "      - run: gh release create v1.0.0 old.bin\n",
            "on:\n  workflow_dispatch:\njobs:\n  x:\n    steps:\n"
            "      - run: gh api repos/example/repo/releases/tags/v1.0.0\n",
            "on:\n  workflow_dispatch:\njobs:\n  x:\n    steps:\n"
            "      - run: python3 certification/validate_record.py --self-test\n",
            "on:\n  workflow_dispatch:\njobs:\n  x:\n    steps:\n"
            "      - run: bash scripts/verify-shipping-toolchain.sh\n",
            "on:\n  workflow_dispatch:\njobs:\n  x:\n    steps:\n"
            "      - uses: softprops/action-gh-release@v2\n",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture[:55]):
                self.assertTrue(live_publication_violations(fixture),
                                "obsolete execution surface was admitted")
        # A negative check of a retired path must remain permissible.
        historical_guard = (
            "on:\n  pull_request:\njobs:\n  test:\n    steps:\n"
            "      - run: test ! -e .github/workflows/product-certification.yml\n"
            "      # historical gh release create is no longer allowed\n"
        )
        self.assertEqual(live_publication_violations(historical_guard), [])

    def test_acoustic_upgrade_has_research_policy_not_shipping_gate(self):
        source = (ROOT / "tools/acoustic_upgrade_decision.py").read_text(encoding="utf-8")
        self.assertIn('policy.get("scope") != "technical-research"', source)
        self.assertIn('"study_id": policy["study_id"]', source)
        self.assertNotIn('policy.get("shipping_approved") is not True', source)
        self.assertNotIn('"sku": policy.get("sku")', source)
        self.assertIn("obsolete product-policy fields are not research evidence", source)

    def test_governance_only_restores_protected_research_main(self):
        bootstrap = (ROOT / "scripts/bootstrap_github_governance.py").read_text(
            encoding="utf-8"
        )
        audit = (ROOT / "scripts/research_github_governance.py").read_text(
            encoding="utf-8"
        )
        workflow = (ROOT / ".github/workflows/repository-governance-bootstrap.yml").read_text(
            encoding="utf-8"
        )
        docs = (ROOT / "docs/REPOSITORY_GOVERNANCE.md").read_text(
            encoding="utf-8"
        )
        for text in (bootstrap, audit):
            self.assertIn("technical-research-main-only", text)
            self.assertNotIn("immutable-releases", text)
            self.assertNotIn("tag_ruleset()", text)
        self.assertIn("strict_required_status_checks_policy", bootstrap)
        self.assertIn("strict_required_status_checks_policy", audit)
        self.assertIn("delete_branch_on_merge", audit)
        self.assertIn("summary", audit)
        self.assertNotIn(".github/workflows/release.yml", workflow)
        self.assertNotIn("main/tag rulesets and immutable releases", workflow)
        self.assertIn("Restore main branch protection only", workflow)
        self.assertIn("Research repository governance", docs)
        for current in (
            ROOT / ".github/scripts/verify-docs-gate.sh",
            ROOT / ".github/workflows/nightly.yml",
            ROOT / ".github/workflows/repository-governance-bootstrap.yml",
        ):
            live = current.read_text(encoding="utf-8")
            self.assertIn("scripts/research_github_governance.py", live)
            self.assertNotIn("python3 scripts/github_governance.py", live)
        self.assertFalse((ROOT / "scripts/github_governance.py").exists())
        self.assertTrue((ROOT / "scripts/run_archived_governance_tests.py").is_file())
        self.assertNotIn("When a new project version reaches `main`", docs)

    def test_required_verify_has_no_product_release_authority(self):
        text = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        for obsolete in (
            "certification/", "product-certification.yml", "shipping_approved",
            "REPOSITORY_GOVERNANCE_TOKEN", "tools/ap_certify.py",
            "tools/certification_provenance.py",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, text)
        self.assertIn("name: Verify", text)
        self.assertIn("sh .github/scripts/verify-docs-gate.sh", text)
        self.assertIn("python3 scripts/ci_failure.py --self-test", text)
        self.assertIn("python3 tools/acoustic_upgrade_decision.py --self-test", text)

    def test_scheduled_research_nightly_has_no_product_certificate_execution(self):
        nightly = (ROOT / ".github/workflows/nightly.yml").read_text(encoding="utf-8")
        for obsolete in (
            "certification/validate_record.py",
            "certification/validate_archive_receipt.py",
            "tools/certification_provenance.py",
            "scripts/verify-shipping-toolchain.sh",
            "shipping_approved",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, nightly)
        for required in (
            "python3 validation/tools/authority.py --self-test",
            "python3 validation/tools/dataset_lock.py validate",
            "python3 validation/tools/run_validation.py --self-test",
            "python3 tools/hil_board.py --self-test",
        ):
            with self.subTest(required=required):
                self.assertIn(required, nightly)

    def test_no_active_commercial_publication_entrypoints(self):
        for legacy in (
            ".github/workflows/release.yml",
            ".github/workflows/post-release-qualification-summary.yml",
            ".github/workflows/product-certification.yml",
        ):
            with self.subTest(legacy=legacy):
                self.assertFalse((ROOT / legacy).exists(),
                                 "commercial publication workflow must be retired")

    def test_post_release_status_tool_is_retired_from_active_tree(self):
        retired = ROOT / "scripts/post_release_status.py"
        self.assertFalse(retired.exists(),
                         "historical post-release approval status is not active research")
        docs = (ROOT / "scripts/docs_consistency.py").read_text(encoding="utf-8")
        self.assertIn("retired post-release status tool reintroduced", docs)
        self.assertNotIn('"scripts/post_release_status.py",', docs)

    def test_doc_gate_keeps_source_science_and_excludes_release_approval(self):
        text = (ROOT / ".github/scripts/verify-docs-gate.sh").read_text(encoding="utf-8")
        self.assertIn("python3 tests/test_research_ci_boundary.py", text)
        for required in (
            "tests/validation/frontend_evolution/test_contracts.py",
            "scripts/ci_impact.py --self-test",
            "tests/validation/test_immutable_whitespace.py",
            "tests/validation/frontend_evolution/test_device_capture.py",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
        for release_only in (
            "scripts/prepare_release.py --self-test",
            "scripts/release_manifest.py --self-test",
            "scripts/post_release_status.py --self-test",
            ".github/program/test_product_soak_observed_duration.py",
        ):
            with self.subTest(release_only=release_only):
                self.assertNotIn(release_only, text)


    def test_quality_source_integrity_is_research_only(self):
        workflow = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tests/test_research_source.py", workflow)
        self.assertIn("sh scripts/verify-research-source.sh", workflow)
        self.assertNotIn("test_release_source.py", workflow)
        self.assertNotIn("verify-release-source.sh", workflow)
        self.assertFalse((ROOT / "scripts/verify-release-source.sh").exists())
        self.assertFalse((ROOT / "tests/test_release_source.py").exists())
        source = (ROOT / "scripts/verify-research-source.sh").read_text(encoding="utf-8")
        self.assertIn("git rev-parse --verify HEAD", source)
        self.assertIn("git diff --cached --quiet HEAD", source)
        self.assertNotIn("gh release", source)

    def test_fe09_s2a_readback_is_exact_attempt_id_bound(self):
        # v7 artifacts are immutable and name discovery may lag final upload.
        # The retry attempt must create a distinct artifact and consume the
        # exact ID returned by the successful upload, not a name lookup.
        workflow = (ROOT / ".github/workflows/quality.yml").read_text(
            encoding="utf-8"
        )
        block = workflow.split("  frontend-s3-t3s2a:", 1)[1].split(
            "\n  frontend-", 1
        )[0]
        self.assertIn("id: t3s2a_artifact", block)
        self.assertIn("github.run_attempt", block)
        self.assertIn("artifact-ids: ${{ steps.t3s2a_artifact.outputs.artifact-id }}", block)
        self.assertIn("fe09-t3s2a-readback", block)
        self.assertIn("SHA256SUMS", block)
        self.assertNotIn(
            "name: frontend-fe09-t3s2a-posix-spool-${{ github.run_id }}\n"
            "          path: fe09-t3s2a-readback", block
        )

    def test_orphaned_product_program_executables_are_retired(self):
        # These historic helpers only served deleted commercial Release / 72h
        # product approval contracts. Keep original source in immutable Git.
        old = (
            "existing_release_identity.py",
            "p002_candidate_zero_audit.py",
            "product_soak_observed_duration.py",
            "test_product_soak_observed_duration.py",
        )
        for name in old:
            with self.subTest(name=name):
                self.assertFalse((ROOT / ".github/program" / name).exists())
                for workflow in (ROOT / ".github/workflows").glob("*.yml"):
                    self.assertNotIn(
                        name, workflow.read_text(encoding="utf-8"),
                        "retired executable reintroduced to active research Actions"
                    )
        current = (ROOT / ".github/program/maintenance_workflow_contract.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("source-bound research maintenance state", current)
        self.assertNotIn("software-commercial-ready maintenance state", current)

    def test_archived_commercial_docs_do_not_gate_research(self):
        # Historical certification procedures are retrievable via Git/docs
        # navigation, but must not be a required file for current quality CI.
        source = (ROOT / "scripts/docs_consistency.py").read_text(encoding="utf-8")
        current = source.split("CURRENT_DOCS = (", 1)[1].split("\n)\n", 1)[0]
        for obsolete in (
            "docs/PRODUCT_ASSURANCE.md",
            "docs/PRODUCT_ASSURANCE.zh-CN.md",
            "certification/README.md",
            "certification/policies/README.md",
        ):
            with self.subTest(obsolete=obsolete):
                self.assertNotIn('"' + obsolete + '"', current)
        navigation_gate = source.split("    critical_tokens = {", 1)[1].split(
            "\n    for rel, tokens in critical_tokens.items():", 1
        )[0]
        self.assertNotIn('"PRODUCT_ASSURANCE.zh-CN.md"', navigation_gate)
        research = (ROOT / "docs/RESEARCH_ONLY_EXECUTION.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("archived commercial documentation", research)
        self.assertFalse((ROOT / ".github/workflows/product-certification.yml").exists())

    def test_agent_and_chinese_navigation_have_no_live_product_authority(self):
        documents = {
            "AGENTS.md": {
                "must": ("technical research only", "no mandatory product-certification path"),
                "forbid": ("The real product path remains", ">=72 h Product Certification",
                           "shipping algorithm change"),
            },
            "AGENTS.zh-CN.md": {
                "must": ("纯技术研究", "真机研究阶段"),
                "forbid": (">=72 h Product Certification", "release-bearing 变化走 governed Release",
                           "measurement change 与 shipping algorithm change"),
            },
            "docs/README.zh-CN.md": {
                "must": ("当前状态边界：纯技术研究", "RESEARCH_ONLY_EXECUTION.md"),
                "forbid": ("仓库已经达到 `software-commercial-ready`",
                           "中文文档负责**商用集成", "产品认证机器真相源"),
            },
            "docs/QUICKSTART.zh-CN.md": {
                "must": ("SSC305 类 ARM 研究构建配置", "RESEARCH_ONLY_EXECUTION.md",
                         "真实目标设备", "NOT_RUN", "BLOCKED", "ssc305-cortex-a32-low"),
                "forbid": ("SSC305 软件商用起始配置", "软件商用就绪",
                           "shipping-approved policy", "真实产品资格只能来自"),
            },
            "docs/DEVELOPMENT.zh-CN.md": {
                "must": ("**纯技术研究**", "RESEARCH_ONLY_EXECUTION.md",
                         "独立数据来源与许可", "exact-head"),
                "forbid": ("software-commercial-ready", "release-bearing 变化必须",
                           "关键中文商用入口必须同步"),
            },
        }
        for path, rules in documents.items():
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                for token in rules["must"]:
                    self.assertIn(token, text, (path, token))
                for token in rules["forbid"]:
                    self.assertNotIn(token, text, (path, token))


if __name__ == "__main__":
    unittest.main()
