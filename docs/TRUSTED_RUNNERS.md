# Trusted Self-hosted Runner Operations

This is the normative activation runbook for the trusted self-hosted runners used by public validation, HIL and product certification.

A runner label is routing metadata, not evidence that the machine is ready. Before enabling long-running or shipping workflows, run the **Trusted Runner Readiness** workflow against the exact 40-character source commit SHA and keep its `runner-readiness.json` result with the lab/change record. The readiness JSON itself is hash-bound to that source revision.

`READY` means only that the runner satisfies the checked infrastructure prerequisites. It is never an acoustic PASS, HIL PASS or `product-certified` result.

## Roles

| Role | Labels | Readiness scope | Subsequent evidence |
| --- | --- | --- | --- |
| public validation | `self-hosted, linux, audio-validation` | Python/CMake/C compiler/Git/Git LFS; either Compact/Full seal or Extended Real catalog/cache | Compact/Full/Extended Real public-data validation |
| shipping builder | `self-hosted, linux, audio-builder` | build tools, exact shipping compiler, sysroot and toolchain root | sealed shipping binaries/build provenance |
| DUT/HIL target | `self-hosted, linux, audio-target` | Linux runner baseline plus supplied board/product input paths | HIL, real target benchmark/route soak/certification |
| lifecycle archive | `self-hosted, linux, certification-archive` | immutable archive backend command and runner baseline | validated product-lifecycle receipt |

Runner registration tokens, repository secrets and archive credentials stay outside the repository. `tools/runner_preflight.py` does not register runners and does not inspect or print secret values.

## Machine contract

`tools/runner_preflight.py` is the shared fail-closed machine contract. It emits schema-versioned JSON containing the role, runner identity available from GitHub Actions, individual checks and one classification:

- `READY`: all requested infrastructure checks passed;
- `NOT_READY`: at least one required command or path is missing/unusable.

The command exits non-zero for `NOT_READY`, so workflow use is fail-closed. Its self-test runs in the required hosted Fast Gate; hosted CI tests the contract implementation only and does not claim any self-hosted machine exists.

## Recommended activation order

### 1. `audio-validation`

1. Register an isolated Linux runner with `audio-validation` label.
2. Prepare and seal the Compact public cache using `validation/RUNNER.md`.
3. Dispatch **Trusted Runner Readiness** with role `audio-validation`.
4. Require `READY`.
5. Run **Validation Compact**: default 100 cases.
6. Run Compact `validation-grade-blind` with 20% holdout.
7. Materialize sufficient official DNS clean/noise data, reseal Full cache and rerun readiness with the DNS root.
8. Run **Validation Grade**: default 160 cases.
9. Run Full blind holdout.
10. Materialize the Extended Real `commercial-core` cache, rerun readiness with `--extended-catalog`, then run Extended Real visible + scenario-stratified blind.
11. Materialize VOiCES/AMI/ICSI and run `commercial-plus`.
12. Only after the isolated runner/cache is repeatedly healthy set `EXTENDED_REAL_ENABLED=true`; release automation then dispatches core and the weekly schedule dispatches plus.

Do not enable product/hardware claims from public validation results.

### 2. `audio-target` engineering HIL

1. Register an isolated DUT runner with `audio-target` label.
2. Install a valid `/etc/audio-pipeline/board.json` and confirm real route/power paths.
3. Dispatch **Trusted Runner Readiness** with role `audio-target`.
4. Run a reviewed manual `accelerated-pr` HIL against an exact SHA.
5. Only after the runner and board route are genuinely online set repository variable `HIL_ENABLED=true`.
6. Accumulate Nightly 1 h, post-release 8 h and Weekly 24 h evidence.

Scheduled/post-release HIL remains fail-visible while `HIL_ENABLED` is not true.

### 3. `audio-builder` + `certification-archive`

Before formal shipping certification:

1. Dispatch readiness for `audio-builder` using the exact shipping compiler, sysroot and toolchain-root paths that will be supplied to Product Certification.
2. Require `READY` and retain the JSON with the toolchain change record.
3. Dispatch readiness for `certification-archive` using the exact immutable archive command path.
4. Require `READY`.
5. Confirm the `audio-target` readiness result for the DUT/product inputs is current.
6. Run **Product Certification** with the exact commit SHA, checked-in shipping-approved policy and a soak duration meeting the policy minimum (72 h for Cortex-A32 LOW). Product Certification re-runs builder/target/archive preflight inside the same execution; external readiness is preparatory, not a substitute.

The Product Certification workflow remains the authority for exact builder/DUT separation, build/deploy/execute digest equality, real corpus/acoustic evidence, thermal/power evidence, route soak, attestation and lifecycle receipt validation.

## Direct command examples

Public validation:

```bash
python3 tools/runner_preflight.py \
  --source-revision <40-hex-commit-sha> \
  --role audio-validation \
  --data-root /opt/audio-validation-data \
  --seal /opt/audio-validation-data/datasets.seal.json \
  --output /tmp/audio-validation-readiness.json
```

Shipping builder:

```bash
python3 tools/runner_preflight.py \
  --source-revision <40-hex-commit-sha> \
  --role audio-builder \
  --shipping-cc /opt/toolchain/bin/arm-linux-gnueabihf-gcc \
  --shipping-sysroot /opt/toolchain/sysroot \
  --shipping-toolchain-root /opt/toolchain \
  --output /tmp/audio-builder-readiness.json
```

DUT/HIL target:

```bash
python3 tools/runner_preflight.py \
  --source-revision <40-hex-commit-sha> \
  --role audio-target \
  --board-manifest /etc/audio-pipeline/board.json \
  --power-input /path/to/live_power \
  --output /tmp/audio-target-readiness.json
```

Lifecycle archive:

```bash
python3 tools/runner_preflight.py \
  --source-revision <40-hex-commit-sha> \
  --role certification-archive \
  --archive-command /usr/local/bin/audio-pipeline-cert-archive \
  --output /tmp/certification-archive-readiness.json
```

## Invalidating readiness

Re-run readiness after any change to:

- runner image/OS or installed build tools;
- shipping compiler, sysroot or toolchain root;
- public dataset lock/seal/cache location;
- DUT board manifest, route, product corpus/acoustic inputs or sensor paths;
- lifecycle archive backend command/storage configuration.

A stale readiness report must not be treated as evidence for a changed machine or changed input set.
