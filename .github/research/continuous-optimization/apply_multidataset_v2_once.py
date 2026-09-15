#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

root = Path('.')
registry_path = root / '.github/research/continuous-optimization/dataset-registry.json'
workflow_path = root / '.github/workflows/research-optimization.yml'
blind_path = root / '.github/research/continuous-optimization/research_candidate_blind.py'

registry = json.loads(registry_path.read_text(encoding='utf-8'))
by_id = {item['id']: item for item in registry['datasets']}
public_validation = by_id['public-validation']
public_validation['selection_roles'] = []
public_validation['frozen_holdout'] = True
public_validation['notes'] = (
    'Pinned public AEC/DNS/RIR sources are evaluation/holdout data only. '
    'They may reject but never select or rescue research candidates.'
)
if 'public-development-diverse' not in by_id:
    synthetic_index = next(i for i, item in enumerate(registry['datasets']) if item['id'] == 'synthetic-regression')
    registry['datasets'].insert(synthetic_index + 1, {
        'id': 'public-development-diverse',
        'source_kind': 'public',
        'stages': ['ns', 'vad', 'agc', 'pipeline'],
        'lock_path': '.github/research/continuous-optimization/development-v2/development.lock.json',
        'builder_path': None,
        'identity_key': 'catalog_id',
        'identity_value': 'audio-pipeline-public-development-v2',
        'selection_roles': ['development'],
        'evaluation_roles': [],
        'frozen_holdout': False,
        'may_promote_shipping': False,
        'notes': (
            'SHA-256-pinned Mini LibriSpeech + SLR26 RIR + DEMAND development corpus. '
            'Selection-only and archive-disjoint from validation-grade blind inputs; no shipping authority.'
        ),
    })
registry_path.write_text(json.dumps(registry, indent=2) + '\n', encoding='utf-8')

text = workflow_path.read_text(encoding='utf-8')
old = """        default: 'validation/tuning/search-spaces/call-pr-smoke-v1.json'\n        options:\n          - 'validation/tuning/search-spaces/call-pr-smoke-v1.json'\n          - 'validation/tuning/search-spaces/call-v1.json'\n"""
new = """        default: '.github/research/continuous-optimization/development-v2/search-space.json'\n        options:\n          - '.github/research/continuous-optimization/development-v2/search-space.json'\n          - 'validation/tuning/search-spaces/call-pr-smoke-v1.json'\n          - 'validation/tuning/search-spaces/call-v1.json'\n"""
if old not in text:
    raise SystemExit('search_space input anchor missing')
text = text.replace(old, new, 1)

old = """          python3 -m py_compile validation/tools/*.py .github/research/continuous-optimization/*.py\n          python3 -m json.tool \"$RESEARCH_REGISTRY\" >/dev/null\n"""
new = """          python3 -m py_compile validation/tools/*.py .github/research/continuous-optimization/*.py\n          python3 -m py_compile .github/research/continuous-optimization/development-v2/*.py\n          python3 .github/research/continuous-optimization/development-v2/prepare.py --self-test\n          python3 .github/research/continuous-optimization/development-v2/build_corpus.py --self-test\n          python3 -m json.tool .github/research/continuous-optimization/development-v2/development.lock.json >/dev/null\n          python3 -m json.tool .github/research/continuous-optimization/development-v2/policy.json >/dev/null\n          python3 -m json.tool .github/research/continuous-optimization/development-v2/search-space.json >/dev/null\n          python3 -m json.tool \"$RESEARCH_REGISTRY\" >/dev/null\n"""
if old not in text:
    raise SystemExit('contract compile anchor missing')
text = text.replace(old, new, 1)

old = """          assert '4a6a408bf0e3' in {item['candidate_id'] for item in registry['terminal_candidates']}\n          product = next(item for item in registry['datasets'] if item['id'] == 'pcr02-product-external')\n          assert product['selection_roles'] == [] and product['evaluation_roles'] == []\n"""
new = """          terminal_ids = {item['candidate_id'] for item in registry['terminal_candidates']}\n          assert '4a6a408bf0e3' in terminal_ids\n          assert '542ae198199b' in terminal_ids\n          public_validation = next(item for item in registry['datasets'] if item['id'] == 'public-validation')\n          assert public_validation['selection_roles'] == [] and public_validation['frozen_holdout'] is True\n          public_development = next(item for item in registry['datasets'] if item['id'] == 'public-development-diverse')\n          assert public_development['selection_roles'] == ['development']\n          assert public_development['evaluation_roles'] == [] and public_development['frozen_holdout'] is False\n          assert public_development['identity_value'] == 'audio-pipeline-public-development-v2'\n          product = next(item for item in registry['datasets'] if item['id'] == 'pcr02-product-external')\n          assert product['selection_roles'] == [] and product['evaluation_roles'] == []\n"""
if old not in text:
    raise SystemExit('authority boundary anchor missing')
text = text.replace(old, new, 1)

old = """      PYTHONPATH: validation/tools:.github/research/continuous-optimization\n      RESEARCH_REGISTRY: .github/research/continuous-optimization/dataset-registry.json\n    steps:\n"""
new = """      PYTHONPATH: validation/tools:.github/research/continuous-optimization:.github/research/continuous-optimization/development-v2\n      RESEARCH_REGISTRY: .github/research/continuous-optimization/dataset-registry.json\n      DEV_LOCK: .github/research/continuous-optimization/development-v2/development.lock.json\n      DEV_POLICY: .github/research/continuous-optimization/development-v2/policy.json\n      DEV_ROOT: ${{ runner.temp }}/audio-pipeline-development-v2\n    steps:\n"""
# replace only bounded-search env, not contract env
marker = '  bounded-search:\n'
pos = text.index(marker)
prefix, suffix = text[:pos], text[pos:]
if old not in suffix:
    raise SystemExit('bounded-search env anchor missing')
suffix = suffix.replace(old, new, 1)
text = prefix + suffix

old = """      - uses: ./.github/actions/setup-ccache\n        with:\n          namespace: research-optimization\n      - name: Build exact offline tuning processor\n"""
new = """      - uses: ./.github/actions/setup-ccache\n        with:\n          namespace: research-optimization\n      - name: Install public development decoder\n        run: |\n          set -euo pipefail\n          sudo apt-get update -qq\n          sudo apt-get install -y -qq ffmpeg\n          command -v ffmpeg >/dev/null\n      - name: Build exact offline tuning processor\n"""
if old not in text:
    raise SystemExit('ccache anchor missing')
text = text.replace(old, new, 1)

old = """      - name: Materialize exact run specification\n"""
new = """      - name: Materialize diverse public development partitions\n        run: |\n          set -euo pipefail\n          python3 .github/research/continuous-optimization/development-v2/prepare.py \\\n            --lock \"$DEV_LOCK\" --root \"$DEV_ROOT\" --output /tmp/development-v2-materialization.json\n          for seed in 1507 1607; do\n            python3 .github/research/continuous-optimization/development-v2/build_corpus.py \\\n              --lock \"$DEV_LOCK\" \\\n              --materialization /tmp/development-v2-materialization.json \\\n              --data-root \"$DEV_ROOT\" \\\n              --output \"/tmp/development-v2-$seed\" \\\n              --seed \"$seed\" --mix-limit 40 --noise-limit 12 --clean-limit 12\n          done\n      - name: Materialize exact run specification\n"""
if old not in text:
    raise SystemExit('run-spec step anchor missing')
text = text.replace(old, new, 1)

old = """          spec = {\n              'schema_version': 1,\n              'experiment_id': f\"github-{os.environ['GITHUB_RUN_ID']}\",\n              'hypothesis_id': 'joint-runtime-safe-tuning-v1',\n"""
new = """          for seed in [1507, 1607]:\n              evaluations.append({\n                  'evaluation_id': f'public-development-{seed}',\n                  'dataset_id': 'public-development-diverse',\n                  'role': 'development',\n                  'seed': seed,\n                  'corpus': f'/tmp/development-v2-{seed}/corpus.json',\n                  'dataset_lock': '.github/research/continuous-optimization/development-v2/development.lock.json',\n                  'policy': '.github/research/continuous-optimization/development-v2/policy.json',\n              })\n          spec = {\n              'schema_version': 1,\n              'experiment_id': f\"github-{os.environ['GITHUB_RUN_ID']}\",\n              'hypothesis_id': 'multidataset-runtime-safe-tuning-v2',\n"""
if old not in text:
    raise SystemExit('run-spec hypothesis anchor missing')
text = text.replace(old, new, 1)

old = """                  'minimum_development_score': 0.05,\n                  'minimum_development_unit_score': 0.0,\n                  'minimum_distinct_development_seeds': 2,\n"""
new = """                  'minimum_development_score': 0.05,\n                  'minimum_development_unit_score': 0.0,\n                  'minimum_distinct_development_seeds': 4,\n"""
if old not in text:
    raise SystemExit('development seed policy anchor missing')
text = text.replace(old, new, 1)

old = """          path: |\n            /tmp/research-run.json\n            research-optimization-out/\n"""
new = """          path: |\n            /tmp/research-run.json\n            /tmp/development-v2-materialization.json\n            research-optimization-out/\n"""
if old not in text:
    raise SystemExit('artifact path anchor missing')
text = text.replace(old, new, 1)
workflow_path.write_text(text, encoding='utf-8')

blind = blind_path.read_text(encoding='utf-8')
old = """    if not str(provenance[\"search_space_path\"]).startswith(\"validation/tuning/search-spaces/\"):\n        raise ValueError(\"search space path invalid\")\n"""
new = """    search_space_path = str(provenance[\"search_space_path\"])\n    allowed_search_spaces = (\n        search_space_path.startswith(\"validation/tuning/search-spaces/\"),\n        search_space_path == \".github/research/continuous-optimization/development-v2/search-space.json\",\n    )\n    if not any(allowed_search_spaces):\n        raise ValueError(\"search space path invalid\")\n"""
if old not in blind:
    raise SystemExit('blind search-space anchor missing')
blind_path.write_text(blind.replace(old, new, 1), encoding='utf-8')

print('multidataset development v2 integration patch: PASS')
