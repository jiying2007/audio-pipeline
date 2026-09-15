# Trusted audio-validation runner admission for blind qualification

This runbook is the operator checklist for executing `Research Candidate Blind Qualification` on an isolated `audio-validation` self-hosted runner.

The target operating model is **role, not service**: `audio-validation` is a capability label, not a requirement to keep a long-running GitHub Actions service online. The preferred runner is registered with GitHub using `config.sh --ephemeral`, processes one job, is automatically de-registered by GitHub, and is then cleaned up.

This is an infrastructure-readiness procedure only. Passing it does **not** grant shipping, HIL, Product Certification, target execution, release mutation, or main-mutation authority.

## Immutable boundaries

For the currently queued frozen research candidate qualification:

- do not rerun or redispatch the blind workflow while the existing `qualify-blind` job is still queued;
- do not change the candidate manifest, tuning, limits, holdout percentage, thresholds, or dataset composition;
- do not use blind/holdout results as optimizer feedback;
- keep the shipping authority unchanged at `v2.3.16 / 57e4c64adc1cf06819e46e24e275ecd746d5f17f / aec_mu=0.22`;
- a successful blind result can advance only to the next non-shipping gate declared by the qualification contract.

The currently queued job remains compatible with the ephemeral model because it already requests exactly:

```text
self-hosted
linux
audio-validation
```

No workflow redispatch is required merely to switch from a persistent runner service to an ephemeral runner process.

## 1. Do not expose a matching runner before admission

A queued job may be claimed immediately when any matching runner becomes online. Complete all command, source, dataset, seal, preflight, cache and secret-presence checks before registering or starting an ephemeral runner.

If a legacy persistent runner service exists on the host, keep it stopped during admission:

```bash
systemctl list-units --all | grep 'actions.runner' || true
```

Do not install or start a new systemd runner service for blind qualification. A clean ephemeral runner directory plus `./run.sh` is sufficient.

## 2. Install and verify the complete command surface

Install `gh` before a runner is registered. On the supported Ubuntu/Debian reference hosts, an administrator may use the distribution package:

```bash
sudo apt-get update
sudo apt-get install -y gh
```

In ordinary-user mode, do not add sudo privileges to the runner account merely to satisfy this prerequisite. If that account cannot install OS packages, have an administrator install `gh` first, then verify it from the exact runner user's PATH.

Run the full command check as the exact OS user that will execute the ephemeral runner:

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

Verify them before any runner registration:

```bash
set -euo pipefail
test -d /opt/audio-validation-data
test -r /opt/audio-validation-data/datasets.seal.json
jq -e . /opt/audio-validation-data/datasets.seal.json >/dev/null
sha256sum /opt/audio-validation-data/datasets.seal.json
```

Do not rewrite or regenerate the seal merely to make validation pass.

## 4. Verify the exact frozen candidate source

Use a clean detached checkout of the frozen candidate source revision:

```bash
EXPECTED_SOURCE_SHA=01c7e0adf3ec9bcb1d401540c5e9d209176bd9ef

git fetch origin "$EXPECTED_SOURCE_SHA"
git checkout --detach "$EXPECTED_SOURCE_SHA"
test "$(git rev-parse HEAD)" = "$EXPECTED_SOURCE_SHA"
test -z "$(git status --porcelain)"
```

Then run repository preflight while explicitly requiring the blind-job command surface:

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

Require both conditions:

```bash
jq -e '
  .classification == "READY"
  and .failure_count == 0
' /tmp/audio-validation-blind-readiness.json >/dev/null
```

If this fails, do not register the runner.

## 5. Verify the full sealed public cache

Still using the exact frozen candidate source checkout:

```bash
python3 validation/tools/prepare_public_validation.py verify \
  --profile full \
  --root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json
```

If the workflow was explicitly dispatched with a DNS data root, verify that same root and pass the matching `--dns-data-root`. Do not silently substitute a different cache or seal.

## 6. Verify the blind holdout secret exists

`AP_VALIDATION_HOLDOUT_KEY` is required by the workflow and missing/empty secret material must fail closed.

From a trusted operator shell with repository access, verify only the secret name exists; never print or copy the secret value into logs or chat:

```bash
gh secret list --repo jiying2007/audio-pipeline | \
  awk '$1 == "AP_VALIDATION_HOLDOUT_KEY" { found=1 } END { exit(found ? 0 : 2) }'
```

If permission prevents this check, treat secret presence as unproven and do not register the runner.

## 7. Verify the queued blind job immediately before registration

Confirm there is exactly one intended queued `qualify-blind` job and that it is still unclaimed. For the currently frozen attempt:

```bash
gh api repos/jiying2007/audio-pipeline/actions/runs/34908798170/jobs | \
  jq -e '
    [
      .jobs[]
      | select(
          .id == 104191496884
          and .name == "qualify-blind"
          and .status == "queued"
          and .conclusion == null
          and .runner_id == 0
        )
    ]
    | length == 1
  ' >/dev/null
```

Do not register a runner if the intended job has completed, been cancelled, moved to another attempt, been claimed already, or no longer has the expected candidate/infra identity.

## 8. Register an ephemeral runner only after every admission gate passes

Use a clean, reviewed GitHub Actions runner installation directory. It must contain `config.sh` and `run.sh` and must not already be configured as another runner:

```bash
RUNNER_HOME=/opt/actions-runner-audio-validation
cd "$RUNNER_HOME"
test -x ./config.sh
test -x ./run.sh
test ! -e .runner
```

Obtain a short-lived repository runner registration token from a trusted administrator context. Do not print or persist the token:

```bash
REG_TOKEN="$(
  gh api --method POST \
    repos/jiying2007/audio-pipeline/actions/runners/registration-token \
    --jq .token
)"
test -n "$REG_TOKEN"
```

Register exactly one ephemeral runner with the existing `audio-validation` capability label:

```bash
RUNNER_NAME="audio-validation-ephemeral-$(hostname)-$$"

./config.sh \
  --unattended \
  --ephemeral \
  --url https://github.com/jiying2007/audio-pipeline \
  --token "$REG_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels audio-validation \
  --work _work

unset REG_TOKEN
```

Do **not** run `svc.sh install` and do **not** create a systemd service.

Start the foreground runner once:

```bash
./run.sh
```

The existing queued blind job should claim it naturally. Do not rerun the job and do not dispatch another blind workflow.

## 9. One job, then automatic de-registration and cleanup

An ephemeral GitHub Actions runner is automatically de-registered after processing one job. After `run.sh` exits:

1. preserve required diagnostic/audit material from `_diag` in controlled external storage if needed;
2. verify the runner no longer appears online in the repository runner inventory;
3. remove `_work` and the disposable runner directory/image;
4. keep the dataset cache and seal only if they belong to the trusted lab host and are intentionally retained.

Do not reuse an already configured runner directory for a later blind candidate. A later qualification should receive a fresh ephemeral registration.

## Result handling

Use only the machine-readable qualification decision:

- `BLIND_QUALIFIED_NON_SHIPPING`: candidate remains non-shipping and may advance only to the declared next non-shipping gate;
- `BLIND_REJECTED_NON_SHIPPING`: explicit validation `FAIL` terminalizes the exact candidate/tuning identity; do not retry, reselect, sweep thresholds, or mint a replacement nonce from the same blind evidence;
- `BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING`: infrastructure/evidence failure is non-terminal; repair the infrastructure/evidence boundary without interpreting it as an acoustic pass or fail.

Hosted CI, public/synthetic validation, QEMU, runner readiness, or ephemeral-runner success must never be used as substitutes for real PCR02/SSC305 HIL or Product Certification evidence.
