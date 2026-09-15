#!/usr/bin/env python3
from pathlib import Path

path = Path('.github/workflows/research-candidate-blind-qualification.yml')
text = path.read_text(encoding='utf-8')
anchor = '''          python3 source/validation/tools/prepare_public_validation.py verify \\
            --profile full --root "$DATA_ROOT" --seal "$SEAL" --dns-data-root "$DNS_ROOT" \\
            > candidate-out/dataset-verification.json
'''
replacement = '''          python3 source/validation/tools/prepare_public_validation.py verify \\
            --lock source/validation/datasets.lock.json \\
            --profile full --root "$DATA_ROOT" --seal "$SEAL" --dns-data-root "$DNS_ROOT" \\
            > candidate-out/dataset-verification.json
'''
if anchor not in text:
    raise SystemExit('standalone full verify anchor missing')
text = text.replace(anchor, replacement, 1)
contract_anchor = "              'candidate-out/github-hosted-progress.json',\n"
contract_marker = "              'prepare_public_validation.py verify',\n              '--lock source/validation/datasets.lock.json',\n"
if contract_anchor not in text:
    raise SystemExit('contract anchor missing')
if "              'prepare_public_validation.py verify',\n" not in text:
    text = text.replace(contract_anchor, contract_anchor + contract_marker, 1)
path.write_text(text, encoding='utf-8')
