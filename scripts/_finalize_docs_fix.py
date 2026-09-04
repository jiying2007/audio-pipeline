#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one anchor, found {count}: {old[:100]!r}')
    p.write_text(text.replace(old, new, 1), encoding='utf-8')


# VERSION/CI impact: lifecycle helpers remain release-neutral repository tooling.
replace_once(
    'scripts/ci_impact.py',
    '    "scripts/release_manifest.py", "scripts/post_release_status.py",\n',
    '    "scripts/release_manifest.py", "scripts/post_release_status.py",\n'
    '    "scripts/qualification_fingerprint.py",\n',
)

# Both fast-docs and fast-code assurance surfaces must exercise the fingerprint tool.
p = Path('.github/workflows/verify.yml')
text = p.read_text(encoding='utf-8')
anchor = '          python3 scripts/post_release_status.py --self-test\n'
if text.count(anchor) != 2:
    raise SystemExit(f'verify qualification self-test anchor count drift: {text.count(anchor)}')
text = text.replace(
    anchor,
    anchor + '          python3 scripts/qualification_fingerprint.py --self-test\n',
)
p.write_text(text, encoding='utf-8')

# docs-consistency minimal fixture must be able to opt out of lifecycle assets.
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
required_anchor = '    "scripts/post_release_status.py",\n'
if text.count(required_anchor) != 1:
    raise SystemExit('lifecycle required qualification anchor drift')
text = text.replace(
    required_anchor,
    required_anchor + '    "scripts/qualification_fingerprint.py",\n',
    1,
)
tools_anchor = "    for tool in ('research_registry.py', 'prepare_release.py', 'release_manifest.py', 'post_release_status.py'):\n"
if text.count(tools_anchor) != 1:
    raise SystemExit('lifecycle self-test tool tuple drift')
text = text.replace(
    tools_anchor,
    "    for tool in ('research_registry.py', 'prepare_release.py', 'release_manifest.py', 'post_release_status.py', 'qualification_fingerprint.py'):\n",
    1,
)
p.write_text(text, encoding='utf-8')
print('lifecycle assurance integration fix: OK')
