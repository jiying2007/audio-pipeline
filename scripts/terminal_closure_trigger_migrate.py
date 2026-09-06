#!/usr/bin/env python3
from pathlib import Path

# Terminal closure workflows are one-shot evidence gates. After their closure
# contract lands, later plan/program edits must not re-run an old exact-delta gate.
for path, iteration in [
    (Path('.github/workflows/i007-closure.yml'), 'I007'),
    (Path('.github/workflows/i009-closure.yml'), 'I009'),
]:
    s = path.read_text()
    old = f"""  pull_request:\n    paths:\n      - 'docs/program/plan.json'\n      - 'docs/program/iterations/{iteration}-closure.json'\n      - 'scripts/program.py'\n      - '.github/workflows/{iteration.lower()}-closure.yml'\n"""
    new = f"""  pull_request:\n    paths:\n      - 'docs/program/iterations/{iteration}-closure.json'\n"""
    assert s.count(old) == 1, (path, s.count(old))
    path.write_text(s.replace(old, new))

# This closure PR now also repairs the stale I007 trigger, so include that one
# governance file in I009's exact-delta contract without relaxing any evidence.
p = Path('.github/workflows/i009-closure.yml')
s = p.read_text()
old = "allowed='^(docs/program/plan\\.json|docs/program/iterations/I009-closure\\.json|scripts/program\\.py|\\.github/workflows/i009-closure\\.yml)$'"
new = "allowed='^(docs/program/plan\\.json|docs/program/iterations/I009-closure\\.json|scripts/program\\.py|\\.github/workflows/i009-closure\\.yml|\\.github/workflows/i007-closure\\.yml)$'"
assert s.count(old) == 1, s.count(old)
s = s.replace(old, new)
old_count = 'test "$(printf \'%s\\n\' "$changed" | sed \'/^$/d\' | wc -l)" -eq 4'
new_count = 'test "$(printf \'%s\\n\' "$changed" | sed \'/^$/d\' | wc -l)" -eq 5'
assert s.count(old_count) == 1, s.count(old_count)
p.write_text(s.replace(old_count, new_count))
