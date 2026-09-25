#!/bin/sh
# One offline documentation/assurance gate for docs-only and full verification.
# I010 is terminal: validate the current registry, never require retired live inputs.
set -eu

python3 scripts/ci_impact.py --self-test
python3 scripts/github_governance.py --self-test
python3 scripts/resource_baseline.py --self-test
python3 scripts/docs_consistency.py --self-test
python3 scripts/public_surface_contract.py --self-test
python3 scripts/research_registry.py --self-test
python3 scripts/prepare_release.py --self-test
python3 scripts/release_manifest.py --self-test
python3 scripts/post_release_status.py --self-test
python3 scripts/qualification_fingerprint.py --self-test
python3 .github/research/continuous-optimization/hosted-validation/public_candidate_pair.py --source-root . --self-test
python3 .github/program/acoustic_terminal_registry.py --self-test
python3 .github/program/acoustic_terminal_registry.py --check
python3 tests/validation/i010_ns_vad_observation.py --self-test
python3 tests/validation/i010_apply_vad_pre_ns_candidate.py --self-test
python3 tests/validation/i010_vad_pre_ns_candidate.py --self-test
python3 .github/research/continuous-optimization/source_candidate_authority_v2.py --self-test
python3 .github/research/continuous-optimization/source_candidate_execution_v2_contract.py --self-test --check
python3 -m json.tool .github/research/evidence-index.json >/dev/null
python3 -m json.tool .github/research/qualification-policy.json >/dev/null
python3 scripts/docs_consistency.py
python3 scripts/public_surface_contract.py
