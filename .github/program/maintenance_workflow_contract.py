#!/usr/bin/env python3
"""Fail-closed workflow contract for the software-commercial-ready maintenance state."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = Path('.github/workflows')

# The generic tuner has no PR-regression role and is therefore manual-only after
# the terminal software program. Stage-specific research workflows keep their PR
# regression coverage and explicit manual replay entry points, but must never run
# autonomous scheduled or push-triggered candidate research in maintenance state.
MANUAL_ONLY_RESEARCH_WORKFLOWS = (
    Path('.github/workflows/acoustic-tuning-iteration.yml'),
)
PR_MANUAL_RESEARCH_WORKFLOWS = (
    Path('.github/workflows/aec-motion-tuning.yml'),
    Path('.github/workflows/agc-stage-tuning.yml'),
    Path('.github/workflows/ns-stage-tuning.yml'),
    Path('.github/workflows/ami-vad-microset-discovery.yml'),
    Path('.github/workflows/vad-operating-point-selector.yml'),
    Path('.github/workflows/vad-hangover-counterfactual.yml'),
    Path('.github/workflows/vad-strong-weak-refresh.yml'),
)

# Recurring execution is an explicit maintenance capability, not a default.
# Every legal cron below is validation, data-integrity, HIL or qualification
# convergence work. Candidate/research search is intentionally absent.
ALLOWED_SCHEDULED_WORKFLOWS = {
    Path('.github/workflows/aec-motion-development.yml'): ('41 18 * * 2,5',),
    Path('.github/workflows/extended-real-automation.yml'): ('17 3 * * 0',),
    Path('.github/workflows/hil-soak.yml'): ('43 18 * * *', '17 17 * * 0'),
    Path('.github/workflows/hosted-aec-real-validation.yml'): ('23 18 * * *',),
    Path('.github/workflows/hosted-real-validation.yml'): ('47 18 * * *',),
    Path('.github/workflows/lab-acquisition-smoke.yml'): ('23 3 * * 3',),
    Path('.github/workflows/nightly.yml'): ('17 19 * * *',),
    Path('.github/workflows/post-release-qualification-summary.yml'): ('23 * * * *',),
}
CRON_RE = re.compile(r"^    - cron:\s*['\"]([^'\"]+)['\"]\s*$", re.MULTILINE)


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


def validate(root: Path = REPOSITORY_ROOT) -> None:
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
        assert path.is_file(), f'missing stage research workflow: {relative}'
        text = path.read_text(encoding='utf-8')
        assert '\n  pull_request:' in text, f'{relative} must retain PR regression coverage'
        assert '\n  workflow_dispatch:' in text, f'{relative} must retain an explicit manual replay entry point'
        assert '\n  schedule:' not in text, f'{relative} must not run autonomous scheduled research in maintenance state'
        assert '\n  push:' not in text, f'{relative} must not run autonomous push research in maintenance state'

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


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        generic = root / MANUAL_ONLY_RESEARCH_WORKFLOWS[0]
        generic.parent.mkdir(parents=True)
        generic.write_text('name: generic\n\non:\n  workflow_dispatch:\n', encoding='utf-8')
        for relative in PR_MANUAL_RESEARCH_WORKFLOWS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                'name: stage\n\non:\n  pull_request:\n  workflow_dispatch:\n',
                encoding='utf-8',
            )
        for relative, crons in ALLOWED_SCHEDULED_WORKFLOWS.items():
            _write_allowed_schedule(root / relative, crons)
        validate(root)

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

        stage = root / PR_MANUAL_RESEARCH_WORKFLOWS[0]
        stage.write_text(
            "name: stage\n\non:\n  pull_request:\n  schedule:\n    - cron: '17 19 * * *'\n  workflow_dispatch:\n",
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'scheduled research' in str(exc)
        else:
            raise AssertionError('scheduled stage research workflow was not rejected')

        stage.write_text('name: stage\n\non:\n  workflow_dispatch:\n', encoding='utf-8')
        try:
            validate(root)
        except AssertionError as exc:
            assert 'PR regression coverage' in str(exc)
        else:
            raise AssertionError('stage research workflow without PR coverage was not rejected')


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
            'maintenance workflow contract: generic research manual-only; stage research PR/manual-only; '
            'scheduled workflows exact-allowlisted'
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
