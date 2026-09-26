#!/usr/bin/env python3
"""Fail-closed workflow contract for the software-commercial-ready maintenance state."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = Path('.github/workflows')
PROGRAM_PLAN = Path('docs/program/plan.json')
I002_CONTRACT = Path('docs/program/iterations/I002.json')
AEC_MOTION_MAINTENANCE_WORKFLOW = Path('.github/workflows/aec-motion-development.yml')
EXTENDED_REAL_AUTOMATION_WORKFLOW = Path('.github/workflows/extended-real-automation.yml')
HIL_SOAK_WORKFLOW = Path('.github/workflows/hil-soak.yml')
PROGRAM_ARCHIVE_WORKFLOW = Path('.github/workflows/program-iteration.yml')
TERMINAL_RETIREMENT_MANIFEST = Path('docs/program/terminal-workflow-retirement.json')

# The generic tuner has no PR-regression role and is therefore manual-only after
# the terminal software program. PR/manual non-shipping workflows keep their PR
# regression or measurement coverage and explicit manual replay entry points,
# but must never run autonomous scheduled or push-triggered research/confirmation
# work in maintenance state.
MANUAL_ONLY_RESEARCH_WORKFLOWS = (
    Path('.github/workflows/acoustic-tuning-iteration.yml'),
)
REUSABLE_GOVERNANCE_WORKFLOWS = (
    Path('.github/workflows/research-source-candidate-v2-preflight.yml'),
)

HOSTED_REAL_PR_REQUIRED_PATHS = {
    Path('.github/workflows/hosted-real-validation.yml'): {
        'src/**',
        'include/**',
        'examples/process_pcm.c',
        'CMakeLists.txt',
        'cmake/**',
        'validation/authority.json',
        'validation/*.schema.json',
        'validation/tools/authority.py',
        'validation/tools/run_validation*.py',
        'validation/tools/render_corr_exact.*',
        'validation/tools/stage_profile_support.py',
        'validation/tools/build_hosted_real_corpus.py',
        'validation/hosted_real.datasets.lock.json',
        'validation/policies/validation-hosted-real-smoke.json',
        '.github/actions/setup-ccache/**',
        '.github/workflows/hosted-real-validation.yml',
    },
    Path('.github/workflows/hosted-aec-real-validation.yml'): {
        'src/**',
        'include/**',
        'examples/process_pcm.c',
        'CMakeLists.txt',
        'cmake/**',
        'validation/authority.json',
        'validation/*.schema.json',
        'validation/tools/authority.py',
        'validation/tools/run_validation*.py',
        'validation/tools/render_corr_exact.*',
        'validation/tools/stage_profile_support.py',
        'validation/tools/build_hosted_aec_corpus.py',
        'validation/hosted_aec.datasets.lock.json',
        'validation/policies/validation-hosted-aec-smoke.json',
        '.github/actions/setup-ccache/**',
        '.github/workflows/hosted-aec-real-validation.yml',
    },
}

PR_MANUAL_RESEARCH_WORKFLOWS = (
    Path('.github/workflows/aec-motion-tuning.yml'),
    Path('.github/workflows/agc-stage-tuning.yml'),
    Path('.github/workflows/ns-stage-tuning.yml'),
    Path('.github/workflows/ami-vad-microset-discovery.yml'),
    Path('.github/workflows/vad-operating-point-selector.yml'),
    Path('.github/workflows/vad-hangover-counterfactual.yml'),
    Path('.github/workflows/vad-strong-weak-refresh.yml'),
    Path('.github/workflows/ami-vad-confirmation-discovery.yml'),
    Path('.github/workflows/bf-hard-mic-fault-discovery.yml'),
    Path('.github/workflows/bf-hard-mic-fault-confirmation.yml'),
    Path('.github/workflows/dsp-data-research.yml'),
    Path('.github/workflows/pcr02-aec-real-tail-confirmation.yml'),
    Path('.github/workflows/pcr02-dsp-counterfactuals.yml'),
    Path('.github/workflows/research-optimization.yml'),
    Path('.github/workflows/research-algorithm-parameter-optimization.yml'),
    Path('.github/workflows/research-candidate-blind-qualification.yml'),
    Path('.github/workflows/research-source-authority-v2-qualification.yml'),
    Path('.github/workflows/research-i011-ns-noise-reference-scale.yml'),
    Path('.github/workflows/research-vad-domain-state-divergence-v1.yml'),
    Path('.github/workflows/research-vad-calibrated-local-snr-v1.yml'),
    Path('.github/workflows/research-i012-ns-spectral-post-snr-v2.yml'),
    Path('.github/workflows/research-i013-ns-excess-concentration-v1.yml'),
    Path('.github/workflows/research-i014-ns-upstream-component-decomposition-v1.yml'),
    Path('.github/workflows/research-i015-vad-upstream-consumption-decomposition-v1.yml'),
    Path('.github/workflows/research-i016-vad-local-evidence-gated-blend-v1.yml'),

)

PR_CONTRACT_MANUAL_REPLAY_WORKFLOWS = (
    Path('.github/workflows/vad-operating-point-selector.yml'),
    Path('.github/workflows/vad-hangover-counterfactual.yml'),
    Path('.github/workflows/vad-strong-weak-refresh.yml'),
    Path('.github/workflows/aec-motion-tuning.yml'),
)

CONTRACT_ONLY_RESEARCH_WORKFLOWS = (
    Path('.github/workflows/research-algorithm-parameter-optimization.yml'),
    Path('.github/workflows/research-vad-domain-state-divergence-v1.yml'),
    Path('.github/workflows/research-vad-calibrated-local-snr-v1.yml'),
    Path('.github/workflows/research-i012-ns-spectral-post-snr-v2.yml'),
    Path('.github/workflows/research-i013-ns-excess-concentration-v1.yml'),
    Path('.github/workflows/research-i014-ns-upstream-component-decomposition-v1.yml'),
    Path('.github/workflows/research-i015-vad-upstream-consumption-decomposition-v1.yml'),
    Path('.github/workflows/research-i016-vad-local-evidence-gated-blend-v1.yml'),
)
CONTRACT_ONLY_RESEARCH_EVIDENCE = {
    Path('.github/workflows/research-algorithm-parameter-optimization.yml'): (
        Path('.github/research/continuous-optimization/algorithm-space-v1.json'),
        Path('.github/research/continuous-optimization/algorithm-space-v1-closure.json'),
        Path('.github/research/continuous-optimization/development-v3/aec-boundary-refinement-v6-origin.json'),
        Path('.github/research/continuous-optimization/development-v3/doubletalk-case-guard-v5-closure.json'),
    ),
    Path('.github/workflows/research-vad-domain-state-divergence-v1.yml'): (
        Path('.github/research/continuous-optimization/development-v4/vad-domain-state-divergence-v1.json'),
        Path('.github/research/continuous-optimization/development-v4/vad-domain-state-divergence-v1-result.json'),
    ),
    Path('.github/workflows/research-vad-calibrated-local-snr-v1.yml'): (
        Path('.github/research/continuous-optimization/development-v4/vad-calibrated-local-snr-v1.json'),
        Path('.github/research/continuous-optimization/development-v4/vad-calibrated-local-snr-v1-result.json'),
    ),
    Path('.github/workflows/research-i012-ns-spectral-post-snr-v2.yml'): (
        Path('.github/research/continuous-optimization/development-v4/i012-ns-spectral-post-snr-v2.json'),
        Path('.github/research/continuous-optimization/development-v4/i012-ns-spectral-post-snr-v2-result.json'),
    ),
    Path('.github/workflows/research-i013-ns-excess-concentration-v1.yml'): (
        Path('.github/research/continuous-optimization/development-v4/i013-ns-excess-concentration-v1.json'),
        Path('.github/research/continuous-optimization/development-v4/i013-ns-excess-concentration-v1-result.json'),
    ),
    Path('.github/workflows/research-i014-ns-upstream-component-decomposition-v1.yml'): (
        Path('.github/research/continuous-optimization/development-v4/i014-ns-upstream-component-decomposition-v1.json'),
        Path('.github/research/continuous-optimization/development-v4/i014-ns-upstream-component-decomposition-v1-result.json'),
    ),
    Path('.github/workflows/research-i015-vad-upstream-consumption-decomposition-v1.yml'): (
        Path('.github/research/continuous-optimization/development-v4/i015-vad-upstream-consumption-decomposition-v1.json'),
        Path('.github/research/continuous-optimization/development-v4/i015-vad-upstream-consumption-decomposition-v1-result.json'),
    ),
    Path('.github/workflows/research-i016-vad-local-evidence-gated-blend-v1.yml'): (
        Path('.github/research/continuous-optimization/development-v4/i016-vad-local-evidence-gated-blend-v1.json'),
        Path('.github/research/continuous-optimization/development-v4/i016-vad-local-evidence-gated-blend-v1-result.json'),
        Path('validation/research/evidence/i016-36245702675/SHA256SUMS'),
        Path('validation/research/evidence/i016-36245702675/build-info.txt'),
        Path('validation/research/evidence/i016-36245702675/contract.json'),
        Path('validation/research/evidence/i016-36245702675/corpora.txt'),
        Path('validation/research/evidence/i016-36245702675/probe.sha256'),
        Path('validation/research/evidence/i016-36245702675/result.json'),
        Path('validation/research/evidence/i016-36245702675/summary.json'),
    ),
}


# Recurring execution is an explicit maintenance capability, not a default.
# Every legal cron below is validation, data-integrity, HIL or qualification
# convergence work. Candidate/research search is intentionally absent.
ALLOWED_SCHEDULED_WORKFLOWS = {
    AEC_MOTION_MAINTENANCE_WORKFLOW: ('41 18 * * 2,5',),
    EXTENDED_REAL_AUTOMATION_WORKFLOW: ('17 3 * * 0',),
    HIL_SOAK_WORKFLOW: ('43 18 * * *', '17 17 * * 0'),
    Path('.github/workflows/hosted-aec-real-validation.yml'): ('23 18 * * *',),
    Path('.github/workflows/hosted-real-validation.yml'): ('47 18 * * *',),
    Path('.github/workflows/lab-acquisition-smoke.yml'): ('23 3 * * 3',),
    Path('.github/workflows/nightly.yml'): ('17 19 * * *',),
    Path('.github/workflows/post-release-qualification-summary.yml'): ('23 * * * *',),
}
CRON_RE = re.compile(r"^    - cron:\s*['\"]([^'\"]+)['\"]\s*$", re.MULTILINE)
MAINTENANCE_CONTRACT_TRIGGER_PATH = ".github/program/maintenance_workflow_contract.py"
LEGACY_SEMANTICS_TOKENS = (
    "stage_profile_support.install(",
    "render_corr_exact.install(",
    "install_fail_closed_guards(",
)
LEGACY_SEMANTICS_GLOBS = (
    ".github/research/continuous-optimization/*.py",
    "validation/tools/*.py",
    "tests/validation/*.py",
)
TERMINAL_RETIREMENT_COLLECTION_KEYS = {
    "workflows",
    "research_workflows",
    "source_candidate_workflows",
    "selection_workflows",
    "source_candidate_rounds",
    "stage_lane_rounds",
    "historical_replay_workflows",
}


def extract_on_block(text: str) -> str:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line == 'on:'), None)
    assert start is not None, 'workflow has no top-level on block'
    block: list[str] = []
    for line in lines[start + 1:]:
        if line and not line.startswith((' ', '\t')):
            break
        block.append(line)
    return '\n'.join(block)


def scheduled_crons(text: str) -> tuple[str, ...]:
    on_block = extract_on_block(text)
    if not re.search(r'(?m)^  schedule:\s*$', on_block):
        return ()
    crons = tuple(CRON_RE.findall(on_block))
    assert crons, 'scheduled workflow must use explicit quoted cron entries'
    return crons


def trigger_block(text: str, trigger: str) -> str:
    on_block = extract_on_block(text)
    lines = on_block.splitlines()
    marker = f'  {trigger}:'
    start = next((index for index, line in enumerate(lines) if line == marker), None)
    assert start is not None, f'workflow is missing {trigger} trigger'
    block: list[str] = []
    for line in lines[start + 1:]:
        if re.match(r'^  [A-Za-z_][A-Za-z0-9_-]*:', line):
            break
        block.append(line)
    return '\n'.join(block)


def job_block(text: str, job: str) -> str:
    jobs_index = text.find('\njobs:')
    assert jobs_index >= 0, 'workflow has no jobs block'
    jobs_text = text[jobs_index + 1:]
    match = re.search(
        rf'(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z_][A-Za-z0-9_-]*:\n|\Z)',
        jobs_text,
    )
    assert match is not None, f'workflow is missing {job} job'
    return match.group(1)


def validate_hosted_real_trigger_boundaries(root: Path) -> None:
    for relative, required_paths in HOSTED_REAL_PR_REQUIRED_PATHS.items():
        path = root / relative
        assert path.is_file(), f'missing hosted-real workflow: {relative}'
        text = path.read_text(encoding='utf-8')
        pull_request = trigger_block(text, 'pull_request')
        actual_paths = set(
            re.findall(r"(?m)^      - ['\"]([^'\"]+)['\"]\s*$", pull_request)
        )
        assert actual_paths, f'{relative} pull_request must be path-scoped'
        missing = sorted(required_paths - actual_paths)
        assert not missing, f'{relative} lost required PR impact path(s): {missing}'

        push = trigger_block(text, 'push')
        assert re.search(r'(?m)^    branches:\s*\[main\]\s*$', push), (
            f'{relative} must retain unconditional main push coverage'
        )
        trigger_block(text, 'workflow_dispatch')

    aec = root / Path('.github/workflows/hosted-aec-real-validation.yml')
    trigger_block(aec.read_text(encoding='utf-8'), 'workflow_call')


def validate_aec_motion_maintenance_boundary(root: Path) -> None:
    """Prove the recurring motion job is regression maintenance, not reopened I002 research."""
    contract = json.loads((root / I002_CONTRACT).read_text(encoding='utf-8'))
    assert contract['iteration_id'] == 'I002', 'AEC motion maintenance lost I002 contract identity'
    assert contract['candidate_limit'] == 0, 'AEC motion maintenance cannot regain candidate search budget'
    assert contract['confirmation_limit'] == 0, 'AEC motion maintenance cannot consume confirmation data'
    assert contract['promotion_allowed'] is False, 'AEC motion maintenance cannot gain promotion authority'
    assert contract['data_role'] == 'development', 'AEC motion maintenance must remain development-only'

    plan = json.loads((root / PROGRAM_PLAN).read_text(encoding='utf-8'))
    task = next((item for item in plan.get('tasks', []) if item.get('id') == 'I002'), None)
    assert task is not None, 'I002 missing from canonical program plan'
    assert task.get('status') == 'CLOSED', 'scheduled AEC motion validation requires terminal I002'
    assert task.get('handler') is None, 'scheduled AEC motion validation cannot restore an I002 handler'


def _github_path_pattern_matches(pattern: str, path: str) -> bool:
    escaped = re.escape(pattern)
    escaped = escaped.replace(r'\*\*', '.*')
    escaped = escaped.replace(r'\*', '[^/]*')
    escaped = escaped.replace(r'\?', '[^/]')
    return re.fullmatch(escaped, path) is not None


def _validate_terminal_retirement_collection_keys(data: dict) -> None:
    collection_keys = {
        key for key, value in data.items() if isinstance(value, list)
    }
    assert collection_keys == TERMINAL_RETIREMENT_COLLECTION_KEYS, (
        f'terminal retirement collection categories drift: '
        f'{sorted(collection_keys ^ TERMINAL_RETIREMENT_COLLECTION_KEYS)}'
    )


def _terminal_retirement_required_paths(root: Path) -> set[str]:
    manifest = root / TERMINAL_RETIREMENT_MANIFEST
    if not manifest.is_file():
        return set()
    data = json.loads(manifest.read_text(encoding='utf-8'))
    _validate_terminal_retirement_collection_keys(data)
    required: set[str] = set()

    for record in data.get('workflows', []):
        required.update((record['path'], record['terminal_evidence']))
    for record in data.get('research_workflows', []):
        required.update((record['path'], record['evidence']))
    for record in data.get('source_candidate_workflows', []):
        required.update((record['path'], record['evidence']))
    for record in data.get('selection_workflows', []):
        required.update((
            record['path'], record['evidence'], record['successor'],
            record['terminal_evidence'],
        ))
    for round_record in data.get('source_candidate_rounds', []):
        required.add(round_record['round_closure'])
        for workflow in round_record.get('workflows', []):
            required.update((workflow['path'], workflow['evidence']))
        required.update(round_record.get('candidate_contracts', {}).values())
        required.update(round_record.get('candidate_closures', {}).values())
    for round_record in data.get('stage_lane_rounds', []):
        required.update((round_record['path'], round_record['evidence']))
        required.update(round_record.get('lane_outcomes', {}).values())
    for replay_record in data.get('historical_replay_workflows', []):
        required.update((replay_record['path'], replay_record['evidence']))
    return required


def program_archive_required_paths(root: Path) -> list[str]:
    required = {
        str(PROGRAM_ARCHIVE_WORKFLOW),
        str(PROGRAM_PLAN),
        str(I002_CONTRACT),
        str(TERMINAL_RETIREMENT_MANIFEST),
        'scripts/program.py',
        '.github/program/promotion_governance.py',
        '.github/program/terminal_workflow_retirement.py',
        '.github/program/maintenance_workflow_contract.py',
    }
    required.update(str(path) for path in MANUAL_ONLY_RESEARCH_WORKFLOWS)
    required.update(str(path) for path in REUSABLE_GOVERNANCE_WORKFLOWS)
    required.update(str(path) for path in PR_MANUAL_RESEARCH_WORKFLOWS)
    required.update(str(path) for path in ALLOWED_SCHEDULED_WORKFLOWS)
    required.update(str(path) for path in HOSTED_REAL_PR_REQUIRED_PATHS)
    for evidence_paths in CONTRACT_ONLY_RESEARCH_EVIDENCE.values():
        required.update(str(path) for path in evidence_paths)
    required.update(_terminal_retirement_required_paths(root))
    return sorted(required)


def validate_program_archive_trigger_boundaries(root: Path) -> None:
    path = root / PROGRAM_ARCHIVE_WORKFLOW
    assert path.is_file(), f'missing Program Archive workflow: {PROGRAM_ARCHIVE_WORKFLOW}'
    text = path.read_text(encoding='utf-8')

    def paths_for(trigger: str) -> list[str]:
        block = trigger_block(text, trigger)
        paths = re.findall(r"(?m)^      - ['\"]([^'\"]+)['\"]\s*$", block)
        assert paths, f'Program Archive {trigger} must remain path-scoped'
        assert len(paths) == len(set(paths)), (
            f'Program Archive {trigger} contains duplicate path entries'
        )
        return paths

    push_paths = paths_for('push')
    pull_paths = paths_for('pull_request')
    assert push_paths == pull_paths, (
        'Program Archive push/pull path sets or ordering drifted'
    )
    missing = [
        required for required in program_archive_required_paths(root)
        if not any(_github_path_pattern_matches(pattern, required) for pattern in push_paths)
    ]
    assert not missing, (
        f'Program Archive trigger missing required path coverage: {missing}'
    )


def validate_no_legacy_semantics_consumers(root: Path) -> None:
    for pattern in LEGACY_SEMANTICS_GLOBS:
        for path in sorted(root.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            for token in LEGACY_SEMANTICS_TOKENS:
                assert token not in text, (
                    f"legacy global semantics consumer remains: "
                    f"{path.relative_to(root)}: {token}"
                )


def validate_deferred_external_schedule_boundaries(root: Path) -> None:
    extended_text = (root / EXTENDED_REAL_AUTOMATION_WORKFLOW).read_text(encoding='utf-8')
    extended_job = job_block(extended_text, 'dispatch')
    extended_skip = 'EXTENDED_REAL_SCHEDULE_SKIPPED_DISABLED'
    extended_required = 'EXTENDED_REAL_REQUIRED_BUT_DISABLED'
    assert extended_skip in extended_job, (
        'Extended Real disabled schedule must cleanly skip instead of failing'
    )
    assert extended_required in extended_job, (
        'Extended Real required/manual events must remain fail-closed when disabled'
    )
    assert extended_job.index(extended_skip) < extended_job.index(extended_required), (
        'Extended Real scheduled skip must be resolved before required-event failure'
    )
    assert 'if [ "$EVENT_NAME" = schedule ]; then' in extended_job, (
        'Extended Real disabled clean skip must remain schedule-only'
    )
    assert "if: steps.request.outputs.run == 'true'" in extended_job, (
        'Extended Real dispatch must remain gated by the resolved run decision'
    )

    hil_text = (root / HIL_SOAK_WORKFLOW).read_text(encoding='utf-8')
    availability = job_block(hil_text, 'availability')
    hil_skip = 'HIL_SCHEDULE_SKIPPED_DISABLED'
    hil_required = 'HIL_REQUIRED_BUT_DISABLED'
    assert hil_skip in availability, (
        'HIL disabled schedule must cleanly skip instead of failing'
    )
    assert hil_required in availability, (
        'HIL post-release required event must remain fail-closed when disabled'
    )
    assert availability.index(hil_skip) < availability.index(hil_required), (
        'HIL scheduled skip must be resolved before required-event failure'
    )
    assert 'if [ "$EVENT_NAME" = schedule ]; then' in availability, (
        'HIL disabled clean skip must remain schedule-only'
    )
    assert 'if [ "$EVENT_NAME" = repository_dispatch ]; then' in availability, (
        'HIL post-release dispatch validation must remain explicit'
    )
    assert 'if [ "$EVENT_NAME" = workflow_dispatch ]; then' in availability, (
        'HIL explicit manual execution path must remain available'
    )


def validate(root: Path = REPOSITORY_ROOT) -> None:
    validate_program_archive_trigger_boundaries(root)
    validate_no_legacy_semantics_consumers(root)
    for relative in MANUAL_ONLY_RESEARCH_WORKFLOWS:
        path = root / relative
        assert path.is_file(), f'missing maintenance research workflow: {relative}'
        text = path.read_text(encoding='utf-8')
        assert '\n  workflow_dispatch:' in text, f'{relative} must retain an explicit manual entry point'
        assert '\n  schedule:' not in text, f'{relative} must not run autonomous scheduled research in maintenance state'
        assert '\n  push:' not in text, f'{relative} must not run autonomous push research in maintenance state'
        assert '\n  pull_request:' not in text, f'{relative} is the generic search entry point and must remain manual-only'

    for relative in PR_MANUAL_RESEARCH_WORKFLOWS:
        path = root / relative
        assert path.is_file(), f'missing PR/manual non-shipping workflow: {relative}'
        text = path.read_text(encoding='utf-8')
        assert '\n  pull_request:' in text, f'{relative} must retain PR regression or measurement coverage'
        # Consumed research may retire manual entry entirely. Its evidence and
        # sole offline contract job are still enforced below. Actual replay
        # workflows retain the mandatory manual-only execution boundary.
        if relative not in CONTRACT_ONLY_RESEARCH_WORKFLOWS:
            assert '\n  workflow_dispatch:' in text, f'{relative} must retain an explicit manual replay entry point'
        assert '\n  schedule:' not in text, f'{relative} must not run autonomous scheduled non-shipping work in maintenance state'
        assert '\n  push:' not in text, f'{relative} must not run autonomous push non-shipping work in maintenance state'
        pull_request = trigger_block(text, 'pull_request')
        assert MAINTENANCE_CONTRACT_TRIGGER_PATH not in pull_request, (
            f'{relative} must not fan out on maintenance contract edits; Program Archive owns that validation'
        )

    for relative in PR_CONTRACT_MANUAL_REPLAY_WORKFLOWS:
        path = root / relative
        text = path.read_text(encoding='utf-8')
        contract = job_block(text, 'contract')
        replay = job_block(text, 'select')
        assert 'actions/checkout@' in contract and '--self-test' in contract, (
            f'{relative} PR contract job must retain checkout and offline self-tests'
        )
        assert not re.search(r"(?m)^    if:\s*github\.event_name\s*==\s*['\"]workflow_dispatch['\"]\s*$", contract), (
            f'{relative} contract job must run on PR and manual dispatch'
        )
        assert re.search(r"(?m)^    needs:\s*contract\s*$", replay), (
            f'{relative} full research replay must depend on contract'
        )
        assert re.search(r"(?m)^    if:\s*github\.event_name\s*==\s*['\"]workflow_dispatch['\"]\s*$", replay), (
            f'{relative} full historical search must remain manual-dispatch-only'
        )

    assert set(CONTRACT_ONLY_RESEARCH_EVIDENCE) == set(CONTRACT_ONLY_RESEARCH_WORKFLOWS), (
        'contract-only research evidence mapping must exactly cover contract-only workflows'
    )
    for relative in CONTRACT_ONLY_RESEARCH_WORKFLOWS:
        path = root / relative
        text = path.read_text(encoding='utf-8')
        evidence_paths = CONTRACT_ONLY_RESEARCH_EVIDENCE[relative]
        assert evidence_paths, f'{relative} must bind durable consumed-research evidence'
        for evidence_relative in evidence_paths:
            assert (root / evidence_relative).is_file(), (
                f'{relative} durable evidence missing: {evidence_relative}'
            )
        contract = job_block(text, 'contract')
        jobs_text = text[text.find('\njobs:') + 1:]
        job_names = re.findall(r'(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$', jobs_text)
        assert job_names == ['contract'], (
            f'{relative} is consumed historical research and must remain contract-only: {job_names}'
        )
        assert 'actions/checkout@' in contract and '--self-test' in contract, (
            f'{relative} contract-only workflow must retain checkout and offline self-tests'
        )

    for relative in REUSABLE_GOVERNANCE_WORKFLOWS:
        path = root / relative
        assert path.is_file(), f'missing reusable governance workflow: {relative}'
        text = path.read_text(encoding='utf-8')
        on = extract_on_block(text)
        assert re.search(r'(?m)^  workflow_call:\s*$', on), (
            f'{relative} must remain workflow_call-only'
        )
        for forbidden in ('workflow_dispatch', 'pull_request', 'push', 'schedule'):
            assert not re.search(rf'(?m)^  {forbidden}:', on), (
                f'{relative} cannot expose direct trigger: {forbidden}'
            )

    validate_aec_motion_maintenance_boundary(root)
    validate_hosted_real_trigger_boundaries(root)
    validate_deferred_external_schedule_boundaries(root)

    actual: dict[Path, tuple[str, ...]] = {}
    workflow_root = root / WORKFLOW_DIR
    for pattern in ('*.yml', '*.yaml'):
        for path in sorted(workflow_root.glob(pattern)):
            crons = scheduled_crons(path.read_text(encoding='utf-8'))
            if crons:
                actual[path.relative_to(root)] = crons

    expected_paths = set(ALLOWED_SCHEDULED_WORKFLOWS)
    actual_paths = set(actual)
    unexpected = sorted(str(path) for path in actual_paths - expected_paths)
    missing = sorted(str(path) for path in expected_paths - actual_paths)
    assert not unexpected, f'unregistered scheduled workflow(s): {unexpected}'
    assert not missing, f'approved scheduled workflow(s) lost schedule: {missing}'
    for relative, expected_crons in ALLOWED_SCHEDULED_WORKFLOWS.items():
        assert actual[relative] == expected_crons, (
            f'approved schedule drift for {relative}: actual={actual[relative]} expected={expected_crons}'
        )


def _write_program_archive_fixture(root: Path, duplicate: bool = False) -> None:
    path = root / PROGRAM_ARCHIVE_WORKFLOW
    path.parent.mkdir(parents=True, exist_ok=True)
    paths = program_archive_required_paths(root)
    push_paths = paths + ([paths[0]] if duplicate else [])
    pull_paths = paths
    push = ''.join(f"      - '{item}'\n" for item in push_paths)
    pull = ''.join(f"      - '{item}'\n" for item in pull_paths)
    path.write_text(
        'name: Program Archive Contract\n\non:\n'
        '  push:\n'
        '    branches: [main]\n'
        '    paths:\n' + push +
        '  pull_request:\n'
        '    branches: [main]\n'
        '    paths:\n' + pull,
        encoding='utf-8',
    )


def _write_allowed_schedule(path: Path, crons: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    schedule = ''.join(f"    - cron: '{cron}'\n" for cron in crons)
    path.write_text(
        'name: approved\n\non:\n  schedule:\n' + schedule + '  workflow_dispatch:\n',
        encoding='utf-8',
    )


def _write_hosted_real_fixture(root: Path, relative: Path,
                               required_paths: set[str],
                               crons: tuple[str, ...]) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    pr_paths = ''.join(f"      - '{item}'\n" for item in sorted(required_paths))
    schedule = ''.join(f"    - cron: '{cron}'\n" for cron in crons)
    reusable = (
        '  workflow_call:\n'
        if relative.name == 'hosted-aec-real-validation.yml'
        else ''
    )
    path.write_text(
        'name: hosted-real\n\non:\n'
        '  pull_request:\n'
        '    paths:\n' + pr_paths +
        '  push:\n'
        '    branches: [main]\n'
        '  schedule:\n' + schedule +
        '  workflow_dispatch:\n' + reusable,
        encoding='utf-8',
    )


def _write_deferred_external_schedule_fixtures(root: Path) -> None:
    extended = root / EXTENDED_REAL_AUTOMATION_WORKFLOW
    extended.parent.mkdir(parents=True, exist_ok=True)
    extended.write_text(
        "name: Extended Real Automation\n\non:\n"
        "  repository_dispatch:\n    types: [extended-real-post-release]\n"
        "  schedule:\n    - cron: '17 3 * * 0'\n"
        "  workflow_dispatch:\n\n"
        "jobs:\n"
        "  dispatch:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: Resolve exact source and automation profile\n"
        "        id: request\n"
        "        run: |\n"
        "          if [ \"$EXTENDED_REAL_ENABLED\" != true ]; then\n"
        "            if [ \"$EVENT_NAME\" = schedule ]; then\n"
        "              echo 'run=false' >> \"$GITHUB_OUTPUT\"\n"
        "              echo 'EXTENDED_REAL_SCHEDULE_SKIPPED_DISABLED'\n"
        "              exit 0\n"
        "            fi\n"
        "            echo 'EXTENDED_REAL_REQUIRED_BUT_DISABLED' >&2\n"
        "            exit 1\n"
        "          fi\n"
        "          echo 'run=true' >> \"$GITHUB_OUTPUT\"\n"
        "      - name: Dispatch canonical extended-real workflow\n"
        "        if: steps.request.outputs.run == 'true'\n"
        "        run: echo dispatch\n",
        encoding='utf-8',
    )

    hil = root / HIL_SOAK_WORKFLOW
    hil.write_text(
        "name: HIL Tiered Soak\n\non:\n"
        "  schedule:\n"
        "    - cron: '43 18 * * *'\n"
        "    - cron: '17 17 * * 0'\n"
        "  repository_dispatch:\n    types: [hil-post-release]\n"
        "  workflow_dispatch:\n\n"
        "jobs:\n"
        "  availability:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: Enforce HIL availability policy\n"
        "        run: |\n"
        "          if [ \"$EVENT_NAME\" = workflow_dispatch ]; then\n"
        "            echo 'run=true' >> \"$GITHUB_OUTPUT\"\n"
        "            exit 0\n"
        "          fi\n"
        "          if [ \"$EVENT_NAME\" = repository_dispatch ]; then\n"
        "            echo validate-post-release\n"
        "          fi\n"
        "          if [ \"$HIL_ENABLED\" != true ]; then\n"
        "            echo 'run=false' >> \"$GITHUB_OUTPUT\"\n"
        "            if [ \"$EVENT_NAME\" = schedule ]; then\n"
        "              echo 'HIL_SCHEDULE_SKIPPED_DISABLED'\n"
        "              exit 0\n"
        "            fi\n"
        "            echo 'HIL_REQUIRED_BUT_DISABLED' >&2\n"
        "            exit 1\n"
        "          fi\n"
        "          echo 'run=true' >> \"$GITHUB_OUTPUT\"\n"
        "  soak:\n"
        "    needs: availability\n"
        "    if: needs.availability.outputs.run == 'true'\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo soak\n",
        encoding='utf-8',
    )


def _write_i002_terminal_fixture(root: Path) -> None:
    contract = root / I002_CONTRACT
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text(
        json.dumps({
            'iteration_id': 'I002',
            'candidate_limit': 0,
            'confirmation_limit': 0,
            'promotion_allowed': False,
            'data_role': 'development',
        }) + '\n',
        encoding='utf-8',
    )
    plan = root / PROGRAM_PLAN
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(
        json.dumps({'tasks': [{'id': 'I002', 'status': 'CLOSED', 'handler': None}]}) + '\n',
        encoding='utf-8',
    )


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        retirement_collections = {
            key: [] for key in TERMINAL_RETIREMENT_COLLECTION_KEYS
        }
        _validate_terminal_retirement_collection_keys(retirement_collections)
        unknown_collections = dict(retirement_collections)
        unknown_collections['future_retirement_category'] = []
        try:
            _validate_terminal_retirement_collection_keys(unknown_collections)
        except AssertionError as exc:
            assert 'collection categories drift' in str(exc)
        else:
            raise AssertionError('unknown retirement collection bypassed archive coverage')
        missing_collections = dict(retirement_collections)
        missing_collections.pop('historical_replay_workflows')
        try:
            _validate_terminal_retirement_collection_keys(missing_collections)
        except AssertionError as exc:
            assert 'collection categories drift' in str(exc)
        else:
            raise AssertionError('missing retirement collection bypassed archive coverage')

        _write_i002_terminal_fixture(root)
        _write_program_archive_fixture(root)
        generic = root / MANUAL_ONLY_RESEARCH_WORKFLOWS[0]
        generic.parent.mkdir(parents=True, exist_ok=True)
        generic.write_text('name: generic\n\non:\n  workflow_dispatch:\n', encoding='utf-8')
        for relative in PR_MANUAL_RESEARCH_WORKFLOWS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative in CONTRACT_ONLY_RESEARCH_WORKFLOWS:
                for evidence_relative in CONTRACT_ONLY_RESEARCH_EVIDENCE[relative]:
                    evidence_path = root / evidence_relative
                    evidence_path.parent.mkdir(parents=True, exist_ok=True)
                    evidence_path.write_text('{}\n', encoding='utf-8')
                path.write_text(
                    'name: contract-only-research\n\non:\n  pull_request:\n  workflow_dispatch:\n\n'
                    'jobs:\n'
                    '  contract:\n'
                    '    runs-on: ubuntu-latest\n'
                    '    steps:\n'
                    '      - uses: actions/checkout@pinned\n'
                    '      - name: self-test\n'
                    '        run: python3 tool.py --self-test\n',
                    encoding='utf-8',
                )
            elif relative in PR_CONTRACT_MANUAL_REPLAY_WORKFLOWS:
                path.write_text(
                    'name: historical-search\n\non:\n  pull_request:\n  workflow_dispatch:\n\n'
                    'jobs:\n'
                    '  contract:\n'
                    '    runs-on: ubuntu-latest\n'
                    '    steps:\n'
                    '      - uses: actions/checkout@pinned\n'
                    '      - name: self-test\n'
                    '        run: python3 tool.py --self-test\n'
                    '  select:\n'
                    '    needs: contract\n'
                    "    if: github.event_name == 'workflow_dispatch'\n"
                    '    runs-on: ubuntu-latest\n'
                    '    steps:\n'
                    '      - run: echo replay\n',
                    encoding='utf-8',
                )
            else:
                path.write_text(
                    'name: non-shipping\n\non:\n  pull_request:\n  workflow_dispatch:\n',
                    encoding='utf-8',
                )
        for relative in REUSABLE_GOVERNANCE_WORKFLOWS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                'name: reusable\n\non:\n  workflow_call:\n',
                encoding='utf-8',
            )
        for relative, crons in ALLOWED_SCHEDULED_WORKFLOWS.items():
            _write_allowed_schedule(root / relative, crons)
        for relative, required_paths in HOSTED_REAL_PR_REQUIRED_PATHS.items():
            _write_hosted_real_fixture(
                root, relative, required_paths, ALLOWED_SCHEDULED_WORKFLOWS[relative]
            )
        _write_deferred_external_schedule_fixtures(root)
        validate(root)

        extended_path = root / EXTENDED_REAL_AUTOMATION_WORKFLOW
        extended_text = extended_path.read_text(encoding='utf-8')
        extended_path.write_text(
            extended_text.replace('EXTENDED_REAL_SCHEDULE_SKIPPED_DISABLED', 'EXTENDED_REAL_DISABLED'),
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'disabled schedule must cleanly skip' in str(exc)
        else:
            raise AssertionError('Extended Real scheduled-disabled failure policy drift was accepted')
        extended_path.write_text(extended_text, encoding='utf-8')

        hil_path = root / HIL_SOAK_WORKFLOW
        hil_text = hil_path.read_text(encoding='utf-8')
        hil_path.write_text(
            hil_text.replace('HIL_REQUIRED_BUT_DISABLED', 'HIL_DISABLED'),
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'post-release required event must remain fail-closed' in str(exc)
        else:
            raise AssertionError('HIL post-release disabled fail-closed policy drift was accepted')
        hil_path.write_text(hil_text, encoding='utf-8')

        _write_program_archive_fixture(root, duplicate=True)
        try:
            validate(root)
        except AssertionError as exc:
            assert 'duplicate path entries' in str(exc)
        else:
            raise AssertionError('duplicate Program Archive path was accepted')
        _write_program_archive_fixture(root)

        archive = root / PROGRAM_ARCHIVE_WORKFLOW
        required_path = str(PR_MANUAL_RESEARCH_WORKFLOWS[0])
        required_line = f"      - '{required_path}'\n"
        archive.write_text(
            archive.read_text(encoding='utf-8').replace(required_line, ''),
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'missing required path coverage' in str(exc)
        else:
            raise AssertionError('missing Program Archive required path was accepted')
        _write_program_archive_fixture(root)

        hosted = next(iter(HOSTED_REAL_PR_REQUIRED_PATHS))
        hosted_path = root / hosted
        hosted_text = hosted_path.read_text(encoding='utf-8')
        hosted_path.write_text(
            re.sub(
                r"(?m)^  pull_request:\n    paths:\n(?:      - .+\n)+",
                '  pull_request:\n',
                hosted_text,
                count=1,
            ),
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'path-scoped' in str(exc) or 'lost required PR impact path' in str(exc)
        else:
            raise AssertionError('hosted-real workflow regained an unscoped PR trigger')
        _write_hosted_real_fixture(
            root, hosted, HOSTED_REAL_PR_REQUIRED_PATHS[hosted],
            ALLOWED_SCHEDULED_WORKFLOWS[hosted],
        )

        rogue = root / WORKFLOW_DIR / 'new-autonomous-research.yml'
        rogue.write_text(
            "name: rogue\n\non:\n  schedule:\n    - cron: '5 * * * *'\n  workflow_dispatch:\n",
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'unregistered scheduled workflow' in str(exc)
        else:
            raise AssertionError('new scheduled workflow bypassed the maintenance allowlist')
        rogue.unlink()

        allowed = next(iter(ALLOWED_SCHEDULED_WORKFLOWS))
        _write_allowed_schedule(root / allowed, ('7 * * * *',))
        try:
            validate(root)
        except AssertionError as exc:
            assert 'schedule drift' in str(exc)
        else:
            raise AssertionError('approved workflow cron drift was accepted')
        _write_allowed_schedule(root / allowed, ALLOWED_SCHEDULED_WORKFLOWS[allowed])

        generic_pr_manual = next(
            relative for relative in PR_MANUAL_RESEARCH_WORKFLOWS
            if relative not in PR_CONTRACT_MANUAL_REPLAY_WORKFLOWS
            and relative not in CONTRACT_ONLY_RESEARCH_WORKFLOWS
        )
        nonshipping = root / generic_pr_manual
        nonshipping.write_text(
            "name: non-shipping\n\non:\n  pull_request:\n  schedule:\n    - cron: '17 19 * * *'\n  workflow_dispatch:\n",
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'scheduled non-shipping work' in str(exc)
        else:
            raise AssertionError('scheduled PR/manual non-shipping workflow was not rejected')

        nonshipping.write_text('name: non-shipping\n\non:\n  workflow_dispatch:\n', encoding='utf-8')
        try:
            validate(root)
        except AssertionError as exc:
            assert 'PR regression or measurement coverage' in str(exc)
        else:
            raise AssertionError('PR/manual non-shipping workflow without PR coverage was not rejected')
        nonshipping.write_text('name: non-shipping\n\non:\n  pull_request:\n  workflow_dispatch:\n', encoding='utf-8')
        nonshipping.write_text(
            'name: non-shipping\n\non:\n  pull_request:\n    paths:\n'
            f"      - '{MAINTENANCE_CONTRACT_TRIGGER_PATH}'\n"
            '  workflow_dispatch:\n',
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'must not fan out on maintenance contract edits' in str(exc)
        else:
            raise AssertionError('maintenance contract trigger fan-out was accepted')
        nonshipping.write_text('name: non-shipping\n\non:\n  pull_request:\n  workflow_dispatch:\n', encoding='utf-8')

        historical_search = root / PR_CONTRACT_MANUAL_REPLAY_WORKFLOWS[0]
        historical_text = historical_search.read_text(encoding='utf-8')
        historical_search.write_text(
            historical_text.replace(
                "    if: github.event_name == 'workflow_dispatch'\n", ''
            ),
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'full historical search must remain manual-dispatch-only' in str(exc)
        else:
            raise AssertionError('historical VAD search regained PR full-replay authority')
        historical_search.write_text(historical_text, encoding='utf-8')

        contract_only = root / CONTRACT_ONLY_RESEARCH_WORKFLOWS[0]
        contract_only_text = contract_only.read_text(encoding='utf-8')
        # Retiring manual entry is valid only for registered contract-only
        # research. The following negative test still rejects an execution job.
        contract_only.write_text(
            contract_only_text.replace('  workflow_dispatch:\n', ''), encoding='utf-8'
        )
        validate(root)
        contract_only.write_text(contract_only_text, encoding='utf-8')
        contract_only.write_text(
            contract_only_text +
            '  joint-search:\n'
            '    runs-on: ubuntu-latest\n'
            '    steps:\n'
            '      - run: echo forbidden\n',
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'must remain contract-only' in str(exc)
        else:
            raise AssertionError('consumed research workflow regained execution job')
        contract_only.write_text(contract_only_text, encoding='utf-8')

        reusable = root / REUSABLE_GOVERNANCE_WORKFLOWS[0]
        reusable.write_text(
            'name: reusable\n\non:\n  workflow_call:\n  workflow_dispatch:\n',
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'cannot expose direct trigger' in str(exc)
        else:
            raise AssertionError('reusable governance workflow gained a direct trigger')
        reusable.write_text(
            'name: reusable\n\non:\n  workflow_call:\n',
            encoding='utf-8',
        )

        legacy = root / '.github/research/continuous-optimization/legacy_semantics_probe.py'
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(
            'import stage_profile_support\nstage_profile_support.install(engine)\n',
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'legacy global semantics consumer remains' in str(exc)
        else:
            raise AssertionError('legacy global semantics mutation consumer was accepted')
        legacy.unlink()

        i002 = root / I002_CONTRACT
        payload = json.loads(i002.read_text(encoding='utf-8'))
        payload['promotion_allowed'] = True
        i002.write_text(json.dumps(payload) + '\n', encoding='utf-8')
        try:
            validate(root)
        except AssertionError as exc:
            assert 'promotion authority' in str(exc)
        else:
            raise AssertionError('scheduled AEC motion validation regained promotion authority')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()

    if not args.self_test and not args.check:
        parser.error('choose --self-test and/or --check')
    if args.self_test:
        self_test()
    if args.check:
        validate()
        print(
            'maintenance workflow contract: generic research manual-only; PR/manual non-shipping workflows '
            'have PR coverage and explicit replay only; historical VAD searches are PR-contract/manual-replay; '
            'consumed algorithm research is contract-only; scheduled workflows exact-allowlisted; '
            'AEC motion schedule bound to terminal zero-budget I002'
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
