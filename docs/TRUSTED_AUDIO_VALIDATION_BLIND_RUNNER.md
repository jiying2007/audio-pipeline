# Trusted audio-validation runner admission for blind qualification

This runbook is the operator checklist for bringing an isolated `audio-validation` self-hosted runner online for `Research Candidate Blind Qualification`.

It is an infrastructure-readiness procedure only. Passing it does **not** grant shipping, HIL, Product Certification, target execution, release mutation, or main-mutation authority.

## Immutable boundaries

For the currently queued frozen research candidate qualification:

- do not rerun or redispatch the blind workflow while the existing `qualify-blind` job is still queued;
- do not change the candidate manifest, tuning, limits, holdout percentage, thresholds, or dataset composition;
- do not use blind/holdout results as optimizer feedback;
- keep the shipping authority unchanged at `v2.3.16 / 57e4c64adc1cf06819e46e24e275ecd746d5f17f / aec_mu=0.22`;
- a successful blind result can advance only to the next non-shipping gate declared by the qualification contract.

## Why this admission check is required

The blind job uses repository tooling plus several host commands before it can complete its own runner preflight and dataset verification. In particular, provenance rebind uses `gh`, `jq`, `curl`, `sha256sum`, and `unzip`.

The reference lab Ansible contract already validates most ordinary-user prerequisites, but `gh` is not currently part of that baseline. Therefore the runner service must stay offline until this explicit operator admission passes.

## 1. Keep the runner offline

Do not start the GitHub Actions runner service yet. A queued job may be claimed immediately when a matching runner becomes online.

The required labels are exactly:

```text
self-hosted
linux
audio-validation
```

## 2. Install and verify the complete command surface

Install `gh` before the runner is brought online. On the supported Ubuntu/Debian reference hosts, an administrator may use the distribution package while the runner service remains stopped:

```bash
sudo apt-get update
sudo apt-get install -y gh
```

In ordinary-user mode, do not add sudo privileges to the runner account merely to satisfy this prerequisite. If that account cannot install OS packages, have an administrator install `gh` first, then verify it from the exact runner user's PATH.

Run the full command check as the exact OS user that will execute the GitHub runner:

```bash
set -euo pipefail
for cmd in \
  gh jq curl sha256sum unzip \
  python3 cmake cc git git-lfs
 do
  command -v "$cmd" >/dev/null || {
    echo "RUNNER_NOT_READY: missing command: $cmd" >&2
    exit 2
  }
done
```

Do not treat an administrator shell having these commands as sufficient; they must be visible in the runner user's PATH.

## 3. Verify the public validation cache and seal

The current blind workflow defaults are:

```text
data_root=/opt/audio-validation-data
seal_path=/opt/audio-validation-data/datasets.seal.json
```

Verify them before the runner is online:

```bash
set -euo pipefail
test -d /opt/audio-validation-data
test -r /opt/audio-validation-data/datasets.seal.json
```

Then, from an exact checkout of the frozen candidate source revision, run the repository preflight while explicitly requiring the blind-job command surface:

```bash
python3 tools/runner_preflight.py \
  --role audio-validation \
  --source-revision 01c7e0adf3ec9bcb1d401540c5e9d209176bd9ef \
  --data-root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json \
  --require-command gh \
  --require-command jq \
  --require-command curl \
  --require-command sha256sum \
  --require-command unzip \
  --writable-path /tmp \
  --output /tmp/audio-validation-blind-readiness.json
```

Require `classification=READY` and `failure_count=0`.

## 4. Verify the full sealed public cache

Still using the exact frozen candidate source checkout:

```bash
python3 validation/tools/prepare_public_validation.py verify \
  --profile full \
  --root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json
```

If the workflow was explicitly dispatched with a DNS data root, verify that same root and pass the matching `--dns-data-root`. Do not silently substitute a different cache or seal.

## 5. Verify the blind holdout secret exists

`AP_VALIDATION_HOLDOUT_KEY` is required by the workflow and missing/empty secret material must fail closed.

From a trusted operator machine, verify only the secret name exists; never print or copy the secret value into logs or chat:

```bash
gh secret list --repo jiying2007/audio-pipeline | \
  awk '$1 == "AP_VALIDATION_HOLDOUT_KEY" { found=1 } END { exit(found ? 0 : 2) }'
```

## 6. Verify the queued job before starting the runner

Confirm there is exactly one intended queued `qualify-blind` job, bound to the expected workflow run and requiring `self-hosted, linux, audio-validation`.

Do not start the runner if:

- another blind attempt exists for the same candidate;
- the intended job has already completed or been cancelled;
- the job is bound to an unexpected candidate/infra identity;
- any command/cache/secret admission check above is not proven READY.

## 7. Start the runner once

Only after all admission checks pass, start the existing reviewed runner service. The queued job should claim that runner naturally; do not rerun the job and do not start a second blind workflow.

After assignment, retain the exact run id, job id, runner name/id, candidate identity, source SHA, infra SHA, dataset seal identity, and uploaded qualification evidence.

## Result handling

Use only the machine-readable qualification decision:

- `BLIND_QUALIFIED_NON_SHIPPING`: candidate remains non-shipping and may advance only to the declared next non-shipping gate;
- `BLIND_REJECTED_NON_SHIPPING`: explicit validation `FAIL` terminalizes the exact candidate/tuning identity; do not retry, reselect, sweep thresholds, or mint a replacement nonce from the same blind evidence;
- `BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING`: infrastructure/evidence failure is non-terminal; repair the infrastructure/evidence boundary without interpreting it as an acoustic pass or fail.

Hosted CI, public/synthetic validation, QEMU, or runner readiness must never be used as substitutes for real PCR02/SSC305 HIL or Product Certification evidence.
