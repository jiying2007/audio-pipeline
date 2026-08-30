#!/usr/bin/env python3
from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} occurrences, found {actual}: {old!r}")
    p.write_text(text.replace(old, new), encoding="utf-8")


replace("CMakeLists.txt", "project(audio_pipeline VERSION 2.2.3 LANGUAGES C)", "project(audio_pipeline VERSION 2.2.4 LANGUAGES C)")
changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
if not text.startswith("# 2.2.3\n"):
    raise SystemExit("unexpected CHANGELOG head")
changelog.write_text(
    "# 2.2.4\n\n"
    "- Complete ordinary-user trusted-runner readiness defaults: blank public-validation cache/seal paths now resolve on `audio-validation` under `$HOME/audio-validation-data`, and blank target board manifests resolve through `AUDIO_PIPELINE_LAB_BOARD`, XDG config or `$HOME/.config/audio-pipeline/board.json`.\n"
    "- Complete ordinary-user Product Certification target setup: blank `board_manifest` resolves only on the `audio-target` runner through the same runner-local board-path chain; explicit absolute system-mode paths remain supported.\n"
    "- Extend permanent documentation/lab assurance contracts so `/opt`/`/etc` cannot silently return as readiness/certification defaults. No DSP/API/ABI, acoustic/resource/HIL thresholds, dataset hashes/licenses or certification authority changed.\n\n"
    + text,
    encoding="utf-8",
)

# Trusted Runner Readiness: blank public cache/seal and target board paths resolve on each self-hosted runner.
replace(
    ".github/workflows/trusted-runner-readiness.yml",
    """      data_root:
        description: audio-validation sealed cache root
        required: false
        default: /opt/audio-validation-data
        type: string
      seal_path:
        description: audio-validation dataset seal
        required: false
        default: /opt/audio-validation-data/datasets.seal.json
        type: string""",
    """      data_root:
        description: Optional public-validation cache root; blank uses $HOME/audio-validation-data on audio-validation
        required: false
        default: ''
        type: string
      seal_path:
        description: Optional public-validation dataset seal; blank uses <resolved-data-root>/datasets.seal.json
        required: false
        default: ''
        type: string""",
)
replace(
    ".github/workflows/trusted-runner-readiness.yml",
    """      board_manifest:
        description: audio-target board manifest when available
        required: false
        default: /etc/audio-pipeline/board.json
        type: string""",
    """      board_manifest:
        description: Optional audio-target board manifest; blank resolves AUDIO_PIPELINE_LAB_BOARD or XDG/HOME user-mode path
        required: false
        default: ''
        type: string""",
)
replace(
    ".github/workflows/trusted-runner-readiness.yml",
    """      - name: Check audio-validation readiness
        env:
          DATA_ROOT: ${{ inputs.data_root }}
          SEAL: ${{ inputs.seal_path }}
          DNS_ROOT: ${{ inputs.dns_data_root }}
        run: |
          set -euo pipefail
          args=(
            --role audio-validation
            --source-revision '${{ needs.resolve.outputs.sha }}'
            --data-root \"$DATA_ROOT\" --seal \"$SEAL\"""",
    """      - name: Check audio-validation readiness
        env:
          INPUT_DATA_ROOT: ${{ inputs.data_root }}
          INPUT_SEAL: ${{ inputs.seal_path }}
          DNS_ROOT: ${{ inputs.dns_data_root }}
        run: |
          set -euo pipefail
          DATA_ROOT=${INPUT_DATA_ROOT:-$HOME/audio-validation-data}
          SEAL=${INPUT_SEAL:-$DATA_ROOT/datasets.seal.json}
          for value in \"$DATA_ROOT\" \"$SEAL\"; do
            case \"$value\" in /*) ;; *) echo \"readiness path must resolve absolute: $value\" >&2; exit 2 ;; esac
            case \"$value\" in *$'\\n'*|*$'\\r'*) echo 'readiness path contains a newline' >&2; exit 2 ;; esac
          done
          args=(
            --role audio-validation
            --source-revision '${{ needs.resolve.outputs.sha }}'
            --data-root \"$DATA_ROOT\" --seal \"$SEAL\"""",
)
replace(
    ".github/workflows/trusted-runner-readiness.yml",
    """      - name: Check audio-target readiness
        env:
          BOARD: ${{ inputs.board_manifest }}
          CORPUS: ${{ inputs.corpus_manifest }}
          ACOUSTIC: ${{ inputs.acoustic_json }}
          FAREND: ${{ inputs.farend_file }}
          POWER: ${{ inputs.power_input }}
        run: |
          set -euo pipefail
          args=(--role audio-target --source-revision '${{ needs.resolve.outputs.sha }}' --writable-path /tmp --output runner-readiness.json)
          if [ -n \"$BOARD\" ]; then args+=(--board-manifest \"$BOARD\"); fi""",
    """      - name: Check audio-target readiness
        env:
          INPUT_BOARD: ${{ inputs.board_manifest }}
          CORPUS: ${{ inputs.corpus_manifest }}
          ACOUSTIC: ${{ inputs.acoustic_json }}
          FAREND: ${{ inputs.farend_file }}
          POWER: ${{ inputs.power_input }}
        run: |
          set -euo pipefail
          BOARD=$INPUT_BOARD
          if [ -z \"$BOARD\" ]; then
            BOARD=${AUDIO_PIPELINE_LAB_BOARD:-${XDG_CONFIG_HOME:-$HOME/.config}/audio-pipeline/board.json}
          fi
          case \"$BOARD\" in /*) ;; *) echo \"board manifest must resolve absolute: $BOARD\" >&2; exit 2 ;; esac
          case \"$BOARD\" in *$'\\n'*|*$'\\r'*) echo 'board manifest contains a newline' >&2; exit 2 ;; esac
          args=(--role audio-target --source-revision '${{ needs.resolve.outputs.sha }}' --writable-path /tmp --output runner-readiness.json)
          args+=(--board-manifest \"$BOARD\")""",
)

# Product Certification: blank board path resolves only on the audio-target runner.
replace(
    ".github/workflows/product-certification.yml",
    """      board_manifest:
        description: Absolute path to the DUT board manifest
        required: true
        default: /etc/audio-pipeline/board.json""",
    """      board_manifest:
        description: Optional absolute DUT board manifest; blank resolves AUDIO_PIPELINE_LAB_BOARD or XDG/HOME on audio-target
        required: false
        default: ''""",
)
replace(
    ".github/workflows/product-certification.yml",
    """      - name: Preflight exact audio-target runner and product inputs
        env:
          BOARD: ${{ inputs.board_manifest }}
          CORPUS: ${{ inputs.corpus_manifest }}
          ACOUSTIC: ${{ inputs.acoustic_json }}
          FAREND: ${{ inputs.farend_pcm }}
          POWER: ${{ inputs.power_input }}
        run: |
          set -euo pipefail
          python3 tools/runner_preflight.py \\
            --role audio-target \\
            --source-revision '${{ needs.resolve.outputs.sha }}' \\
            --board-manifest \"$BOARD\" --corpus-manifest \"$CORPUS\"""",
    """      - name: Preflight exact audio-target runner and product inputs
        env:
          INPUT_BOARD: ${{ inputs.board_manifest }}
          CORPUS: ${{ inputs.corpus_manifest }}
          ACOUSTIC: ${{ inputs.acoustic_json }}
          FAREND: ${{ inputs.farend_pcm }}
          POWER: ${{ inputs.power_input }}
        run: |
          set -euo pipefail
          BOARD=$INPUT_BOARD
          if [ -z \"$BOARD\" ]; then
            BOARD=${AUDIO_PIPELINE_LAB_BOARD:-${XDG_CONFIG_HOME:-$HOME/.config}/audio-pipeline/board.json}
          fi
          case \"$BOARD\" in /*) ;; *) echo \"board_manifest must resolve absolute: $BOARD\" >&2; exit 2 ;; esac
          case \"$BOARD\" in *$'\\n'*|*$'\\r'*) echo 'board_manifest contains a newline' >&2; exit 2 ;; esac
          printf '%s\\n' \"$BOARD\" > /tmp/audio-target-board-path.txt
          python3 tools/runner_preflight.py \\
            --role audio-target \\
            --source-revision '${{ needs.resolve.outputs.sha }}' \\
            --board-manifest \"$BOARD\" --corpus-manifest \"$CORPUS\"""",
)

# Current operational docs: ordinary-user is default; system paths are explicit examples only.
replace(
    "docs/TRUSTED_RUNNERS.md",
    """2. Install a valid `/etc/audio-pipeline/board.json` and confirm real route/power paths.""",
    """2. Install a reviewed board manifest at `$HOME/.config/audio-pipeline/board.json` for ordinary-user mode (or an explicit system-mode path) and confirm real route/power paths.""",
)
replace(
    "docs/TRUSTED_RUNNERS.md",
    """  --data-root /opt/audio-validation-data \\
  --seal /opt/audio-validation-data/datasets.seal.json \\
  --output /tmp/audio-validation-readiness.json""",
    """  --data-root $HOME/audio-validation-data \\
  --seal $HOME/audio-validation-data/datasets.seal.json \\
  --output /tmp/audio-validation-readiness.json""",
)
replace(
    "docs/TRUSTED_RUNNERS.md",
    """  --board-manifest /etc/audio-pipeline/board.json \\
  --power-input /path/to/live_power \\
  --output /tmp/audio-target-readiness.json""",
    """  --board-manifest $HOME/.config/audio-pipeline/board.json \\
  --power-input /path/to/live_power \\
  --output /tmp/audio-target-readiness.json""",
)

cert = Path("certification/README.md")
cert_text = cert.read_text(encoding="utf-8")
needle = """A formal run requires:\n\n- exact source ref/SHA;"""
replacement = """A formal run requires:\n\n- exact source ref/SHA;\n- a reviewed DUT board manifest; when the workflow input is blank, the `audio-target` runner resolves `AUDIO_PIPELINE_LAB_BOARD`, XDG config, then `$HOME/.config/audio-pipeline/board.json`; explicit absolute system-mode paths remain supported;"""
if cert_text.count(needle) != 1:
    raise SystemExit("certification README insertion anchor drift")
cert.write_text(cert_text.replace(needle, replacement), encoding="utf-8")

# Permanent assurance: cover the two remaining trusted workflow surfaces.
p = Path("scripts/docs_consistency.py")
text = p.read_text(encoding="utf-8")
anchor = '''    if "default: /etc/audio-pipeline/board.json" in hil:
        errors.append("HIL workflow reintroduced a system-mode /etc board default")
    for token in ("AUDIO_PIPELINE_LAB_BOARD", "XDG_CONFIG_HOME", "$HOME/.config"):
        if token not in hil:
            errors.append(f"HIL workflow missing runner-local user-mode token: {token}")
'''
insert = anchor + '''    readiness = read(root, ".github/workflows/trusted-runner-readiness.yml")
    certification = read(root, ".github/workflows/product-certification.yml")
    for forbidden in ("default: /opt/audio-validation-data", "default: /etc/audio-pipeline/board.json"):
        if forbidden in readiness:
            errors.append(f"trusted runner readiness reintroduced stale system-mode default: {forbidden}")
    for token in ("$HOME/audio-validation-data", "datasets.seal.json", "AUDIO_PIPELINE_LAB_BOARD", "XDG_CONFIG_HOME", "$HOME/.config"):
        if token not in readiness:
            errors.append(f"trusted runner readiness missing runner-local user-mode token: {token}")
    if "default: /etc/audio-pipeline/board.json" in certification:
        errors.append("Product Certification reintroduced a system-mode /etc board default")
    for token in ("AUDIO_PIPELINE_LAB_BOARD", "XDG_CONFIG_HOME", "$HOME/.config", "/tmp/audio-target-board-path.txt"):
        if token not in certification:
            errors.append(f"Product Certification missing runner-local user-mode token: {token}")
'''
if text.count(anchor) != 1:
    raise SystemExit("docs_consistency v2.2.3 anchor drift")
p.write_text(text.replace(anchor, insert), encoding="utf-8")

Path("workflow-export").mkdir(exist_ok=True)
for name in ("trusted-runner-readiness.yml", "product-certification.yml"):
    Path("workflow-export", name).write_bytes(Path(".github/workflows", name).read_bytes())

print("v2.2.4 readiness/certification candidate generated")
