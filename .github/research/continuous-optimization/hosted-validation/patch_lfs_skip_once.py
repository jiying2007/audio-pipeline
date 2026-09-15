#!/usr/bin/env python3
from pathlib import Path

path = Path('.github/research/continuous-optimization/hosted-validation/prepare_full_validation.py')
text = path.read_text(encoding='utf-8')
old = '''def run(command: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:\n    result = subprocess.run(\n        command,\n        cwd=str(cwd) if cwd else None,\n        check=True,\n        text=True,\n        stdout=subprocess.PIPE if capture else None,\n    )\n'''
new = '''def run(command: list[str], *, cwd: Path | None = None, capture: bool = False,\n        env: dict[str, str] | None = None) -> str:\n    result = subprocess.run(\n        command,\n        cwd=str(cwd) if cwd else None,\n        check=True,\n        text=True,\n        stdout=subprocess.PIPE if capture else None,\n        env=env,\n    )\n'''
if old not in text:
    raise SystemExit('run helper anchor missing')
text = text.replace(old, new, 1)
old = '''    run([\n        sys.executable, str(fetch), "--lock", str(source_lock_path), "--root", str(data_root),\n        "--dataset", "microsoft-aec-challenge",\n    ], cwd=source_root)\n'''
new = '''    metadata_env = dict(os.environ)\n    metadata_env["GIT_LFS_SKIP_SMUDGE"] = "1"\n    run([\n        sys.executable, str(fetch), "--lock", str(source_lock_path), "--root", str(data_root),\n        "--dataset", "microsoft-aec-challenge",\n    ], cwd=source_root, env=metadata_env)\n'''
if old not in text:
    raise SystemExit('AEC fetch anchor missing')
text = text.replace(old, new, 1)
old = 'import json\nimport shutil\n'
new = 'import json\nimport os\nimport shutil\n'
if old not in text:
    raise SystemExit('import anchor missing')
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
