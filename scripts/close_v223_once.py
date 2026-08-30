#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old!r}")
    p.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "CMakeLists.txt",
    "project(audio_pipeline VERSION 2.2.2 LANGUAGES C)",
    "project(audio_pipeline VERSION 2.2.3 LANGUAGES C)",
)

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
if not text.startswith("# 2.2.2\n"):
    raise SystemExit("CHANGELOG top version is not 2.2.2")
prefix = """# 2.2.3

- Make Extended Real automation leave the dataset root unresolved until the `audio-validation` runner executes; blank input resolves to `AUDIO_PIPELINE_LAB_DATA_ROOT` or `$HOME/audio-validation-extended`.
- Make HIL blank `board_manifest` resolve on the `audio-target` runner through `AUDIO_PIPELINE_LAB_BOARD`, XDG config, or `$HOME/.config/audio-pipeline/board.json` instead of a hard-coded `/etc` path.
- Make `labctl.py dispatch-validation` and `dispatch-hil` avoid leaking the operator machine's HOME paths into a different self-hosted runner unless an explicit path override is supplied.
- Preserve explicit system-mode `/opt`/`/etc` overrides and keep DSP/API/ABI, dataset hashes/licenses, acoustic thresholds, HIL thresholds and Product Certification authority unchanged.

"""
changelog.write_text(prefix + text, encoding="utf-8")

labctl = Path("lab/scripts/labctl.py")
text = labctl.read_text(encoding="utf-8")
old = '''def dispatch_validation(source_revision: str, profile: str, data_root: Path, repo: str) -> None:
    require_command("gh")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_revision):
        raise ValueError("source_revision must be exact 40-hex commit SHA")
    run([
        "gh", "workflow", "run", "validation-extended-real.yml", "--repo", repo, "--ref", "main",
        "-f", f"source_sha={source_revision.lower()}", "-f", f"profile={profile}",
        "-f", f"data_root={data_root}", "-f", "limit_per_dataset=48",
        "-f", "direct_limit=24", "-f", "derived_limit=16", "-f", "holdout_percent=20",
    ])


def dispatch_hil(source_revision: str, repo: str, board: Path, capture: str, playback: str,
                 farend: str, power: str, tier: str) -> None:
    require_command("gh")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_revision):
        raise ValueError("source_revision must be exact 40-hex commit SHA")
    run([
        "gh", "workflow", "run", "hil-soak.yml", "--repo", repo, "--ref", "main",
        "-f", f"source_sha={source_revision.lower()}", "-f", f"tier={tier}",
        "-f", f"board_manifest={board}", "-f", f"capture_device={capture}",
        "-f", f"playback_device={playback}", "-f", f"farend_file={farend}",
        "-f", "sample_rate=16000", "-f", "mic_channels=2", "-f", "dsp_cpu=1",
        "-f", f"power_input={power}", "-f", "power_scale=1000000",
    ])
'''
new = '''def dispatch_validation(source_revision: str, profile: str, data_root: Path | None, repo: str) -> None:
    require_command("gh")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_revision):
        raise ValueError("source_revision must be exact 40-hex commit SHA")
    run([
        "gh", "workflow", "run", "validation-extended-real.yml", "--repo", repo, "--ref", "main",
        "-f", f"source_sha={source_revision.lower()}", "-f", f"profile={profile}",
        "-f", f"data_root={data_root if data_root is not None else ''}", "-f", "limit_per_dataset=48",
        "-f", "direct_limit=24", "-f", "derived_limit=16", "-f", "holdout_percent=20",
    ])


def dispatch_hil(source_revision: str, repo: str, board: Path | None, capture: str, playback: str,
                 farend: str, power: str, tier: str) -> None:
    require_command("gh")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_revision):
        raise ValueError("source_revision must be exact 40-hex commit SHA")
    run([
        "gh", "workflow", "run", "hil-soak.yml", "--repo", repo, "--ref", "main",
        "-f", f"source_sha={source_revision.lower()}", "-f", f"tier={tier}",
        "-f", f"board_manifest={board if board is not None else ''}", "-f", f"capture_device={capture}",
        "-f", f"playback_device={playback}", "-f", f"farend_file={farend}",
        "-f", "sample_rate=16000", "-f", "mic_channels=2", "-f", "dsp_cpu=1",
        "-f", f"power_input={power}", "-f", "power_scale=1000000",
    ])
'''
if text.count(old) != 1:
    raise SystemExit("labctl dispatch function anchor drifted")
text = text.replace(old, new)
replace_map = {
    'dv.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)': 'dv.add_argument("--data-root", type=Path)',
    'dh.add_argument("--board", type=Path, default=DEFAULT_BOARD)': 'dh.add_argument("--board", type=Path)',
}
for before, after in replace_map.items():
    if text.count(before) != 1:
        raise SystemExit(f"labctl parser anchor drifted: {before}")
    text = text.replace(before, after)
marker = '    for current in (DEFAULT_DATA_ROOT, DEFAULT_CACHE_ROOT, DEFAULT_STATE_ROOT, DEFAULT_BOARD):\n        assert current.is_absolute()\n'
addition = marker + '''    dispatch_validation_args = parser().parse_args(["dispatch-validation", "--source-revision", "0" * 40])
    assert dispatch_validation_args.data_root is None
    dispatch_hil_args = parser().parse_args(["dispatch-hil", "--source-revision", "0" * 40, "--capture", "hw:0,0"])
    assert dispatch_hil_args.board is None
'''
if text.count(marker) != 1:
    raise SystemExit("labctl self-test anchor drifted")
labctl.write_text(text.replace(marker, addition), encoding="utf-8")

readme = Path("lab/README.md")
text = readme.read_text(encoding="utf-8")
replacements = [
    (
        '''sudo -u audio-ci /opt/audio-lab/venv/bin/python lab/scripts/labctl.py verify-profile \\
  --profile commercial-core \\
  --data-root $HOME/audio-validation-extended \\
  --source-revision "$SHA"''',
        '''$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py verify-profile \\
  --profile commercial-core \\
  --source-revision "$SHA"''',
    ),
    (
        '''python3 lab/scripts/labctl.py dispatch-validation \\
  --source-revision "$SHA" \\
  --profile commercial-core \\
  --data-root $HOME/audio-validation-extended''',
        '''python3 lab/scripts/labctl.py dispatch-validation \\
  --source-revision "$SHA" \\
  --profile commercial-core''',
    ),
    ('''EXTENDED_REAL_ENABLED=true
EXTENDED_REAL_DATA_ROOT=$HOME/audio-validation-extended''', '''EXTENDED_REAL_ENABLED=true'''),
    (
        '''At that point post-release automation runs `commercial-core` and the weekly automation runs `commercial-plus`.''',
        '''At that point post-release automation runs `commercial-core` and the weekly automation runs `commercial-plus`. With no `EXTENDED_REAL_DATA_ROOT` repository variable, the workflow deliberately resolves `$HOME/audio-validation-extended` on the `audio-validation` runner itself. Set `EXTENDED_REAL_DATA_ROOT` only when that runner uses an explicit non-default/system-mode location.''',
    ),
    (
        '''python3 lab/scripts/labctl.py dispatch-hil \\
  --source-revision "$SHA" \\
  --tier accelerated-pr \\
  --board $HOME/.config/audio-pipeline/board.json \\
  --capture '<controller-visible-capture-device>' \\
''',
        '''python3 lab/scripts/labctl.py dispatch-hil \\
  --source-revision "$SHA" \\
  --tier accelerated-pr \\
  --capture '<controller-visible-capture-device>' \\
''',
    ),
    (
        '''Do not set `HIL_ENABLED=true` until repeated manual accelerated runs demonstrate that the controller, DUT route, power-cycle/cleanup hooks and sensors are actually healthy.''',
        '''When `--board` is omitted, the HIL workflow resolves `AUDIO_PIPELINE_LAB_BOARD`, then XDG config, then `$HOME/.config/audio-pipeline/board.json` on the `audio-target` runner. Use `--board` only for an explicit runner-local override.

Do not set `HIL_ENABLED=true` until repeated manual accelerated runs demonstrate that the controller, DUT route, power-cycle/cleanup hooks and sensors are actually healthy.''',
    ),
]
for before, after in replacements:
    count = text.count(before)
    if count != 1:
        raise SystemExit(f"lab README anchor drifted ({count}): {before[:80]!r}")
    text = text.replace(before, after)
readme.write_text(text, encoding="utf-8")

docs = Path("scripts/docs_consistency.py")
text = docs.read_text(encoding="utf-8")
before = '    "lab/examples/board.ssc305.example.json",\n)'
after = '    "lab/examples/board.ssc305.example.json",\n    ".github/workflows/extended-real-automation.yml",\n    ".github/workflows/validation-extended-real.yml",\n    ".github/workflows/hil-soak.yml",\n)'
if text.count(before) != 1:
    raise SystemExit("docs_consistency LAB_REQUIRED anchor drifted")
text = text.replace(before, after)
anchor = '''    if read(root, "lab/requirements-ansible.txt").strip() != "ansible-core==2.19.12":
        errors.append("lab Ansible dependency pin drift")
'''
extra = anchor + '''    extended_auto = read(root, ".github/workflows/extended-real-automation.yml")
    extended = read(root, ".github/workflows/validation-extended-real.yml")
    hil = read(root, ".github/workflows/hil-soak.yml")
    if "/opt/audio-validation-extended" in extended_auto or "/opt/audio-validation-extended" in extended:
        errors.append("extended-real workflow reintroduced a system-mode /opt default")
    for token in ("AUDIO_PIPELINE_LAB_DATA_ROOT", "$HOME/audio-validation-extended"):
        if token not in extended:
            errors.append(f"extended-real workflow missing runner-local user-mode token: {token}")
    if "default: /etc/audio-pipeline/board.json" in hil:
        errors.append("HIL workflow reintroduced a system-mode /etc board default")
    for token in ("AUDIO_PIPELINE_LAB_BOARD", "XDG_CONFIG_HOME", "$HOME/.config"):
        if token not in hil:
            errors.append(f"HIL workflow missing runner-local user-mode token: {token}")
'''
if text.count(anchor) != 1:
    raise SystemExit("docs_consistency lab anchor drifted")
docs.write_text(text.replace(anchor, extra), encoding="utf-8")
