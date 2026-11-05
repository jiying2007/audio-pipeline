# Retired product-certification records (historical only)

> **Archive warning (research only).** The former product-certification publication workflow is not present in active GitHub Actions. The procedures, identifiers, schemas and thresholds below document a retired historical evidence system; they are **not runnable current release instructions** and cannot authorize any model, SDK, dataset, source change or target-device measurement. Current research uses [research execution](../docs/RESEARCH_ONLY_EXECUTION.md) and the explicitly requested [HIL research experiment](../hil/README.md). Original historical Git/Actions receipts remain unchanged.

The retained `certification/` namespace records the former shipping-SKU evidence contract. Its validators may still be inspected offline for audit/regression, but no current scientific workflow consults them for source acceptance. Hosted CI, QEMU, real-audio research and physical HIL have their own independent evidence limits; none creates a product-approval result.

## Historical record contract (retired)

The retired v2-era procedure used **schema v4** for product-era receipts. `tools/ap_certify.py` created a release-source v4 payload, and the now-retired publication workflow formerly bound an immutable GitHub Release identity for archival review. `certification/validate_record.py` still checks that historical schema; it is **not** a current research gate. Older v1.x/v2/v3 records remain audit-only and must not be relabeled as fresh evidence.

A formal v4 certification bundle binds all of the following to one immutable GitHub Release, one exact source revision and one exact shipping binary set:

- annotated semantic release tag, numeric GitHub Release id, `immutable=true`, `draft=false`, `prerelease=false`, and the exact release source revision;
- release tag version equality with the certified binary/project version;
- shipping-approved SKU policy bytes and SHA-256;
- shipping SoC/revision, kernel, governor, cpuset, IRQ affinity and CPU-frequency state;
- exact shipping compiler executable SHA-256/version, sysroot tree SHA-256, toolchain-root SHA-256 and C flags;
- exact reviewed SKU CMake argument array and canonical SHA-256;
- deterministic build-configuration digest from `ap_build_info()`;
- SHA-256 for every certification binary;
- distinct builder and DUT runner identities;
- exact equality of build, deployed and executed binary SHA-256 maps;
- real product capture/playback route and audio geometry;
- target CPU/RSS/p50/p95/p99/deadline evidence;
- measured thermal and power evidence; missing values are errors and are never replaced by zero;
- real product acoustic corpus identity and threshold results;
- real ALSA-route soak evidence for at least the policy minimum;
- a materialized evidence package whose files, sizes and SHA-256 values are revalidated before acceptance;
- cryptographic artifact attestation for the final certification bundle;
- an immutable `product-lifecycle` archive receipt whose bundle hash matches that attested certification bundle.

`record.json` is a core evidence document, not by itself the final lifecycle authority. Under the historical process, formal completion would have required the **now-retired Product Certification workflow** to finish successfully through the `certification-archive` job, including validation of the immutable `product-lifecycle` archive receipt for the exact final bundle hash. A locally assembled record, a transport artifact, or an otherwise valid record without that workflow/archive lineage must not be interpreted as final Product Certification PASS.

## Archived formal policy (not current research authority)

`certification/policies/cortex-a32-low-shipping.json` is a frozen historical Cortex-A32 LOW policy sample. Its `shipping_approved=true` and 72-hour minimum are **archived policy fields**, not research execution prerequisites or evidence that a real device passed.

The policy is an acceptance contract, **not measured evidence and not a PASS result**. Threshold changes are reviewed product-requirement changes. Never tune policy values inside a certification run to make failing evidence pass.

`example-cortex-a32-low.json` is explicitly `shipping_approved=false`; the collector/validator rejects example and `not-for-shipping` policies.

## Historical trusted-runner readiness (retired)

The former procedure called for **Trusted Runner Readiness** against the exact immutable release source for `audio-builder`, `audio-target`, and `certification-archive`. Require `READY` for the exact shipping compiler/sysroot/toolchain paths, the reviewed DUT board manifest and product evidence paths, and the immutable archive command that will be used. See [`docs/TRUSTED_RUNNERS.md`](../docs/TRUSTED_RUNNERS.md).

Readiness is an infrastructure prerequisite only. It is not acoustic/HIL/product evidence.

## Retired automated workflow architecture

The deleted `.github/workflows/product-certification.yml` historically separated release binding, build, DUT execution and long-term archive responsibilities (diagram retained for audit only):

```text
annotated immutable GitHub Release tag
        |
        | tag -> exact source SHA; immutable=true; draft=false; prerelease=false
        v
trusted exact release source SHA
        |
        v
[self-hosted, linux, audio-builder]
  exact shipping compiler/sysroot/C flags/CMake arguments
  build binaries -> seal build/toolchain provenance
        |
        | short-lived transport artifact
        v
[self-hosted, linux, audio-target]
  verify transport hash -> deploy exact binaries
  collect deployed hash -> execute build-info/benchmark/real ALSA route
  collect executed hash
  require build == deployed == executed
  derive route/power only from the reviewed board manifest
  seal the board bytes/SHA-256 with immutable release identity + real corpus + target performance/thermal/power + route soak
  validate v4 record/evidence -> deterministic bundle -> artifact attestation
        |
        | Actions artifact is transport/cache only
        v
[self-hosted, linux, certification-archive]
  immutable product-lifecycle storage
  receipt binds archive id + final bundle SHA-256 + immutable=true
  validate and attest receipt
        |
        v
formal Product Certification workflow PASS
```

That retired workflow deliberately did **not** synthesize `acoustic.json` and does not compile the shipping binary on the DUT. Product acoustic evidence must come from the real microphone/speaker/enclosure corpus and the DUT executes the exact artifact produced by the shipping builder.

## Former shipping inputs (historical checklist)

The retired formal procedure required:

- an annotated semantic Git tag with a non-draft, non-prerelease, immutable GitHub Release;
- the exact source SHA to which that tag resolves; `release_tag` must equal `v<project-version>` and both identities must match before any self-hosted hardware allocation;
- a reviewed DUT board manifest; when the workflow input is blank, the `audio-target` runner resolves `AUDIO_PIPELINE_LAB_BOARD`, XDG config, then `$HOME/.config/audio-pipeline/board.json`; that manifest is the single authority for capture/playback, far-end PCM, sample rate, microphone count, DSP CPU, live power sensor and power scale, and its bytes are sealed into the certification evidence bundle;
- shipping SKU and approved checked-in policy;
- real corpus manifest and acoustic result JSON already present on the DUT/lab environment;
- ambient condition; route/power fields are deliberately not separate Product Certification workflow inputs;
- exact shipping compiler absolute path, sysroot and toolchain root;
- exact shipping C flags;
- reviewed non-empty shipping SKU CMake argument JSON array;
- soak duration meeting the checked-in policy minimum.

Critical CMake boundary variables such as compiler, sysroot, root-path modes, C flags and build type are workflow-owned and cannot be overridden by SKU arguments.

Missing release identity, hardware, sensor, route, archive service, corpus or toolchain input is failed/incomplete certification, not a degraded hosted PASS.

## Target collectors (reusable research measurements)

Synthetic DSP timing and real route stability remain separate measurements:

```bash
python3 tools/target_evidence.py benchmark \
  --binary /deployed/exact/ap_bench --output benchmark.json \
  --seconds 120 --idle-seconds 30 --dsp-cpu 1 \
  --ambient-c 25 --power-input /path/to/live_power \
  --power-scale 1000000 --require-sensors

python3 tools/target_evidence.py route-soak \
  --binary /deployed/exact/ap_alsa_runtime_duplex --output soak.json \
  --capture-device hw:0,0 --playback-device hw:0,0 \
  --farend /path/to/farend.pcm --seconds 259200 \
  --sample-rate 16000 --mic-channels 2 --dsp-cpu 1 \
  --max-xruns 0 --max-overruns 0 \
  --power-input /path/to/live_power --power-scale 1000000
```

`benchmark` measures deterministic DSP workload. `route-soak` exercises the actual ALSA route. The commands above are low-level source-locked measurement examples only. For current device studies use the explicit HIL research runbook and actual private board manifest; no product-certification workflow derives these inputs anymore. A synthetic runtime benchmark is never labeled product-route soak evidence.

## Retired certification generators; guarded historical replay

The old `tools/ap_certify.py` and `tools/certification_provenance.py` no longer exist in the active research source tree. Their exact original source, signed/hashed historical evidence and prior workflow runs remain recoverable through Git history. They cannot now mint `product-certified` payloads in current research. The preserved `certification/validate_record.py` and `certification/validate_archive_receipt.py` are **read-only historical format auditors**, default-deny on ordinary invocation and require `--historical-replay-only` for deliberate offline replay. A successful historical replay does not authorize publication, research data admission, HIL/DUT status or model promotion.

For diagnostic inspection of an unpacked bundle, the record/evidence validator can be run as follows:

```bash
python3 certification/validate_record.py --historical-replay-only certification-out/record.json \
  --policy certification/policies/cortex-a32-low-shipping.json \
  --corpus-manifest /path/to/product-corpus.json \
  --evidence-manifest certification-out/evidence-manifest.json
```

That command checks the archived record/evidence schema only. It is **not** an active research acceptance path, real SSC305/HIL observation, or permission to publish a product release.

For current research, source and data rights, independent acoustic evaluation and genuine physical target measurements are assessed on their own evidence; old product-certification status has no approval authority. Preserve historical receipts without manufacturing new PASS.