#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

CANDIDATE_ID = "542ae198199b"
RESEARCH_ID = "f5ad7c495d7f67d6"
SOURCE_SHA = "01c7e0adf3ec9bcb1d401540c5e9d209176bd9ef"
MAIN_SHA = "a1a5041790acbbe54561ae06e07fa1aed9fa5acf"
RUN_ID = 34932084718
JOB_ID = 104262276947
ARTIFACT_ID = 10382241748
ARTIFACT_NAME = "research-candidate-blind-f5ad7c495d7f67d6-34932084718"
ARTIFACT_DIGEST = "sha256:cc1dc6f4df362bb1070d608484ae45b6a193b9eaf7d10bc37ce816ddbc4d4802"

root = Path('.')
active = root / '.github/research/continuous-optimization/candidates/f5ad7c495d7f67d6.json'
terminal_dir = root / '.github/research/continuous-optimization/terminal-candidates'
terminal = terminal_dir / 'f5ad7c495d7f67d6.json'
registry_path = root / '.github/research/continuous-optimization/dataset-registry.json'
workflow_path = root / '.github/workflows/research-candidate-blind-qualification.yml'

manifest = json.loads(active.read_text(encoding='utf-8'))
assert manifest['candidate_id'] == CANDIDATE_ID
assert manifest['research_candidate_id'] == RESEARCH_ID
assert manifest['source_sha'] == SOURCE_SHA
assert manifest['status'] == 'FROZEN_RESEARCH_CANDIDATE'

verdict = {
    'schema_version': 1,
    'status': 'BLIND_REJECTED_NON_SHIPPING',
    'next_gate': None,
    'terminal_candidate': True,
    'research_candidate_id': RESEARCH_ID,
    'candidate_id': CANDIDATE_ID,
    'source_sha': SOURCE_SHA,
    'hypothesis_id': manifest['hypothesis_id'],
    'tuning': manifest['tuning'],
    'failed_stage': 'visible-validation',
    'visible_result': 'FAIL',
    'blind_result': None,
    'qualification_provenance': {
        'workflow': 'Research Candidate Blind Qualification',
        'run_id': RUN_ID,
        'job_id': JOB_ID,
        'head_sha': MAIN_SHA,
        'artifact_id': ARTIFACT_ID,
        'artifact_name': ARTIFACT_NAME,
        'artifact_digest': ARTIFACT_DIGEST,
    },
    'visible_gate_violations': [
        {
            'gate': 'min_median_near_si_sdr_improvement_db',
            'metric': 'median_near_si_sdr_improvement_db',
            'actual': -0.21302848600074853,
            'expected_min': 0.0,
        },
        {
            'gate': 'min_median_output_render_corr_reduction',
            'metric': 'median_output_render_corr_reduction',
            'actual': 0.001330810077271048,
            'expected_min': 0.05,
        },
        {
            'gate': 'min_vad_f1',
            'metric': 'min_vad_f1',
            'actual': 0.30326295585412666,
            'expected_min': 0.8,
        },
    ],
    'output_authority': {
        'shipping_authority': False,
        'target_execution_authority': False,
        'hil_authority': False,
        'product_certification_authority': False,
        'automatic_main_mutation': False,
    },
    'rule': (
        'Explicit visible validation FAIL is terminal for this exact tuning identity. '
        'The candidate may not be retried, reselected, promoted, or used to change shipping.'
    ),
}
terminal_dir.mkdir(parents=True, exist_ok=True)
terminal.write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n', encoding='utf-8')
active.unlink()

registry = json.loads(registry_path.read_text(encoding='utf-8'))
terminal_candidates = registry['terminal_candidates']
if any(item['candidate_id'] == CANDIDATE_ID for item in terminal_candidates):
    raise SystemExit('candidate already terminal in registry')
terminal_candidates.append({
    'candidate_id': CANDIDATE_ID,
    'source_sha': SOURCE_SHA,
    'decision': 'BLIND_REJECTED_NON_SHIPPING',
})
registry_path.write_text(json.dumps(registry, indent=2) + '\n', encoding='utf-8')

workflow = workflow_path.read_text(encoding='utf-8')
path_anchor = "      - '.github/research/continuous-optimization/candidates/**'\n"
path_insert = (
    path_anchor
    + "      - '.github/research/continuous-optimization/terminal-candidates/**'\n"
    + "      - '.github/research/continuous-optimization/dataset-registry.json'\n"
)
if path_anchor not in workflow:
    raise SystemExit('candidate path trigger anchor missing')
workflow = workflow.replace(path_anchor, path_insert, 1)
nonempty_guard = '          test "${#manifests[@]}" -gt 0\n'
if nonempty_guard not in workflow:
    raise SystemExit('active candidate non-empty guard missing')
workflow = workflow.replace(nonempty_guard, '', 1)
workflow_path.write_text(workflow, encoding='utf-8')

# Fail-closed local assertions for the generated terminal state.
assert not active.exists()
archived = json.loads(terminal.read_text(encoding='utf-8'))
assert archived['status'] == 'BLIND_REJECTED_NON_SHIPPING'
assert archived['terminal_candidate'] is True
assert archived['next_gate'] is None
assert archived['visible_result'] == 'FAIL'
assert archived['blind_result'] is None
assert archived['qualification_provenance']['artifact_digest'] == ARTIFACT_DIGEST
assert archived['output_authority'] == verdict['output_authority']
registry2 = json.loads(registry_path.read_text(encoding='utf-8'))
matches = [x for x in registry2['terminal_candidates'] if x['candidate_id'] == CANDIDATE_ID]
assert matches == [{
    'candidate_id': CANDIDATE_ID,
    'source_sha': SOURCE_SHA,
    'decision': 'BLIND_REJECTED_NON_SHIPPING',
}]
workflow2 = workflow_path.read_text(encoding='utf-8')
assert "terminal-candidates/**" in workflow2
assert "dataset-registry.json" in workflow2
assert nonempty_guard not in workflow2
print('terminal blind candidate lifecycle archive: PASS')
