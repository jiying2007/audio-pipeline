# Product Certification

`certification/` is the shipping-SKU evidence layer. Hosted CI, QEMU and public validation-grade corpora can validate software contracts, but they cannot create a `product-certified` result.

## Trust boundary

A product certification record must bind all of the following to one exact source revision and one exact target build:

- shipping SoC/revision, kernel, governor, cpuset, IRQ affinity and CPU-frequency state;
- compiler ID/version, target triple, build type and deterministic build-configuration digest;
- SHA-256 for every certification binary used to create evidence;
- real product capture/playback route and audio geometry;
- target CPU/RSS/p50/p95/p99/deadline evidence;
- measured thermal and power evidence; missing values are errors and are never replaced by zero;
- real product acoustic corpus identity and threshold results;
- real ALSA-route soak evidence for at least the policy minimum, normally 8 hours;
- a materialized evidence package whose files, sizes and SHA-256 values are revalidated before acceptance.

## Record versions

Schema v2 remains accepted for historical evidence. New product certification runs emit schema v3. v3 adds exact build identity and materialized-evidence verification while keeping the existing 1.x C API/ABI compatible.

`ap_build_info_t` remains frozen. The additive `ap_build_info_v2_t`/`ap_build_info_v2_get()` surface reports source revision, compiler, target triple, build type and a SHA-256 configuration digest without changing the original structure.

## Automated target workflow

`.github/workflows/product-certification.yml` runs only on a self-hosted Linux runner labeled `audio-target`.

The workflow performs the target-side work itself:

1. checks out the requested exact revision and embeds that revision into the build;
2. optionally verifies the shipping compiler/sysroot contract;
3. builds `ap_bench`, `ap_build_info_dump` and `ap_alsa_runtime_duplex` on the target runner;
4. runs target DSP benchmark collection while sampling RSS, thermal zones and the configured live power source;
5. runs the real ALSA capture/playback route for the requested soak duration, counting actual XRUN recoveries and runtime queue/overrun/failure counters;
6. combines those measurements with an externally supplied real-product `acoustic.json` and corpus manifest;
7. packages all evidence bytes, binaries, CMake cache and build identity, hashes them, then validates the record and every materialized evidence file;
8. uploads the immutable evidence package as a workflow artifact.

The workflow deliberately does **not** synthesize `acoustic.json`. Product acoustic evidence must come from the real microphone/speaker/enclosure corpus and test method for the shipping SKU.

## Target collectors

Synthetic DSP timing and real route stability are separate measurements:

```bash
python3 tools/target_evidence.py benchmark \
  --binary build/ap_bench --output benchmark.json \
  --seconds 120 --idle-seconds 30 --dsp-cpu 1 \
  --ambient-c 25 --power-input /path/to/live_power \
  --power-scale 1000000 --require-sensors

python3 tools/target_evidence.py route-soak \
  --binary build/ap_alsa_runtime_duplex --output soak.json \
  --capture-device hw:0,0 --playback-device hw:0,0 \
  --farend /path/to/farend.pcm --seconds 28800 \
  --sample-rate 16000 --mic-channels 2 --dsp-cpu 1 \
  --max-xruns 0 --max-overruns 0 \
  --power-input /path/to/live_power --power-scale 1000000
```

`benchmark` measures the deterministic DSP workload. `route-soak` exercises the actual ALSA route; a synthetic runtime benchmark is never labeled as an 8-hour product-route soak.

## Policies

Certification thresholds remain SKU-specific. Start from `certification/policies/example-cortex-a32-low.json`, copy it to a shipping-SKU policy, review every CPU/RSS/latency/thermal/power/acoustic/soak threshold, and pass that explicit policy to the workflow. Do not treat the example policy as measured product evidence.

Validate a completed package with:

```bash
python3 certification/validate_record.py certification-out/record.json \
  --policy path/to/sku-policy.json \
  --corpus-manifest path/to/product-corpus.json \
  --evidence-manifest certification-out/evidence-manifest.json
```

A successful software release or public validation-grade run remains separate from product certification.
