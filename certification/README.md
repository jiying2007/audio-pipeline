# Product Certification

`certification/` is the shipping-SKU evidence layer. Hosted CI, QEMU and public validation-grade corpora can validate software contracts, but they cannot create a `product-certified` result.

## Current record contract

The v2 repository accepts **schema v4 only** for formal product certification. `tools/ap_certify.py` emits the release-source v4 payload and the current Product Certification control plane adds the immutable GitHub Release identity before final validation, attestation and archival. `certification/validate_record.py` rejects older certification schemas. Historical v1.x v2/v3 records may be retained externally for audit history, but they are not accepted as current shipping evidence and must not be used to satisfy v2 certification gates.

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

`record.json` is a core evidence document, not by itself the final lifecycle authority. Formal completion requires the **Product Certification workflow** to finish successfully through the `certification-archive` job, including validation of the immutable `product-lifecycle` archive receipt for the exact final bundle hash. A locally assembled record, a transport artifact, or an otherwise valid record without that workflow/archive lineage must not be interpreted as final Product Certification PASS.

## Formal policy

`certification/policies/cortex-a32-low-shipping.json` is the formal repository baseline for the Cortex-A32 LOW SKU profile. It declares `shipping_approved=true` and requires a 72-hour route soak.

The policy is an acceptance contract, **not measured evidence and not a PASS result**. Threshold changes are reviewed product-requirement changes. Never tune policy values inside a certification run to make failing evidence pass.

`example-cortex-a32-low.json` is explicitly `shipping_approved=false`; the collector/validator rejects example and `not-for-shipping` policies.

## Trusted runner readiness

Before allocating a formal certification run, dispatch **Trusted Runner Readiness** against the exact immutable release source for `audio-builder`, `audio-target`, and `certification-archive`. Require `READY` for the exact shipping compiler/sysroot/toolchain paths, DUT product-input paths and immutable archive command that will be used. See [`docs/TRUSTED_RUNNERS.md`](../docs/TRUSTED_RUNNERS.md).

Readiness is an infrastructure prerequisite only. It is not acoustic/HIL/product evidence.

## Automated shipping workflow

`.github/workflows/product-certification.yml` separates release binding, build, DUT execution and long-term archive responsibilities:

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
  combine immutable release identity + real corpus + target performance/thermal/power + route soak
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

The workflow deliberately does **not** synthesize `acoustic.json` and does not compile the shipping binary on the DUT. Product acoustic evidence must come from the real microphone/speaker/enclosure corpus and the DUT executes the exact artifact produced by the shipping builder.

## Required shipping inputs

A formal run requires:

- an annotated semantic Git tag with a non-draft, non-prerelease, immutable GitHub Release;
- the exact source SHA to which that tag resolves; `release_tag` must equal `v<project-version>` and both identities must match before any self-hosted hardware allocation;
- a reviewed DUT board manifest; when the workflow input is blank, the `audio-target` runner resolves `AUDIO_PIPELINE_LAB_BOARD`, XDG config, then `$HOME/.config/audio-pipeline/board.json`; explicit absolute system-mode paths remain supported;
- shipping SKU and approved checked-in policy;
- real corpus manifest and acoustic result JSON already present on the DUT/lab environment;
- capture/playback route and real far-end PCM;
- live target power sensor and ambient condition;
- exact shipping compiler absolute path, sysroot and toolchain root;
- exact shipping C flags;
- reviewed non-empty shipping SKU CMake argument JSON array;
- soak duration meeting the checked-in policy minimum.

Critical CMake boundary variables such as compiler, sysroot, root-path modes, C flags and build type are workflow-owned and cannot be overridden by SKU arguments.

Missing release identity, hardware, sensor, route, archive service, corpus or toolchain input is failed/incomplete certification, not a degraded hosted PASS.

## Target collectors

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

`benchmark` measures deterministic DSP workload. `route-soak` exercises the actual ALSA route. A synthetic runtime benchmark is never labeled product-route soak evidence.

## Provenance helpers

`tools/certification_provenance.py` produces/validates build, deployed and executed snapshots. `tools/ap_certify.py` assembles the release-source v4 record and materialized evidence. The Product Certification control plane then seals the immutable Release identity into the evidence set and record before validation. `certification/validate_record.py` revalidates policy, corpus/evidence hashes, exact binaries, target metrics and deployment provenance. `certification/validate_archive_receipt.py` validates the immutable lifecycle receipt.

For diagnostic inspection of an unpacked bundle, the record/evidence validator can be run as follows:

```bash
python3 certification/validate_record.py certification-out/record.json \
  --policy certification/policies/cortex-a32-low-shipping.json \
  --corpus-manifest /path/to/product-corpus.json \
  --evidence-manifest certification-out/evidence-manifest.json
```

That command validates the record/evidence contract only; it is **not** a replacement for the successful Product Certification workflow, final bundle attestation, or validated immutable archive receipt.

A successful software release, public validation run, HIL engineering soak, checked-in policy, locally valid record or Actions artifact remains separate from formal Product Certification.