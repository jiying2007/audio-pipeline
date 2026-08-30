# Audio Pipeline Laboratory Infrastructure

`lab/` turns the trusted validation/HIL environment into reproducible infrastructure. It provisions isolated GitHub self-hosted runner controllers, materializes the commercial real-data profile, seals acquisition state, runs the repository's canonical per-file source scanner/readiness checks, and can dispatch the existing Extended Real/HIL workflows against an exact commit SHA.

It does **not** make a lab result product-certified. Public/real-data validation, DUT HIL and formal Product Certification remain separate evidence levels.

## Reference topology

```text
operator / Ansible controller
        |
        +--> audio-validation PC (Ubuntu x64, 32 GiB+, 4 TiB NVMe recommended)
        |      label: self-hosted,linux,audio-validation
        |      $HOME/audio-validation-extended
        |      RealMAN / BUT ReverbDB / MUSAN / Mini LibriSpeech / plus imports
        |
        +--> audio-target controller PC (Ubuntu x64)
               label: self-hosted,linux,audio-target
               |
               +-- SSH/serial/ALSA/USB --> SSC305 DUT
               +-- relay/power-cycle hook
               +-- live temperature/power sensor exports
```

Do not install the GitHub runner on the low-resource DUT unless there is a reviewed reason to do so. The reference design runs Actions on the controller and treats the product board as the DUT.

Because this repository is public, never route untrusted fork pull-request code to these runners. The repository's trusted workflows use exact SHA/manual/schedule/repository-dispatch entrypoints instead.

## 1. Provision the hosts

The **default is ordinary-user mode**. It requires no sudo and writes only below the SSH user's HOME:

```text
$HOME/.local/share/audio-pipeline-lab/   runner + venv + fixtures
$HOME/.cache/audio-pipeline-lab/         downloaded archives
$HOME/.local/state/audio-pipeline-lab/   acquisition/readiness/HIL state
$HOME/.config/audio-pipeline/board.json  audio-target board manifest
$HOME/audio-validation-extended/         real validation datasets
```

The OS still needs the required native tools (`cc`, CMake, Git/Git-LFS, ffmpeg, 7z, ALSA tools as applicable). In ordinary-user mode Ansible verifies them but never attempts apt/sudo. Ask an administrator to install missing OS packages once if needed.

Copy the inventory, set the real SSH hosts/users, obtain a short-lived repository runner token, then run without `--become`:

```bash
cd lab/ansible
cp inventory.example.yml inventory.yml
ansible-playbook site.yml --limit audio_validation \
  --extra-vars 'github_runner_registration_token=<SHORT_LIVED_TOKEN>'
ansible-playbook site.yml --limit audio_target \
  --extra-vars 'github_runner_registration_token=<SHORT_LIVED_TOKEN>'
```

The ordinary-user runner is installed as a `systemd --user` service. For unattended reboot/no-login persistence only, an administrator may run once:

```bash
sudo loginctl enable-linger <ubuntu-user>
```

This linger step is optional for interactive/login-session use; it is not permission to write `/opt`.

For a dedicated service-account deployment, explicitly set `lab_system_mode: true`, `lab_service_user`, and any desired `/opt` data paths in inventory. System mode retains apt/service-account/systemd-system behavior.

The runner distribution remains SHA-256 pinned and registration tokens remain runtime-only `no_log` inputs.

## 2. Materialize commercial-core

In default ordinary-user mode, use the Ansible-created user virtual environment:

```bash
cd /path/to/audio-pipeline
$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py self-test
$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py validate-catalog
$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py plan --profile commercial-core
$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py materialize --profile commercial-core
```

The locked core sources are:

| Dataset | Acquisition | Integrity |
| --- | --- | --- |
| RealMAN | Hugging Face `AISHELL/RealMAN` | exact revision `12b6f7979e4e5efad4e1004280cf7419201ce209`; only `val`, `test`, `dataset_info`, transcription patterns; RARs extracted locally |
| BUT ReverbDB | official `19_06` RIR-only archive | official versioned TLS URL; first acquisition SHA-256 is sealed under `$HOME/.local/state/audio-pipeline-lab/acquisition`, all later acquisitions must match |
| MUSAN | OpenSLR SLR17 | official MD5 `0c472d4fc0c5141eca47ad1ffeb2a7df` plus local SHA-256 acquisition seal |
| Mini LibriSpeech | OpenSLR SLR31 `dev-clean-2` | official MD5 `6d7ab67ac6a1d2c993d050e16d61080d` plus local SHA-256 acquisition seal |

Large archives stay in `$HOME/.cache/audio-pipeline-lab/datasets`; extracted data lives under `$HOME/audio-validation-extended`; acquisition seals live under `$HOME/.local/state/audio-pipeline-lab/acquisition`. None are Git artifacts.

RealMAN train and `*_raw` trees are intentionally excluded. Validation needs the real val/test noisy/direct-path pairs and location metadata, not the hundreds-of-gigabytes training set.

## 3. Verify actual files and runner readiness

Use the exact source commit that will be validated:

```bash
SHA=<40-hex-audio-pipeline-commit>

$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py verify-profile \
  --profile commercial-core \
  --source-revision "$SHA"
```

This invokes the repository's existing `prepare_extended_validation.py scan/verify` and `runner_preflight.py`. The resulting source manifest contains per-file SHA-256 values selected by the canonical validation scanner. `READY` is infrastructure readiness only.

Readiness/evidence preparation is stored below:

```text
$HOME/.local/state/audio-pipeline-lab/readiness/commercial-core/
  source-manifest.json
  runner-readiness.json
```

## 4. Dispatch the first Extended Real run

From a trusted operator machine already authenticated with `gh`:

```bash
python3 lab/scripts/labctl.py dispatch-validation \
  --source-revision "$SHA" \
  --profile commercial-core
```

The workflow then repeats runner preflight, scans/hashes source files, builds the exact processor, creates the real corpus, performs scenario-stratified visible/blind validation and uploads the hash-bound evidence bundle. `AP_VALIDATION_HOLDOUT_KEY` must be configured as a repository secret before commercial validation.

Do **not** set `EXTENDED_REAL_ENABLED=true` after only one run. Require repeated manual `commercial-core` success first.

## 5. Add commercial-plus

VOiCES/AMI/ICSI use `operator_import` because their upstream distribution layouts/terms should be reviewed instead of silently scraped. Acquire them from their official sources, then adopt a reviewed local tree:

```bash
python3 lab/scripts/labctl.py adopt --dataset voices --source /mnt/intake/VOiCES --delete
python3 lab/scripts/labctl.py adopt --dataset ami    --source /mnt/intake/AMI    --delete
python3 lab/scripts/labctl.py adopt --dataset icsi   --source /mnt/intake/ICSI   --delete

python3 lab/scripts/labctl.py materialize --profile commercial-plus --skip-operator
python3 lab/scripts/labctl.py verify-profile \
  --profile commercial-plus --source-revision "$SHA"
```

The canonical scanner, not the intake copy operation, establishes per-file validation evidence.

Only after the isolated runner/cache has repeatedly produced valid core/plus reports should the repository variable be set:

```text
EXTENDED_REAL_ENABLED=true
```

At that point post-release automation runs `commercial-core` and the weekly automation runs `commercial-plus`. With no `EXTENDED_REAL_DATA_ROOT` repository variable, the workflow deliberately resolves `$HOME/audio-validation-extended` on the `audio-validation` runner itself. Set `EXTENDED_REAL_DATA_ROOT` only when that runner uses an explicit non-default/system-mode location.

## 6. Bring up the SSC305 audio-target controller

Start from `lab/examples/board.ssc305.example.json`, replace **every** placeholder with the real product route and install it as `$HOME/.config/audio-pipeline/board.json`. Hardware hooks and sensor paths are product/lab specific and must never be invented by automation.

Then run:

```bash
SHA=<40-hex-audio-pipeline-commit>

python3 lab/scripts/labctl.py target-readiness \
  --source-revision "$SHA" \
  --board $HOME/.config/audio-pipeline/board.json \
  --power-input <live-power-path>
```

This executes both the board preflight and the shared `audio-target` runner contract.

From a trusted authenticated operator machine, start the 10-minute accelerated HIL only after readiness is `READY`:

```bash
python3 lab/scripts/labctl.py dispatch-hil \
  --source-revision "$SHA" \
  --tier accelerated-pr \
  --capture '<controller-visible-capture-device>' \
  --playback '<controller-visible-playback-device>' \
  --farend $HOME/.local/share/audio-pipeline-lab/fixtures/farend-s16le.pcm \
  --power '<live-power-path>'
```

When `--board` is omitted, the HIL workflow resolves `AUDIO_PIPELINE_LAB_BOARD`, then XDG config, then `$HOME/.config/audio-pipeline/board.json` on the `audio-target` runner. Use `--board` only for an explicit runner-local override.

Do not set `HIL_ENABLED=true` until repeated manual accelerated runs demonstrate that the controller, DUT route, power-cycle/cleanup hooks and sensors are actually healthy.

## 7. Activation gates

A lab is considered operational only when all applicable items are true:

- self-hosted runner is online with the expected dedicated label;
- `labctl.py self-test` and catalog validation pass;
- commercial-core materialization completes with acquisition seals;
- canonical source scan + re-verification pass;
- `audio-validation` runner preflight is `READY` for the exact SHA;
- visible and blind commercial-core validation pass repeatedly;
- commercial-plus is adopted/scanned and passes before weekly automation is enabled;
- `$HOME/.config/audio-pipeline/board.json` is a reviewed real product manifest;
- `audio-target` runner and board preflight are `READY`;
- accelerated HIL passes repeatedly before `HIL_ENABLED=true`;
- Nightly 1 h, release 8 h and weekly 24 h evidence are accumulated before formal certification;
- the separate `audio-builder -> audio-target -> certification-archive` topology is still required for 72 h Product Certification.

## Recovery and upgrades

Re-run Ansible and readiness after OS/tool/runner upgrades, dataset changes, board/codec/mic revisions, route changes, sensor changes or storage relocation. Do not treat old readiness JSON as evidence for a changed machine.

Changing a pinned GitHub Runner, Hugging Face revision, archive checksum or Python dependency is a reviewed repository change and must pass normal PR verification before lab rollout.
