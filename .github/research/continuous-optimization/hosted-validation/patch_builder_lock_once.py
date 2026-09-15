#!/usr/bin/env python3
from pathlib import Path

PROBE = Path('.github/workflows/github-hosted-full-cache-probe.yml')
FORMAL = Path('.github/workflows/research-candidate-blind-qualification.yml')


def patch_builder(path: Path, formal: bool) -> None:
    text = path.read_text(encoding='utf-8')
    anchor = '          python3 source/validation/tools/build_full_public_corpus.py \\\n            --data-root '
    replacement = '          python3 source/validation/tools/build_full_public_corpus.py \\\n            --lock source/validation/datasets.lock.json \\\n            --data-root '
    if anchor not in text:
        raise SystemExit(f'builder lock anchor missing: {path}')
    text = text.replace(anchor, replacement, 1)
    if formal:
        marker = "              'candidate-out/github-hosted-progress.json',\n"
        if marker not in text:
            raise SystemExit('formal contract marker anchor missing')
        text = text.replace(
            marker,
            marker + "              '--lock source/validation/datasets.lock.json',\n",
            1,
        )
    path.write_text(text, encoding='utf-8')


patch_builder(PROBE, False)
patch_builder(FORMAL, True)
