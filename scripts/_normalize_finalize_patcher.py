#!/usr/bin/env python3
from pathlib import Path

path = Path('scripts/_finalize_framework_lifecycle.py')
text = path.read_text(encoding='utf-8')
function_anchor = '\n\ndef append_once(path: str, marker: str, addition: str) -> None:\n'
helper = '''\n\ndef replace_exact_two(path: str, old: str, new: str) -> None:\n    p = Path(path)\n    text = p.read_text(encoding="utf-8")\n    count = text.count(old)\n    if count != 2:\n        raise SystemExit(f"{path}: expected two anchors, found {count}: {old[:120]!r}")\n    p.write_text(text.replace(old, new), encoding="utf-8")\n'''
if function_anchor not in text:
    raise SystemExit('temporary patcher helper anchor missing')
text = text.replace(function_anchor, helper + function_anchor, 1)
call_anchor = 'replace_once(\n    ".github/workflows/verify.yml",\n'
if text.count(call_anchor) != 1:
    raise SystemExit('verify patch call anchor drift')
text = text.replace(call_anchor, 'replace_exact_two(\n    ".github/workflows/verify.yml",\n', 1)
path.write_text(text, encoding='utf-8')
print('finalize patcher normalization: OK')
