# FE03 A2 D0 — RealMAN source metadata / 非商用真实阵列来源审查

## Authority and boundary / 研究范围

This is a **source-only metadata and negative-testing gate**, not an audio
download, DOA evaluator, performance result, or product DSP change.

The user explicitly approved **noncommercial scientific/technical research**.
The university CC BY 4.0 statement and the AISHELL CC BY-NC 4.0 data notice
do not block this limited research. Use the more restrictive noncommercial,
attribution and original-notice rules for AISHELL data. Future commercial
products, distribution of original recordings, code rights and model
weight rights remain separately controlled.

The original A1 numerical retention #691 is closed after squash #692,
fresh-main Verify 38006524852, and same-main Release 38008866026 on
4395782b9b7e7c352bff56e1c240e3751465d59e.
The first-party RealMAN source-only work follows the preregistered
[FE03 A2 rules](https://github.com/jiying2007/audio-pipeline/issues/693#issuecomment-6091562243).
Its frozen machine input is
[realman-source-metadata-d0.json](../../../.github/research/frontend-evolution-v1/realman-source-metadata-d0.json).

**Decision: REALMAN_SOURCE_METADATA_ONLY_DATA_NOT_ADMITTED.**

## Independent source identities

| Authority | Pinned revision / detail | Role |
| --- | --- | --- |
| Westlake RealMAN source | 9dc59f03a98149bc7fe5524d1363af83a5b399f7 | 32-mic native geometry code, not the dataset bytes |
| AISHELL/RealMAN dataset | fea47505cae8041f4b652b0954ba61c77d2b6df1 | Repository snapshot, not the SHA of every audio/CSV |
| Development source | val/ma_noisy_speech | Actual mixed/noisy recordings; **not** untouched blind qualification |
| Source annotation | val_static_source_location.csv and val_moving_source_location.csv | Nominal 10-Hz labels, units/time origin unverified |
| Sampling | 48-kHz native | 16-kHz resampler/delay not qualified |

The geometry has 32 physical sensors: sensor 0 at the center; three
8-microphone XY rings of radii 30, 60 and 90 mm; and other horizontal /
vertical microphones. The first-party validator independently constructs
these coordinates rather than copying an upstream baseline implementation.
Two upstream code-blob identities are retained in the machine contract.

| Profile | Original physical channels | XY rank | Max aperture |
| --- | --- | ---: | ---: |
| REALMAN_C2_INNER_OPPOSITE | [1,5] | 1 | 60 mm |
| REALMAN_C4_INNER_CARDINAL | [1,3,5,7] | 2 | 60 mm |

The future four-slot adapter maps slots 0,1,2,3 to physical channels
1,3,5,7; C2 uses slot mask 0x5 and C4 uses 0xf. Physical microphone
index and render-reference count are independent. This is **not** the
PCR02 35-mm geometry or an already-shipped 4-mic SDK.

## Metadata inspection and stop conditions / 数据解析

The Python standard-library test rejects duplicate/missing/extra semantic
CSV headers; invalid UTF-8; unsafe, noncanonical or duplicated filenames;
wrong partition or static/moving family; incorrect interval syntax;
nonfinite/out-of-range azimuth, elevation and distance; incorrect
static/moving sequence dimensions; and missing/duplicate channel paths.
Historical Unnamed index columns are accepted only as ignored metadata,
not as alternate acoustic labels.

The *future* acquisition tool must independently hash and verify exact
source CSVs, scene-RAR and selected FLAC bytes, confirm 48-kHz sample
format, four channel identities and length/synchronization, establish
the units and origin of audio/video timing fields and the sign of
the coordinate system. The source label fields include filename,
angle(°), distance, ele, real_st, real_ed, video_st and video_ed.
The presence of nominal 10-Hz values is **not** clock alignment proof.
The per-row SHA-256 binds the original text of every semantic CSV field,
including real/video start and end clocks: a metadata timing change must
not retain the same semantic receipt. This row hash does not replace the
full raw CSV SHA-256 or establish timestamp unit/alignment correctness.

Before looking at performance, select the lexically lowest eligible
shared scene and then lowest complete static and moving utterances.
Each requires original physical channels 1,3,5,7. Do not silently
join val_raw audio to val labels without exact utterance/time proof,
substitute a favorable clip or infer a missing channel by duplication.
The current tool can produce only a **provisional filename selection**,
explicitly marked as audio-not-admitted. It does not read audio,
download RARs, resample PCM or calculate a DOA score.

## Reproduce / 复验

Run the two no-dependency commands from the exact Git source checkout:

    python3 tests/validation/frontend_evolution/realman_source_metadata_d0.py --self-test
    python3 tests/validation/frontend_evolution/realman_source_metadata_d0.py --check

Existing Verify assurance executes the self-test and uses synthetic
CSV/filename inventory fixtures plus fail-closed semantic mutations.
No new workflow, paid resource, external code, shipping API, DSP default,
software version or E001 identity is introduced.

## Open next stage / 下一步

Only after real CSV and recording files have independently verified
hashes, complete channels and source-label time alignment should a new
real-array DOA comparison be preregistered. A2 will disclose all measured
failures, ULA mirror/planar elevation limits, and different native apertures.
This metadata gate does not close FE03 overall, C4 delivery, FE07/FE08/FE09,
SSC305 runtime, or real Product Certification #58.
