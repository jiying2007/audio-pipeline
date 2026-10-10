# RealMAN FE03 A2 D2-S1 — one original RAR integrity pilot / 单档案真字节核验

**Scope**: preregistered noncommercial/attribution-only research issue [#703](https://github.com/jiying2007/audio-pipeline/issues/703). This is a one-object **source-byte feasibility study**, not a DOA/beamforming experiment and not an authorization to deploy an array product. Parent [D2-S0 #701](https://github.com/jiying2007/audio-pipeline/issues/701) closed after protected [PR #702](https://github.com/jiying2007/audio-pipeline/pull/702), **same exact new main `f05eecb69ab5ac1a0968381f109510c939b53e50`** success: Verify [38038446186](https://github.com/jiying2007/audio-pipeline/actions/runs/38038446186) required `summary=success`, Release [38040079205](https://github.com/jiying2007/audio-pipeline/actions/runs/38040079205) and source vetting [38038445977](https://github.com/jiying2007/audio-pipeline/actions/runs/38038445977) all completed/success. Raw source receipt artifact 11664786609 was independently hashed on that exact SHA.

## Only one immutable archive / 唯一下载对象

| Attribute | Fixed, preregistered value |
| --- | --- |
| Dataset | `AISHELL/RealMAN@fea47505cae8041f4b652b0954ba61c77d2b6df1` |
| Role | `val/ma_noisy_speech` mixed/noisy, exposed development; not blind or `val_raw` |
| Sole path | `val/ma_noisy_speech/Gym.rar` |
| Provider-declared compressed size | **447,127,176 bytes** |
| Provider LFS SHA-256 to verify against real bytes | `8175dad412a752a34bdf2722f7e9b5ee671b62e67dfe5179f7a769d63912b2ea` |
| Hard transfer limit | **512 MiB**; one object/CI run; no retries, alternate scenes or partial resume |
| Intended result | `REALMAN_D2_S1_ONE_ARCHIVE_HASH_VERIFIED_RESEARCH_ONLY` if *actual bytes* qualify |

The Gym scene is selected **only as the smallest remotely declared archive**, to test bounded transfer/storage and optional member enumeration. It is NOT the D0 lexical scene selected for scored DOA, nor a substituted blind holdout or a user-selected high-performing environment. The other 12 scene RARs (~25 GB total including Gym) are **not downloaded**.

## Code and operational safety / 实施约束

The new Python-stdlib `tests/validation/frontend_evolution/realman_single_archive_d2_s1.py` constructs exactly one full-revision official `/resolve/` URL. It follows at most five redirects to HTTPS `huggingface.co` / subdomains or `hf.co` / subdomains; only a pinned initial source object and raw bounded byte stream may qualify. Untrusted host/URL, unexpected response status, HTML/JSON body, compression, range response, oversized size, truncated transfer, bad RAR magic, wrong length/digest or timeout => **fail closed** and retain metadata failure codes. A remote `ETag`, Git object SHA-1 or LFS oid is *not* a local byte proof. Provider-generated signed redirect query URLs must never enter a log or artifact.

- A **constant-memory first streaming SHA-256** checks every original RAR byte against frozen digest and exact size. A separate `verify` action independently re-reads the temporary on-disk archive and recomputes the entire SHA-256/magic/size and canonical receipt identity, including source-script and D2-S0 script hashes.
- If a compatible preinstalled tool (`bsdtar`, `7z` or `unrar`) can list the archive, record its executable SHA-256, version and bounded **read-only** listing identity/counts; do not extract, decode, install a third-party package or retain raw member names. A failed/unavailable tool stays `member_inventory_listed=false` and **does not turn a valid archived-byte SHA into false FLAC verification**.
- Source-authority naming cross-check comes from pinned official [RealMAN README](https://github.com/Audio-WestlakeU/RealMAN/blob/9dc59f03a98149bc7fe5524d1363af83a5b399f7/README.md) and [SSL RecordData.py](https://github.com/Audio-WestlakeU/RealMAN/blob/9dc59f03a98149bc7fe5524d1363af83a5b399f7/baselines/SSL/RecordData.py); filenames `_CH1`, `_CH3`, `_CH5`, `_CH7` are physical-C4 **candidates**, and upstream can also include `_CH0`. File names never prove the data are all present, correctly sampled, matched/clock synchronized, or captured with PCR02 array geometry.
- The **existing** `.github/workflows/research-development-dataset-source-vetting.yml` contains a separately scoped `realman-one-archive-d2-s1` job, no new workflow or privileges. No new external dependency, paid service, broad dataset download, SSH credentials or persistent storage. The original archive is stored **only** at `$RUNNER_TEMP/realman-d2-s1/Gym.rar`; independent verify is run before this file is explicitly deleted. The 30-day public CI Artifact carries **only** `receipt.json`, `collect.log`, `verify.log`, `SHA256SUMS` (no RAR, FLAC, PCM or raw CSV).
- Existing `.github/scripts/verify-docs-gate.sh` runs **network-free** `self-test` for malformed/partial/wrong-digest bytes, invalid origin, safe member path and tampered receipt. No changes to D0, D1, D1-Q, D2-S0 parser, B0 DSP, I025–I040 research, current 2.x shipping SDK/ABI or E001 physical gates.

## Explicit qualification distinction / 结果不越权

`REALMAN_D2_S1_ONE_ARCHIVE_HASH_VERIFIED_RESEARCH_ONLY` means **one real raw compressed archive matches exactly the pinned byte size and SHA-256**; it does NOT admit its internal audio FLAC bytes, sample rate, 4-mic header or content, AV annotation synchronization, speech-source azimuth ground truth, GCC-PHAT/SRP-PHAT DOA error, RT CPU/latency, commercial-use rights, SSC305 HIL, or shipped C4 firmware. A list-only member fingerprint (if possible) is independently reported and cannot substitute for FLAC-bytes/header checks.

If the upstream cannot provide the frozen byte object within the time/size/origin constraints, the result remains `REALMAN_D2_S1_SOURCE_FEASIBILITY_BLOCKED` with exact failure evidence; do not relax hash/budget/redirect rules or download different scenes. A later A2 real-acoustic/clock/multichannel verification stage requires its own preregistration and protected development/blind distinction. Noncommercial CC BY-NC use and attribution terms remain applicable; no original data redistribution or implied product license.

**All GitHub CI/Artifact source evidence in this document is research only, not a manufacturer qualification certificate.**
