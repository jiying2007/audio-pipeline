# Product Certification

`certification/` is the shipping-SKU evidence layer. Hosted CI, QEMU and public validation-grade corpora can validate software contracts, but they cannot create a `product-certified` result.

## Trust boundary

A v4 product certification record binds all of the following to one exact source revision and one exact shipping binary set:

- shipping-approved SKU policy bytes and SHA-256;
- shipping SoC/revision, kernel, governor, cpuset, IRQ affinity and CPU-frequency state;
- exact shipping compiler executable SHA-256/version, sysroot tree SHA-256, toolchain-root SHA-256 and C flags;
- exact reviewed SKU CMake argument array and its canonical SHA-256;
- deterministic build-configuration digest and build-info identity;
- SHA-256 for every certification binary;
- distinct builder and DUT runner identities;
- exact equality of build, deployed and executed binary SHA-256 maps;
- real product capture/playback route and audio geometry;
- target CPU/RSS/p50/p95/p99/deadline evidence;
- measured thermal and power evidence; missing values are errors and are never replaced by zero;
- real product acoustic corpus identity and threshold results;
- real ALSA-route soak evidence for at least the policy minimum;
- a materialized evidence package whose files, sizes and SHA-256 values are revalidated before acceptance;
- cryptographic artifact attestation for the certification bundle;
- an immutable `product-lifecycle` archive receipt whose bundle hash matches the attested certification bundle.

## Record versions

Schema v2/v3 remain accepted as historical evidence. New formal shipping certification runs emit schema v4.

v3 added exact build identity and materialized-evidence verification. v4 adds the shipping-approved SKU policy contract plus builder/DUT separation, exact build/deploy/execute binary identity, detailed toolchain/CMake-argument provenance and deployment-provenance evidence.

The 1.x C API/ABI remains compatible. `ap_build_info_t` stays frozen; additive build identity is exposed through versioned build-info surfaces rather than by mutating the original public structure.

## Formal policy

`certification/policies/cortex-a32-low-shipping.json` is the formal repository baseline for the Cortex-A32 LOW SKU profile. It declares `shipping_approved=true` and currently requires a 72-hour route soak.

The policy is an acceptance contract, **not measured evidence and not a PASS result**. Threshold changes are reviewed product-requirement changes. Do not tune policy values inside a certification run to make failing evidence pass.

`example-cortex-a32-low.json` is explicitly `shipping_approved=false`. v4 collector/validator logic rejects example and `not-for-shipping` policies.

## Automated shipping workflow

`.github/workflows/product-certification.yml` deliberately separates build, DUT execution and long-term archive responsibilities:

```text
trusted exact source SHA
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
  combine real corpus + target performance/thermal/power + route soak
  validate v4 record -> deterministic evidence tarball -> artifact attestation
        |
        | 90-day Actions artifact is transport/cache only
        v
[self-hosted, linux, certification-archive]
  immutable product-lifecycle storage
  receipt binds archive id + bundle SHA-256 + immutable=true
  validate and attest receipt
```

The workflow deliberately does **not** synthesize `acoustic.json`. Product acoustic evidence must come from the real microphone/speaker/enclosure corpus and test method for the shipping SKU.

It also does not compile the shipping binary on the DUT. The DUT runs the exact artifact produced by the shipping builder, and the provenance verifier rejects builder/DUT identity collapse or any binary SHA mismatch.

## Required shipping inputs

A formal run requires all of the following rather than optional fallbacks:

- exact source ref/SHA;
- shipping SKU and checked-in approved policy under `certification/policies/`;
- real corpus manifest and acoustic result JSON already present on the DUT/lab environment;
- capture/playback route and real far-end PCM;
- live target power sensor and ambient condition;
- exact shipping compiler absolute path;
- exact shipping sysroot;
- exact shipping toolchain root;
- exact shipping C flags;
- reviewed shipping SKU CMake arguments supplied as a non-empty JSON string array and hash-bound in build provenance;
- soak duration meeting the checked-in policy minimum.

Critical CMake boundary variables such as compiler, sysroot, root-path modes, C flags and build type are enforced by the workflow and cannot be overridden by SKU argument input.

Missing hardware, sensor, route, archive service or toolchain input is a failed/incomplete certification run, not a degraded hosted PASS.

## Target collectors

Synthetic DSP timing and real route stability remain separate measurements. Product Certification invokes them against the exact deployed artifact, conceptually:

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

`benchmark` measures deterministic DSP workload. `route-soak` exercises the actual ALSA route. A synthetic runtime benchmark is never labeled as product-route soak evidence.

## Provenance helpers

`tools/certification_provenance.py` produces/validates build, deployed and executed snapshots. Build provenance includes compiler/sysroot/toolchain-root hashes, exact C flags, the exact CMake argument array and its canonical SHA-256; the final verifier requires binary-map equality and distinct builder/DUT runners.

`tools/ap_certify.py` assembles the v4 record and materialized evidence. `certification/validate_record.py` revalidates policy, corpus/evidence hashes, exact binaries, target metrics and v4 deployment provenance.

`certification/validate_archive_receipt.py` verifies that the lifecycle archive receipt refers to the exact certification bundle SHA-256 and asserts `retention_class=product-lifecycle` with `immutable=true`.

Validate a completed unpacked package with:

```bash
python3 certification/validate_record.py certification-out/record.json \
  --policy certification/policies/cortex-a32-low-shipping.json \
  --corpus-manifest /path/to/product-corpus.json \
  --evidence-manifest certification-out/evidence-manifest.json
```

A successful software release, public validation run, HIL engineering soak, checked-in policy or 90-day Actions artifact remains separate from formal product certification.
