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
    Path('.github/workflows/bf-hard-mic-fault-base-replay.yml'),
    Path('.github/workflows/dsp-data-research.yml'),
    Path('.github/workflows/pcr02-aec-real-tail-confirmation.yml'),
    Path('.github/workflows/pcr02-dsp-counterfactuals.yml'),
    Path('.github/workflows/research-optimization.yml'),
    Path('.github/workflows/research-algorithm-parameter-optimization.yml'),
    Path('.github/workflows/research-candidate-blind-qualification.yml'),
    Path('.github/workflows/research-stage-lane-optimization.yml'),
    Path('.github/workflows/research-source-authority-v2-qualification.yml'),
)

# Recurring execution is an explicit maintenance capability, not a default.
# Every legal cron below is validation, data-integrity, HIL or qualification
# convergence work. Candidate/research search is intentionally absent.
ALLOWED_SCHEDULED_WORKFLOWS = {
    AEC_MOTION_MAINTENANCE_WORKFLOW: ('41 18 * * 2,5',),
    Path('.github/workflows/extended-real-automation.yml'): ('17 3 * * 0',),
    Path('.github/workflows/hil-soak.yml'): ('43 18 * * *', '17 17 * * 0'),
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


def validate_no_legacy_semantics_consumers(root: Path) -> None:
    for pattern in LEGACY_SEMANTICS_GLOBS:
        for path in sorted(root.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            for token in LEGACY_SEMANTICS_TOKENS:
                assert token not in text, (
                    f"legacy global semantics consumer remains: "
                    f"{path.relative_to(root)}: {token}"
                )


def validate(root: Path = REPOSITORY_ROOT) -> None:
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
        assert '\n  workflow_dispatch:' in text, f'{relative} must retain an explicit manual replay entry point'
        assert '\n  schedule:' not in text, f'{relative} must not run autonomous scheduled non-shipping work in maintenance state'
        assert '\n  push:' not in text, f'{relative} must not run autonomous push non-shipping work in maintenance state'
        pull_request = trigger_block(text, 'pull_request')
        assert MAINTENANCE_CONTRACT_TRIGGER_PATH not in pull_request, (
            f'{relative} must not fan out on maintenance contract edits; Program Archive owns that validation'
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
        _write_i002_terminal_fixture(root)
        generic = root / MANUAL_ONLY_RESEARCH_WORKFLOWS[0]
        generic.parent.mkdir(parents=True)
        generic.write_text('name: generic\n\non:\n  workflow_dispatch:\n', encoding='utf-8')
        for relative in PR_MANUAL_RESEARCH_WORKFLOWS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
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
        validate(root)

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

        nonshipping = root / PR_MANUAL_RESEARCH_WORKFLOWS[0]
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
            'have PR coverage and explicit replay only; scheduled workflows exact-allowlisted; '
            'AEC motion schedule bound to terminal zero-budget I002'
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
