# PCR02 Real Capture Bundle

This document defines the repository-internal real-device capture contract for PCR02 / SSC305 / dual 35 mm microphones. It is designed so one physical capture can be reused for BF, AEC, NS, VAD, replay, diagnostics and later evidence review without changing the immutable v2.3.16 release surface.

The bundle contract is `tests/validation/pcr02_capture_bundle.schema.json`; the executable helper is `tests/validation/pcr02_capture_bundle.py`; the fixed 42-slot scene plan is `tests/validation/pcr02_capture_plan.json`.

A sealed bundle proves that a set of user-supplied capture files is internally consistent and hash-bound. It does **not** by itself prove HIL PASS, Extended Real PASS, Product Qualification PASS or Product Certification PASS.

## Fixed product geometry

Qualification-candidate captures are bound to:

- product: PCR02;
- SoC: SSC305;
- microphone channels: 2;
- microphone spacing: 35 mm;
- sample rate: 16 kHz;
- sample format: signed 16-bit little-endian PCM;
- frame size: 160 samples / 10 ms;
- immutable release: `v2.3.16`;
- immutable release source: `57e4c64adc1cf06819e46e24e275ecd746d5f17f`.

Development captures may use another executable source SHA, but they still carry the v2.3.16 qualification authority as the reference product baseline. A `qualification-candidate` bundle fails closed unless the executed source and version are exactly the immutable v2.3.16 source/version.

## Required bundle files

Every completed slot contains five required roles:

```text
capture/<capture-id>/
├── manifest.json
├── audio/
│   ├── mic_raw.pcm
│   ├── render_reference.pcm
│   └── pipeline_output.pcm
├── frame_timeline.jsonl
└── telemetry.jsonl
```

`mic_raw.pcm` is interleaved two-channel S16LE microphone input before BF/AEC/NS/AGC. `render_reference.pcm` is mono S16LE render reference aligned to the microphone stream. `pipeline_output.pcm` is the mono on-device integrated pipeline output from the same physical execution.

All three PCM streams must represent the same number of samples. Their sample count must be an integer number of 160-sample frames. The validator derives duration from PCM bytes instead of trusting a manually entered duration.

## Capture context

Each manifest also records the low-rate physical context that would otherwise be easy to lose after the PCM files leave the device:

- `room_id` — a stable lab/room identifier, not a private street address;
- `ambient_condition` — short condition text such as `quiet-lab`, `tv-background`, `fan-on` or another controlled description;
- `speaker_volume_percent` — product playback-volume setting from 0 to 100;
- `battery_mv` — battery voltage at the start of the run;
- `charging_state` — e.g. `discharging`, `charging`, `dock`.

These fields are intentionally snapshot metadata. Values that change during the run belong in `telemetry.jsonl` or optional `system_metrics` rather than being repeatedly copied into the manifest.

## Per-frame timeline

`frame_timeline.jsonl` contains exactly one object per 10 ms audio frame. Every row must contain:

```json
{"index":0,"sequence":1000,"capture_timestamp_ns":123456789000,"render_timestamp_ns":123455789000}
```

`index` starts at zero and is contiguous. `sequence` is contiguous. Capture timestamps are strictly monotonic; render timestamps may stay equal but may not move backwards. Both timestamp streams are in the same monotonic nanosecond domain used by telemetry.

Additional per-frame fields such as `processing_time_ns`, `metadata_flags`, `lost_capture_frames`, `lost_render_frames`, AEC delay/ERLE, VAD state or quality state may be added in a separate optional `frame_metrics` file. Do not overload the minimum timeline with unstable algorithm-specific fields.

## Robot telemetry

`telemetry.jsonl` may run at a lower rate than audio, but it must span the complete capture interval in the same monotonic clock domain. Every declared telemetry signal must exist in every row.

The minimum signal set is:

- `timestamp_ns`;
- `left_motor_rpm`, `right_motor_rpm`;
- `left_foc_iq`, `right_foc_iq`;
- `left_pwm`, `right_pwm`;
- `servo_state`;
- `motion_state`.

Product integrations should add useful signals such as battery voltage/current, charging state, robot linear/angular velocity, IMU attitude, fan state and thermal state when they are available. Extra telemetry is encouraged; the minimum set is only the cross-capture correlation floor.

## Optional evidence files

The bundle accepts these additional roles without making them mandatory for all 42 slots:

- `aec_output`, `bf_output`, `ns_output`, `agc_output` — mono S16LE integrated intermediate PCM from the same execution;
- `frame_metrics` — algorithm/runtime metrics JSONL;
- `system_metrics` — CPU/RSS/thermal/power/runtime timing JSONL;
- `app_log`, `dmesg` — diagnostic logs;
- `config_snapshot` — exact effective tuning/config snapshot when the product can export one;
- `apd` — native APD v1 flight-recorder dump from the same execution.

Optional intermediate PCM must contain the same number of samples as `mic_raw.pcm`. All optional files are hash-bound into the sealed manifest.

## Initialize a capture slot

First compute the SHA-256 of the exact on-device audio binary and obtain its build fingerprint. For a v2.3.16 qualification-candidate capture:

```bash
python3 tests/validation/pcr02_capture_bundle.py new \
  --slot-id aec-07 \
  --capture-id pcr02-aec-07-unit01-run01 \
  --purpose qualification-candidate \
  --output-dir capture/pcr02-aec-07-unit01-run01 \
  --source-sha 57e4c64adc1cf06819e46e24e275ecd746d5f17f \
  --version 2.3.16 \
  --binary-sha256 <executed-binary-sha256> \
  --board-revision <board-revision> \
  --device-id <pseudonymous-device-id> \
  --room-id <lab-room-id> \
  --ambient-condition <controlled-condition> \
  --speaker-volume-percent <0-100> \
  --battery-mv <battery-millivolts> \
  --charging-state <charging-state> \
  --aec-backend <ap_build_info-value> \
  --ns-estimator <ap_build_info-value> \
  --simd-backend <ap_build_info-value> \
  --resampler-mode <ap_build_info-value>
```

To attach data that are available on this run, add one or more optional roles at creation time, for example:

```bash
  --optional-file apd=diagnostics/source.apd \
  --optional-file frame_metrics=frame_metrics.jsonl \
  --optional-file system_metrics=system_metrics.jsonl \
  --optional-file dmesg=logs/dmesg.txt
```

The `new` command creates an **unsealed working manifest** and the required parent directories. It does not create audio, timeline or telemetry bytes and it cannot be treated as real evidence.

## Record on the DUT

Write the required files to the paths declared by `manifest.json`. Capture microphone, render reference and integrated output from the same physical execution; do not splice unrelated runs together.

For self-noise slots the render reference may legitimately be digital silence, but it is still recorded so the file geometry and time relationship stay explicit. For AEC slots, capture the actual render reference fed into the echo path, not a source file that bypasses device buffering/resampling.

When APD is enabled, keep APD v1 unchanged. The bundle does not synthesize or reinterpret APD records; it only hash-binds an optional native `.apd` file alongside the broader product telemetry.

## Seal and validate

After a physical run finishes:

```bash
python3 tests/validation/pcr02_capture_bundle.py seal \
  --manifest capture/pcr02-aec-07-unit01-run01/manifest.json
```

`seal` fails unless:

- all required files exist beneath the bundle root;
- dual-mic/render/output PCM sample counts agree;
- PCM contains an integer number of 10 ms frames;
- timeline row count matches audio frames;
- sequence and monotonic timestamps are valid;
- telemetry includes all declared signals and covers the full capture interval;
- the scene exactly matches its 42-slot plan entry;
- a qualification-candidate uses exact v2.3.16 source/version.

It then writes actual file byte sizes and SHA-256 hashes, derives `duration_seconds`, sets `real_capture=true`, and computes one canonical `bundle_digest_sha256` over metadata plus file bindings. A sealed manifest is treated as immutable; correcting a physical capture requires a new capture ID/run.

Independent verification is:

```bash
python3 tests/validation/pcr02_capture_bundle.py validate \
  --manifest capture/pcr02-aec-07-unit01-run01/manifest.json
```

Any post-seal modification to a bound PCM, timeline, telemetry, log or APD file causes validation to fail because its byte count and/or SHA-256 no longer matches the sealed manifest.

## Offline replay

The capture bundle can replay the dual-mic + render streams through a candidate `ap_process_pcm` and compare the result with the on-device integrated output:

```bash
python3 tests/validation/pcr02_capture_bundle.py replay \
  --manifest capture/pcr02-aec-07-unit01-run01/manifest.json \
  --processor ./build/ap_process_pcm \
  --output-pcm replay.pcm
```

Use `--require-bit-exact` only when the complete effective runtime configuration and processor build are known to be equivalent. A replay against a different build/tuning is A/B evidence, not deterministic reproduction or causal proof.

## APD inspection and diagnosis

If the bundle includes the optional `apd` role, the file remains a normal APD v1 dump. The released tools still work directly:

```bash
python3 tools/apdump.py info capture/.../diagnostics/source.apd
python3 tools/apdump.py extract capture/.../diagnostics/source.apd --output-dir extracted
python3 tools/apreplay.py capture/.../diagnostics/source.apd \
  --processor ./build/ap_process_pcm \
  --output-pcm apd-replay.pcm
```

For the repository-internal one-command triage/diagnosis chain:

```bash
python3 tests/validation/pcr02_capture_bundle.py diagnose \
  --manifest capture/pcr02-aec-07-unit01-run01/manifest.json \
  --processor ./build/ap_process_pcm \
  --processor-build-info processor-build-info.json \
  --output-dir diagnosis \
  --stage-counterfactuals
```

This delegates the attached APD to `tests/diagnostics/aptriage.py` and then `apdiagnose.py`, producing hash-bound triage/diagnosis references plus `capture-analysis.json`. The diagnosis remains heuristic and explicitly keeps `causal_proof=false`.

## 42-slot acquisition order

The existing plan remains 42 slots rather than multiplying the scene count:

- 16 BF geometry slots: 0/30/60/90 degrees × 0.5/1/2/3 m;
- 14 self-noise slots: idle/straight/turning/acceleration/braking/servo/floor-transition × hard floor/carpet;
- 12 AEC product-path slots: speaker-only/double-talk × idle/straight/turning × hard floor/carpet.

The richer bundle format increases the evidence captured **inside each slot** instead of creating a much larger scene matrix. Additional rear-field, mic-fault, speaker-volume sweep or long-duration stress runs can be added later as separate development captures after the base 42-slot product set exists.

## Privacy and evidence boundary

Raw microphones may contain private speech. Product/lab operators are responsible for consent, access control, retention, encryption at rest/in transit and secure erasure.

A capture bundle is measurement evidence only. `evidence_claims.hil_pass`, `extended_real_pass`, `product_qualification_pass` and `product_certification_pass` are structurally forced to `false`. Those states can only be established by their separate reviewed workflows and retained physical evidence. Issue #58 remains the authority for the still-missing external PCR02/HIL/Extended Real/Product Certification evidence.
