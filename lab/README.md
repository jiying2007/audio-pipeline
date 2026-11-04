# Audio Pipeline Research Laboratory

This laboratory exists for **technical research only**. It provides pinned public
source acquisition, deterministic audio front-end validation, isolated ARM
cross-builds, and independently authorized physical SSC305 / ALSA experiments.
A runner being online or a CI job being green is **not** human-acoustic evidence,
device resource measurement, consent verification, or product certification.

## 1. Exactly three research runner roles

| Role | Isolated runner labels | Purpose |
| --- | --- | --- |
| Audio validation | `self-hosted, linux, audio-validation` | Lawful source acquisition, 1/2/4-mic front-end, Extended Real visible/blind evidence |
| ARM research builder | `self-hosted, linux, audio-builder` | Reproducible exact compiler/sysroot cross-build and SHA identity |
| Physical target | `self-hosted, linux, audio-target` | Real SSC305 codec, microphone/speaker, route, CPU/RSS, XRUN, temperature and power |

The controller, not the low-memory DUT itself, normally runs the GitHub runner.
Never execute code from an untrusted fork on an isolated physical target.
Historical publication/archive roles are **not installed** in this research
topology. Their original source and old evidence remain in Git history.

## 2. Provision ordinary users by default

The default `lab_system_mode: false` writes under each unprivileged user's HOME:

```text
$HOME/.local/share/audio-pipeline-lab/    runner + pinned venv + fixtures
$HOME/.cache/audio-pipeline-lab/          downloaded legal-source archives
$HOME/.local/state/audio-pipeline-lab/    acquisition, readiness, HIL receipts
$HOME/.config/audio-pipeline/board.json   private board identity/route/sensors
$HOME/audio-validation-extended/          permitted acoustic validation data
```

System-mode installation and OS packages require a separately authorized
administrator. Ansible does not invent compiler binaries or private datasets.
After reviewing hosts, SSH users, source permissions and short-lived runner
registration tokens, run:

```bash
cd lab/ansible
cp inventory.example.yml inventory.yml
ansible-playbook site.yml --limit audio_validation \
  --extra-vars 'github_runner_registration_token=<SHORT_LIVED_TOKEN>'
ansible-playbook site.yml --limit audio_target \
  --extra-vars 'github_runner_registration_token=<SHORT_LIVED_TOKEN>'
ansible-playbook site.yml --limit audio_builder \
  --extra-vars 'github_runner_registration_token=<SHORT_LIVED_TOKEN>'
```

The research builder's **operator-installed, absolute** compiler/toolchain
inputs in the private inventory are:

```yaml
audio_builder_target_cc: /real/toolchain/bin/arm-linux-gnueabihf-gcc
audio_builder_target_sysroot: /real/toolchain/sysroot
audio_builder_target_toolchain_root: /real/toolchain
```

The builder role rejects missing/nonexecutable compiler paths, missing sysroot
or root directories and inaccessible toolchains. Only explicit role readiness
can be reported. Registration tokens are runtime-only `no_log` values;
the pinned GitHub runner digest is verified. An administrator may enable
`loginctl enable-linger` for authorized unattended user services.

## 3. License-scoped datasets and acquisition

The committed [data lock](data-sources.lock.json) is the authority for
each public dataset URL/revision, checksum, use conditions, and whether
redistribution, transformation or commercial use is limited. **Do not infer
new rights from GitHub visibility or the directory/profile name.**

The existing machine profile IDs `commercial-core` and `commercial-plus`
are historical source-catalog keys; they are **not** product deployment
authorization. For the current research-only task, use only data whose exact
source license permits that experiment, and isolate conditional/noncommercial
corpora from any other cohort.

```bash
cd /path/to/audio-pipeline
$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py self-test
$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py validate-catalog
$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py plan --profile commercial-core
$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py materialize --profile commercial-core
```

Materialization verifies the originally pinned hashes and safe extraction;
cache and acquisition receipts remain private. The optional scheduled
[SLR31 acquisition smoke](../.github/workflows/lab-acquisition-smoke.yml)
verifies the downloader, acquisition seal, idempotence and corrupt-cache
rejection. It does not prove RealMAN/BUT/MUSAN or hardware acoustic quality.

## 4. Exact source and three independent readiness records

Bind a real research commit, not a Release tag:

```bash
SHA=$(git rev-parse HEAD)
gh workflow run trusted-runner-readiness.yml --repo jiying2007/audio-pipeline --ref main \
  -f source_sha="$SHA" -f role=audio-validation \
  -f data_root="$HOME/audio-validation-data" \
  -f seal_path="$HOME/audio-validation-data/datasets.seal.json"

gh workflow run trusted-runner-readiness.yml --repo jiying2007/audio-pipeline --ref main \
  -f source_sha="$SHA" -f role=audio-builder \
  -f target_cc=/real/toolchain/bin/arm-linux-gnueabihf-gcc \
  -f target_sysroot=/real/toolchain/sysroot \
  -f target_toolchain_root=/real/toolchain

gh workflow run trusted-runner-readiness.yml --repo jiying2007/audio-pipeline --ref main \
  -f source_sha="$SHA" -f role=audio-target \
  -f board_manifest="$HOME/.config/audio-pipeline/board.json"
```

The exact script `tools/runner_preflight.py` has offline self-tests. A
`READY` result means infrastructure/route availability only. To verify
the source-catalog profile's actual local files on an authorized
audio-validation runner:

```bash
$HOME/.local/share/audio-pipeline-lab/venv/bin/python lab/scripts/labctl.py verify-profile \
  --profile commercial-core --source-revision "$SHA"
```

Never treat a cached run, source-only seal, empty corpus or untrusted
external state as independent acoustic PASS.

## 5. Extended Real and physical-target experiments

After verifying the exact authorized source, materialized legal datasets,
runner and evaluation roles, use
[validation-extended-real.yml](../.github/workflows/validation-extended-real.yml)
with explicit source SHA and its reviewed profile. Development, visible
validation and independent blind evaluation must remain separate.

For physical experiments, configure the private
[board manifest](../hil/board.schema.json), capture/playback route, ALSA
inventory, codec/microphone/speaker identities and real thermal/power sensors.
Run `tools/hil_board.py preflight` against the real board. Then use the
[manual research HIL](../.github/workflows/hil-soak.yml) with exact source
SHA and a scientifically justified duration: 600 seconds, 1h, 8h, 24h or
optional 72h. Set `HIL_ENABLED=true` **only** after the real isolated
runner and board prerequisites exist.

Missing hardware, rights, sensor readings, measured duration or independent
real-person audio must be recorded as `NOT_RUN`, `BLOCKED` or `FAIL`,
never treated as PASS. Hardware runtime, CPU/RSS, thermal/power, XRUN and
audio results must retain their exact source/board/measurement hashes.

## 6. Verification, rollback and upgrades

[Lab User Mode Runtime](../.github/workflows/lab-user-mode.yml) performs
ordinary-user installation, three **parallel** role smoke tests, idempotent
reruns, absent sudo/system-path writes and a SHA-bound synthetic proof.
The fixture validates provisioning logic only, not actual SSC305 acoustic
or performance evidence.

Re-run impacted Ansible roles and readiness after a runner/OS/toolchain,
dataset revision/license, codec, microphone, board, path or sensor change.
Keep immutable original source/failed receipts and require exact-head PR
verification before rolling out updates. Do not replace or reinterpret old
results.
