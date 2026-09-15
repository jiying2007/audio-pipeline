#!/usr/bin/env python3
from pathlib import Path

workflow = Path('.github/workflows/research-candidate-blind-qualification.yml')
text = workflow.read_text(encoding='utf-8')
old = '''      - name: Partition run-ephemeral blind holdout
        run: |
          set -euo pipefail
          test -n "$AP_EPHEMERAL_HOLDOUT_KEY"
          python3 source/validation/tools/split_holdout.py \\
            --corpus candidate-out/public/corpus.json \\
            --validation-output candidate-out/public/corpus-validation.json \\
            --blind-output candidate-out/public/corpus-blind.json \\
            --holdout-percent "$HOLDOUT" \\
            --key-env AP_EPHEMERAL_HOLDOUT_KEY
          unset AP_EPHEMERAL_HOLDOUT_KEY
          printf 'AP_EPHEMERAL_HOLDOUT_KEY=\\n' >> "$GITHUB_ENV"
'''
new = '''      - name: Partition run-ephemeral blind holdout
        run: |
          set -euo pipefail
          cleanup() {
            unset AP_EPHEMERAL_HOLDOUT_KEY || true
            printf 'AP_EPHEMERAL_HOLDOUT_KEY=\\n' >> "$GITHUB_ENV"
          }
          trap cleanup EXIT
          test -n "$AP_EPHEMERAL_HOLDOUT_KEY"
          python3 source/validation/tools/split_holdout.py \\
            --corpus candidate-out/public/corpus.json \\
            --validation-output candidate-out/public/corpus-validation.json \\
            --blind-output candidate-out/public/corpus-blind.json \\
            --holdout-percent "$HOLDOUT" \\
            --key-env AP_EPHEMERAL_HOLDOUT_KEY
          python3 -c "import json; v=len(json.load(open('candidate-out/public/corpus-validation.json'))['cases']); b=len(json.load(open('candidate-out/public/corpus-blind.json'))['cases']); print(f'holdout partition admission: visible={v} blind={b}'); raise SystemExit(0 if v >= 100 and b >= 16 else 2)"
'''
if old not in text:
    raise SystemExit('expected holdout partition block not found')
text = text.replace(old, new, 1)
marker = "              'jq -r .digest /tmp/research-artifact.json',\n"
addition = marker + "              'trap cleanup EXIT', 'v >= 100 and b >= 16',\n"
if marker not in text:
    raise SystemExit('contract marker insertion point not found')
text = text.replace(marker, addition, 1)
workflow.write_text(text, encoding='utf-8')
