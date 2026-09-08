#!/usr/bin/env python3
"""Fail-closed workflow contract for the software-commercial-ready maintenance state."""

from __future__ import annotations

import argparse
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANUAL_ONLY_RESEARCH_WORKFLOWS = (
    Path('.github/workflows/acoustic-tuning-iteration.yml'),
)


def validate(root: Path = REPOSITORY_ROOT) -> None:
    for relative in MANUAL_ONLY_RESEARCH_WORKFLOWS:
        path = root / relative
        assert path.is_file(), f'missing maintenance research workflow: {relative}'
        text = path.read_text(encoding='utf-8')
        assert '\n  workflow_dispatch:' in text, f'{relative} must retain an explicit manual entry point'
        assert '\n  schedule:' not in text, f'{relative} must not run autonomous scheduled research in maintenance state'
        assert '\n  push:' not in text, f'{relative} must not run autonomous push research in maintenance state'
        assert '\n  pull_request:' not in text, f'{relative} is the generic search entry point and must remain manual-only'


def self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workflow = root / MANUAL_ONLY_RESEARCH_WORKFLOWS[0]
        workflow.parent.mkdir(parents=True)
        workflow.write_text('name: test\n\non:\n  workflow_dispatch:\n', encoding='utf-8')
        validate(root)

        workflow.write_text(
            "name: test\n\non:\n  schedule:\n    - cron: '17 19 * * *'\n  workflow_dispatch:\n",
            encoding='utf-8',
        )
        try:
            validate(root)
        except AssertionError as exc:
            assert 'scheduled research' in str(exc)
        else:
            raise AssertionError('scheduled research workflow was not rejected')


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
        print('maintenance workflow contract: generic acoustic tuning is manual-only')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
