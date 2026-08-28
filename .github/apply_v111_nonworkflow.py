#!/usr/bin/env python3
from pathlib import Path

workflow_dir = Path('.github/workflows')
workflow_snapshot = {
    p.relative_to(workflow_dir): p.read_bytes()
    for p in workflow_dir.rglob('*') if p.is_file()
}

patch_script = Path('.github/apply_v111.py')
source = patch_script.read_text(encoding='utf-8')
exec(compile(source, str(patch_script), 'exec'), {'__name__': '__main__'})

# GITHUB_TOKEN intentionally has no workflows write permission. Restore the
# workflow tree exactly; the GitHub connector will apply those reviewed changes.
for p in sorted(workflow_dir.rglob('*'), reverse=True):
    if p.is_file():
        p.unlink()
for rel, data in workflow_snapshot.items():
    p = workflow_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)

# Keep no bootstrap scripts in the resulting product commit.
Path('.github/apply_v111.py').unlink(missing_ok=True)
Path('.github/apply_v111_nonworkflow.py').unlink(missing_ok=True)
