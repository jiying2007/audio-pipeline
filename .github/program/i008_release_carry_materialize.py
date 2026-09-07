#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

BASE = "d36755720e2fd34e59abc51b215d42b78fb6d9a3"
VERIFIED_FIX = "03a3bd9a85bb15e1a783ed78f4d2efc0b4bb966a"
TARGET_VERSION = "2.3.13"
TARGET_TAG = "v2.3.13"


def show(ref: str, path: str) -> str:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], text=True)

cmake = show(BASE, "CMakeLists.txt")
old = "project(audio_pipeline VERSION 2.3.12 LANGUAGES C)"
new = f"project(audio_pipeline VERSION {TARGET_VERSION} LANGUAGES C)"
assert cmake.count(old) == 1
Path("CMakeLists.txt").write_text(cmake.replace(old, new))

changelog = show(BASE, "CHANGELOG.md")
assert changelog.startswith("# 2.3.12\n")
section = """# 2.3.13

- Repair the I008 resampler performance comparator so base and head are both configured with the explicit FAST backend, preventing the project default BANDLIMITED backend from being compared against FAST and producing a false 72%–90% improvement artifact.
- Fail the paired comparator closed unless every `AP_*` CMake cache entry is behavior-equivalent between base and head, excluding only `AP_BUILD_SOURCE_REVISION`; retain the existing seven-repetition/100000-frame, eight-path regression gate and its conjunctive >10% plus >0.05 us threshold.
- This maintenance release changes performance-measurement infrastructure only: realtime DSP, public API/ABI, algorithm defaults, acoustic gates and Product Qualification authority are unchanged. The previously exposed I008 comparator evidence remains engineering lineage, not independent acoustic confirmation.

"""
Path("CHANGELOG.md").write_text(section + changelog)

Path("scripts/compare-resampler-perf.sh").write_text(show(VERIFIED_FIX, "scripts/compare-resampler-perf.sh"))

contract = {
    "schema_version": 1,
    "iteration_id": "I008",
    "action_id": "resampler-perf-comparator-release-carry-v2.3.13",
    "state": "RELEASE_CARRY_REVIEW_REQUIRED",
    "lane": "engineering",
    "exact_base_sha": BASE,
    "target_version": TARGET_VERSION,
    "target_tag": TARGET_TAG,
    "tag_absent_at_authorization": True,
    "release_absent_at_authorization": True,
    "shipping_baseline_before_release": {
        "release": "v2.3.12",
        "source_sha": "d82cb6d2be76497d1d66dd16da00924411207046",
        "unchanged_until_release_verified": True,
    },
    "source_fix_lineage": {
        "pr": 122,
        "pr_closed": True,
        "pr_merged": False,
        "verified_fix_sha": VERIFIED_FIX,
        "dedicated_run_id": 34039351719,
        "artifact_id": 9991183617,
        "artifact_digest": "sha256:b6c82e12e6e27529861e95cc3c1c29751d88d7d2d22522595c188524d1884ebd",
        "internal_sha256s_verified": 2,
        "authority": "already-exposed-engineering-lineage-only",
        "may_be_independent_confirmation": False,
    },
    "root_cause": {
        "id": "resampler-perf-base-head-backend-asymmetry",
        "shipping_dsp_defect": False,
        "base_before_fix": "CMake default BANDLIMITED",
        "head_before_fix": "explicit FAST",
        "false_improvement_artifact_pct": "approximately -72% to -90%",
    },
    "frozen_change_scope": {
        "allowed_paths": [
            "scripts/compare-resampler-perf.sh",
            "CMakeLists.txt",
            "CHANGELOG.md",
            "docs/program/iterations/I008-release-carry-v2.3.13.json",
            ".github/workflows/i008-release-carry.yml",
        ],
        "shipping_dsp_source_change_allowed": False,
        "public_api_change_allowed": False,
        "program_baseline_change_allowed_before_release": False,
        "candidate_limit_consumed": 0,
        "confirmation_limit_consumed": 0,
        "threshold_tuning_allowed": False,
    },
    "required_fix": {
        "base_resampler_mode": "FAST",
        "head_resampler_mode": "FAST",
        "require_base_head_ap_cache_equivalence": True,
        "excluded_equivalence_key": "AP_BUILD_SOURCE_REVISION",
        "repetitions": 7,
        "frames": 100000,
        "paths": 8,
        "regression_gate": {
            "relative_regression_pct": 10.0,
            "absolute_regression_us": 0.05,
            "logic": "fail only when both are exceeded",
        },
    },
    "release_policy": {
        "semver_bump_required": True,
        "base_version": "2.3.12",
        "target_version": TARGET_VERSION,
        "changelog_top_must_match": TARGET_VERSION,
        "release_must_not_exist_before_merge": True,
        "program_shipping_baseline_migrates_only_after_release_exists_and_is_verified": True,
    },
    "post_merge_requirements": {
        "exact_main_verify_success": True,
        "release_workflow_must_create_new_release": True,
        "tag_peel_must_equal_release_source_sha": True,
        "immutable_release_required": True,
        "asset_count": 8,
        "checksummed_assets": 7,
        "manifest_payload_assets": 6,
        "product_qualification_inferred_from_hosted_or_dispatch_results": False,
    },
    "authority_boundary": {
        "release_created_before_merge": False,
        "shipping_baseline_changed_before_release": False,
        "software_candidate_promoted": False,
        "product_qualification": "DEFERRED_BY_SCOPE",
        "dut_hil": "DEFERRED_BY_SCOPE",
    },
}
contract_path = Path("docs/program/iterations/I008-release-carry-v2.3.13.json")
contract_path.parent.mkdir(parents=True, exist_ok=True)
contract_path.write_text(json.dumps(contract, indent=2) + "\n")

workflow = r'''name: I008 Release Carry v2.3.13

on:
  pull_request:
    paths:
      - 'scripts/compare-resampler-perf.sh'
      - 'CMakeLists.txt'
      - 'CHANGELOG.md'
      - 'docs/program/iterations/I008-release-carry-v2.3.13.json'
      - '.github/workflows/i008-release-carry.yml'

permissions:
  contents: read
  actions: read

jobs:
  release-carry:
    runs-on: ubuntu-24.04
    timeout-minutes: 25
    env:
      PROGRAM_BASE: d36755720e2fd34e59abc51b215d42b78fb6d9a3
      VERIFIED_FIX_SHA: 03a3bd9a85bb15e1a783ed78f4d2efc0b4bb966a
      LINEAGE_ARTIFACT_ID: 9991183617
      LINEAGE_ZIP_SHA256: b6c82e12e6e27529861e95cc3c1c29751d88d7d2d22522595c188524d1884ebd
      TARGET_VERSION: 2.3.13
      TARGET_TAG: v2.3.13
      HEAD_SHA: ${{ github.event.pull_request.head.sha }}
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
          persist-credentials: false

      - name: Enforce exact five-file release carry
        shell: bash
        run: |
          set -euo pipefail
          test "${{ github.event.pull_request.base.sha }}" = "$PROGRAM_BASE"
          test "$(git rev-parse HEAD)" = "$HEAD_SHA"
          changed="$(git diff --name-only "$PROGRAM_BASE"...HEAD | sort)"
          cat > /tmp/expected <<'EOF'
          .github/workflows/i008-release-carry.yml
          CHANGELOG.md
          CMakeLists.txt
          docs/program/iterations/I008-release-carry-v2.3.13.json
          scripts/compare-resampler-perf.sh
          EOF
          printf '%s\n' "$changed" > /tmp/actual
          diff -u /tmp/expected /tmp/actual
          git diff --check "$PROGRAM_BASE"...HEAD
          git diff --quiet "$PROGRAM_BASE"...HEAD -- src include docs/program/plan.json scripts/program.py
          test "$(sed -n 's/^project(audio_pipeline VERSION \([0-9][0-9.]*\).*/\1/p' CMakeLists.txt)" = "$TARGET_VERSION"
          test "$(sed -n '1s/^# //p' CHANGELOG.md)" = "$TARGET_VERSION"
          git show "$VERIFIED_FIX_SHA:scripts/compare-resampler-perf.sh" > /tmp/verified-comparator.sh
          cmp scripts/compare-resampler-perf.sh /tmp/verified-comparator.sh
          python3 -m json.tool docs/program/iterations/I008-release-carry-v2.3.13.json >/dev/null
          python3 scripts/program.py --self-test
          python3 scripts/program.py check >/dev/null

      - name: Validate frozen release-carry contract
        shell: bash
        run: |
          set -euo pipefail
          python3 - <<'PY'
          import json
          c=json.load(open('docs/program/iterations/I008-release-carry-v2.3.13.json'))
          assert c['schema_version']==1 and c['iteration_id']=='I008'
          assert c['state']=='RELEASE_CARRY_REVIEW_REQUIRED'
          assert c['exact_base_sha']=='d36755720e2fd34e59abc51b215d42b78fb6d9a3'
          assert c['target_version']=='2.3.13' and c['target_tag']=='v2.3.13'
          assert c['tag_absent_at_authorization'] is True and c['release_absent_at_authorization'] is True
          assert c['source_fix_lineage']['verified_fix_sha']=='03a3bd9a85bb15e1a783ed78f4d2efc0b4bb966a'
          assert c['source_fix_lineage']['artifact_id']==9991183617
          assert c['source_fix_lineage']['may_be_independent_confirmation'] is False
          assert c['root_cause']['shipping_dsp_defect'] is False
          assert c['frozen_change_scope']['candidate_limit_consumed']==0
          assert c['frozen_change_scope']['confirmation_limit_consumed']==0
          assert c['frozen_change_scope']['threshold_tuning_allowed'] is False
          assert c['required_fix']['base_resampler_mode']==c['required_fix']['head_resampler_mode']=='FAST'
          assert c['required_fix']['require_base_head_ap_cache_equivalence'] is True
          assert c['required_fix']['excluded_equivalence_key']=='AP_BUILD_SOURCE_REVISION'
          assert c['required_fix']['repetitions']==7 and c['required_fix']['frames']==100000 and c['required_fix']['paths']==8
          assert c['required_fix']['regression_gate']=={
              'relative_regression_pct':10.0,'absolute_regression_us':0.05,
              'logic':'fail only when both are exceeded'}
          assert c['release_policy']['semver_bump_required'] is True
          assert c['release_policy']['base_version']=='2.3.12' and c['release_policy']['target_version']=='2.3.13'
          assert c['release_policy']['program_shipping_baseline_migrates_only_after_release_exists_and_is_verified'] is True
          assert c['authority_boundary']=={
              'release_created_before_merge':False,'shipping_baseline_changed_before_release':False,
              'software_candidate_promoted':False,'product_qualification':'DEFERRED_BY_SCOPE','dut_hil':'DEFERRED_BY_SCOPE'}
          PY

      - name: Require target tag and release to remain absent
        env:
          GH_TOKEN: ${{ github.token }}
        shell: bash
        run: |
          set -euo pipefail
          if gh api "repos/$GITHUB_REPOSITORY/releases/tags/$TARGET_TAG" >/dev/null 2>&1; then
            echo "target release already exists: $TARGET_TAG" >&2; exit 1
          fi
          if gh api "repos/$GITHUB_REPOSITORY/git/ref/tags/$TARGET_TAG" >/dev/null 2>&1; then
            echo "target tag already exists: $TARGET_TAG" >&2; exit 1
          fi

      - name: Reverify previously exposed comparator lineage artifact
        env:
          GH_TOKEN: ${{ github.token }}
        shell: bash
        run: |
          set -euo pipefail
          curl --fail --silent --show-error --location \
            -H "Authorization: Bearer $GH_TOKEN" \
            -H 'Accept: application/vnd.github+json' \
            -H 'X-GitHub-Api-Version: 2022-11-28' \
            "https://api.github.com/repos/$GITHUB_REPOSITORY/actions/artifacts/$LINEAGE_ARTIFACT_ID/zip" \
            -o /tmp/i008-lineage.zip
          echo "$LINEAGE_ZIP_SHA256  /tmp/i008-lineage.zip" | sha256sum -c -
          rm -rf /tmp/i008-lineage && mkdir /tmp/i008-lineage
          unzip -q /tmp/i008-lineage.zip -d /tmp/i008-lineage
          python3 - <<'PY'
          from pathlib import Path
          import hashlib
          root=Path('/tmp/i008-lineage')
          manifests=list(root.rglob('SHA256SUMS'))
          assert len(manifests)==1, manifests
          rows=[line.split(maxsplit=1) for line in manifests[0].read_text().splitlines() if line.strip()]
          assert len(rows)==2, len(rows)
          files=[p for p in root.rglob('*') if p.is_file() and p!=manifests[0]]
          for digest, rel in rows:
              rel=rel.strip().lstrip('*')
              candidates=[p for p in files if str(p.relative_to(root))==rel or str(p.relative_to(root)).endswith('/'+rel)]
              assert len(candidates)==1, (rel,candidates)
              assert hashlib.sha256(candidates[0].read_bytes()).hexdigest()==digest
          print('lineage artifact: 2/2 hashes OK; authority remains exposed engineering lineage only')
          PY

      - name: Run fresh behavior-equivalent FAST paired measurement
        shell: bash
        env:
          CC: gcc
        run: |
          set -euo pipefail
          rm -rf i008-release-carry-evidence
          mkdir i008-release-carry-evidence
          sh scripts/compare-resampler-perf.sh "$PROGRAM_BASE" 7 100000 0.05 \
            | tee i008-release-carry-evidence/resampler-fast-paired.log
          test "$(grep -c '^resampler_fast_path ' i008-release-carry-evidence/resampler-fast-paired.log)" -eq 8

      - name: Seal release-carry engineering evidence
        if: always()
        shell: bash
        env:
          JOB_STATUS: ${{ job.status }}
        run: |
          set -euo pipefail
          mkdir -p i008-release-carry-evidence
          python3 - <<'PY'
          import json, os, re
          from pathlib import Path
          root=Path('i008-release-carry-evidence')
          log=root/'resampler-fast-paired.log'
          rows=[]
          if log.exists():
              pat=re.compile(r'^resampler_fast_path io=(\d+) internal=(\d+) base_median_us=([0-9.]+) head_median_us=([0-9.]+) paired_delta_pct=(-?[0-9.]+) abs_delta_us=(-?[0-9.]+)$')
              for line in log.read_text().splitlines():
                  m=pat.match(line)
                  if m:
                      rows.append({'io_hz':int(m.group(1)),'internal_hz':int(m.group(2)),
                          'base_median_us':float(m.group(3)),'head_median_us':float(m.group(4)),
                          'paired_delta_pct':float(m.group(5)),'abs_delta_us':float(m.group(6))})
          result={
              'schema_version':1,'iteration_id':'I008',
              'action_id':'resampler-perf-comparator-release-carry-v2.3.13',
              'base_sha':os.environ['PROGRAM_BASE'],'head_sha':os.environ['HEAD_SHA'],
              'target_version':'2.3.13','target_tag':'v2.3.13',
              'job_status':os.environ['JOB_STATUS'],'behavior_equivalent_cache_required':True,
              'candidate_limit_consumed':0,'confirmation_limit_consumed':0,
              'authority':'engineering-release-carry-regression-only',
              'product_qualification':'DEFERRED_BY_SCOPE','dut_hil':'DEFERRED_BY_SCOPE',
              'paths':rows,
              'decision':'RELEASE_CARRY_ENGINEERING_PASS_REVIEW_REQUIRED' if os.environ['JOB_STATUS']=='success' else 'RELEASE_CARRY_ENGINEERING_FAILED'}
          (root/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
          PY
          (cd i008-release-carry-evidence && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum) > i008-release-carry-evidence/SHA256SUMS

      - name: Upload hash-bound release-carry evidence
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
        with:
          name: i008-release-carry-v2.3.13-${{ github.run_id }}
          path: i008-release-carry-evidence/
          retention-days: 30
          if-no-files-found: error
'''
wf_path = Path(".github/workflows/i008-release-carry.yml")
wf_path.parent.mkdir(parents=True, exist_ok=True)
wf_path.write_text(workflow)
