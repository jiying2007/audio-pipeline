# Audio Pipeline Research Laboratory

**Technical research only.** The supported live laboratory roles are an isolated `audio-validation` runner for licensed real-audio experiments and an isolated `audio-target` controller for actual DUT/HIL measurements. Neither role gives release, certification, product qualification or model-acceptance authority. Historical builder/archive runbooks and source are retained in Git history, not active Ansible/site or lab workflow.

## Topology and independent evidence

```text
trusted operator / Ansible controller
  +-- self-hosted,linux,audio-validation (Ubuntu x64; source-locked public data)
  |     $HOME/audio-validation-extended
  |     RealMAN / BUT ReverbDB / MUSAN / OpenSLR sources as licensed
  +-- self-hosted,linux,audio-target (Ubuntu x64 controller)
        SSH / serial / ALSA / USB / relay -> real SSC305-class DUT
        board manifest + observed XRUN, latency, temperature, power
```

GitHub Actions should execute on the isolated controller, not necessarily on the low-resource DUT. Never run fork PR code on self-hosted devices. A GitHub-hosted/QEMU CI PASS and an ordinary-user role PASS never establish actual physical measurements.

## 1. Provision the two ordinary-user roles

The default is `lab_system_mode: false`: no Ansible privilege escalation and no writes to `/opt`, `/var` or `/etc` on the target host. Required OS packages (C compiler, Git/Git LFS, CMake, Python, ALSA/ffmpeg and 7z where applicable) must be installed independently by an authorized administrator. The user-mode controller stores state under:

```text
$HOME/.local/share/audio-pipeline-lab/     runner, isolated venv and fixtures
$HOME/.cache/audio-pipeline-lab/           verified acquisition cache
$HOME/.local/state/audio-pipeline-lab/     source seals and test receipts
$HOME/.config/audio-pipeline/board.json    actual target identity and routes
$HOME/audio-validation-extended/           source-licensed datasets
```

Copy `lab/ansible/inventory.example.yml` to an untracked restricted inventory. Replace example host addresses, usernames and short-lived runner tokens. Run only the two active plays:

```bash
cd lab/ansible
ansible-playbook site.yml --limit audio_validation --extra-vars 'github_runner_registration_token=<SHORT_LIVED_TOKEN>'
ansible-playbook site.yml --limit audio_target --extra-vars 'github_runner_registration_token=<SHORT_LIVED_TOKEN>'
```

The GitHub runner package has a pinned SHA-256 identity. Registration tokens are runtime-only and hidden from Ansible logs. `systemd --user` is the default. A one-time `loginctl enable-linger` can be arranged by an administrator for an unattended user service; it does not authorize broader filesystem access.

## 2. Research data rights, preparation and source seals

Run from a trusted checked-out exact source revision:

```bash
python3 lab/scripts/labctl.py self-test
python3 lab/scripts/labctl.py validate-catalog
python3 lab/scripts/labctl.py plan --profile research-attribution-core
python3 lab/scripts/labctl.py materialize --profile research-attribution-core
```

**Research data-rights boundary:** The active `research-attribution-core` and `research-attribution-extended` identities select only the previously reviewed CC-BY-4.0 dataset sets. Their names grant no additional source rights or model/publication authority. The previous source-lock identifiers remain in historical Git records. Actual source notices, attribution, noncommercial/conditional restrictions, transform permissions, SHA/MD5 verification and independent holdout roles must always be respected. Do not substitute broader conditional/NC corpora into an unattended profile without separate source review. The acquisition smoke validates the OpenSLR SLR31 download/cache/integrity path; it does not represent a RealMAN/BUT/MUSAN acoustic PASS.

Use `lab/data-sources.lock.json`, `validation/extended.datasets.lock.json`, `validation/authority.json` and the canonical `validation/tools` scanners for exact source and role enforcement. Cache under the user home; keep private or unlicensed raw voice files outside public Git/Actions artifacts.

## 3. Pin exact research SHA and verify real readiness

Choose a reviewed exact 40-hex research source SHA. Do not assume that an old software release or a previous runner state establishes the current experiment. From a trusted operator environment:

```bash
SHA=$(git rev-parse HEAD)
gh workflow run trusted-runner-readiness.yml -R jiying2007/audio-pipeline --ref main -f source_sha="$SHA" -f role=audio-validation -f data_root="$HOME/audio-validation-data" -f seal_path="$HOME/audio-validation-data/datasets.seal.json"
gh workflow run trusted-runner-readiness.yml -R jiying2007/audio-pipeline --ref main -f source_sha="$SHA" -f role=audio-target -f board_manifest="$HOME/.config/audio-pipeline/board.json"
```

Run the appropriate source verification and `tools/runner_preflight.py` on each isolated actual runner. Revalidate when the source SHA, codec/route, dataset bytes, system kernel or compiler changes. `READY` verifies infrastructure identity only; it does not imply AEC/BF/NS accuracy, power/thermal limits or a DUT PASS.

## 4. Independently authorize and run experiments

Extended Real validation uses the exact-source `validation-extended-real.yml` workflow, with real-audio rights and the frozen scanner/holdout contract. For physical HIL, create an actual reviewed board manifest conforming to `hil/board.schema.json` and run preflight. Only after a physical target, route and cleanup hooks exist may the operator enable `HIL_ENABLED=true`. Dispatch manually:

```bash
python3 lab/scripts/labctl.py target-readiness --source-revision "$SHA" --board "$HOME/.config/audio-pipeline/board.json"
python3 lab/scripts/labctl.py dispatch-hil --source-revision "$SHA" --tier accelerated-pr
```

Optional duration choices are `accelerated-pr` (600 s), `research-1h`, `research-8h`, `research-24h`, and `research-72h`. The 72-hour tier is an optional scientific long-soak observation, **never a source admission or certification requirement**. A missing runner, board, dataset right, duration or sensor returns `NOT_RUN`, `BLOCKED` or an actual `FAIL` where appropriate; it must not be manufactured as PASS. See `hil/README.md`, `docs/RESEARCH_ONLY_EXECUTION.md`, and `docs/TRUSTED_RUNNERS.md`.

## 5. Repeatability and recovery

Run the source-only ordinary-user smoke in `.github/workflows/lab-user-mode.yml`: it validates only the real audio-validation and audio-target user-mode Ansible roles, idempotence, permissions, paths, board-manifest identity and lack of system-path writes. Historical product-builder and certification-archive fake roles are not exercised. Keep its exact source SHA artifact with experiment records.

Re-run preflight and source/permission audits after upgrades, dataset refreshes, microphone geometry, device/codec, kernel, routes, sensors or storage location changes. Never treat a prior READY record, historic product-certificate receipt or archived failure as a new measurement result.
