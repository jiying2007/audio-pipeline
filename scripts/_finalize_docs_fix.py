#!/usr/bin/env python3
from pathlib import Path

p = Path('scripts/docs_consistency.py')
text = p.read_text(encoding='utf-8')
old = '''def validate(root: Path, *, require_lab: bool = True,
             require_validation: bool = True,
             require_supply_chain: bool = True) -> list[str]:
'''
new = '''def validate(root: Path, *, require_lab: bool = True,
             require_validation: bool = True,
             require_supply_chain: bool = True,
             require_lifecycle: bool = True) -> list[str]:
'''
if text.count(old) != 1:
    raise SystemExit('docs consistency validate signature drift')
text = text.replace(old, new, 1)
old = '''    if require_lab:
        validate_lab(root, errors)
    validate_lifecycle(root, errors)
    return errors
'''
new = '''    if require_lab:
        validate_lab(root, errors)
    if require_lifecycle:
        validate_lifecycle(root, errors)
    return errors
'''
if text.count(old) != 1:
    raise SystemExit('docs consistency lifecycle call drift')
text = text.replace(old, new, 1)
fixture = 'root, require_lab=False, require_validation=False, require_supply_chain=False\n'
if text.count(fixture) != 2:
    raise SystemExit('docs consistency self-test fixture count drift')
text = text.replace(
    fixture,
    'root, require_lab=False, require_validation=False, require_supply_chain=False,\n            require_lifecycle=False\n',
)
p.write_text(text, encoding='utf-8')
print('docs consistency lifecycle fixture fix: OK')
