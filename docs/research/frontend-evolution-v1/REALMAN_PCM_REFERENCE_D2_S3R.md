# FE03 A2 D2-S3R — Original eight FLAC-to-PCM integrity / 八路原始音频解码校验

## Independent research authorization / 独立预注册

[D2-S3R issue #711](https://github.com/jiying2007/audio-pipeline/issues/711) was registered before any source-built original RealMAN decode. It is NOT a retroactive pass of original failed [D2-S3 #707](https://github.com/jiying2007/audio-pipeline/issues/707) or unmerged [Draft #708](https://github.com/jiying2007/audio-pipeline/pull/708), which remains blocked by unavailable preinstalled decoder.

Predecessor [D2-T0 #709](https://github.com/jiying2007/audio-pipeline/issues/709) is CLOSED: protected [#710](https://github.com/jiying2007/audio-pipeline/pull/710) merged main **feb2f8ebc17a25bf248a63139ea4a219de39545d**; matching Verify **38063778210** 64 success + one skip, required summary success; Release **38065749535** success; source **38063778040** 6/6 success. Independent toolchain Artifact **11673859179**, ZIP SHA256 **73269e2c809d88838a835bd397b57a6613599990a4c97508f1c00e3b653773dd**, receipt SHA256 **9b47aa74da3b7533d8fbb1b4985a727114fdafd245dd5895656fb737b389b807**. This proved synthetic reference decoding ONLY.

## Fixed original dataset / 原始数据身份冻结

- Only official AISHELL/RealMAN revision **fea47505cae8041f4b652b0954ba61c77d2b6df1**, one archive **val/ma_noisy_speech/Gym.rar**, **447127176 bytes**, SHA256 **8175dad412a752a34bdf2722f7e9b5ee671b62e67dfe5179f7a769d63912b2ea**. Max 512MiB / 13 minutes. No source, scene or fallback alternatives.
- Original [D2-S2 #705](https://github.com/jiying2007/audio-pipeline/issues/705) exact-main [source 38050714903](https://github.com/jiying2007/audio-pipeline/actions/runs/38050714903), sealed Artifact **11669252369**, ZIP SHA256 **298432f0d6b8ceb69d48d62c0d2bdf8f42dee6383534b48109d4a80f7719870a**, receipt SHA256 **16e690a4b32f0aeb9f011900af55f83f302a6f29662f2bb1601c058257ae3190**. Frozen path/stem hashes, exactly eight FLAC file bytes/SHA and original STREAMINFO are preserved in first-party frozen metadata JSON, not selected by acoustic score.
- One **lexically first complete static** quartet and one **lexically first complete moving** quartet, physical CH1/CH3/CH5/CH7. Mono native **48kHz / 16-bit**. Each static channel **238895 samples / 477790 signed S16LE bytes**, each moving **237071 samples / 474142 bytes**. All eight calculated decoded PCM MD5 values MUST exactly equal the original distinct nonzero STREAMINFO PCM MD5 values. Retain decoded SHA256 for eight streams.

## Same-runner reference builder and original decode / 同 runner 完整验证

1. Before accessing original audio, run the existing first-party T0 source-only build and two synthetic bit-exact proofs on this very runner. Official Xiph FLAC tag **1.4.3** exact upstream commit **28e4f0528c76b296c561e922ba67d43751990599**, tree **9d1cf0c77df717e633c9020eb60c87642beb9037**. CMake target **flacapp** builds version **flac 1.4.3**. Preinstalled Git/GCC/CMake only; no apt, pip, sudo, paid service, prebuilt binary or artifact executable reuse. Source <=128MiB, CLI <=64MiB, clone <=120 seconds, configure/build <=8 minutes, max two build jobs. Verify source tree, executable SHA/version, synthetic 514-byte exact SHA/MD5 and corrupt FLAC negative before original download.
2. Stream-download and rehash exactly the pinned 447MB original RAR, then reuse S2's exact 7z member inventory and fixed first static/moving CH1/3/5/7 lexical selection. Reject any changed path hash, data SHA, length or native STREAMINFO. Each selected FLAC <=32MiB; combined <=128MiB; extraction <=75s/member and <=180s total. No path-controlled extraction, wildcard, repair or re-selection.
3. Decode each original file with the ephemeral fixed Xiph native CLI into a **bounded constant-memory S16LE hashing pipe**, no output PCM file, WAV header, gain, resampling, filters, reordering or mixing. Exact raw byte lengths, exit code 0, original declared PCM MD5 for all **8/8**. <=30s per stream, <=180s total.
4. Independently re-read full original RAR SHA, eight original FLAC byte hashes/headers, provenance and every decoded PCM MD5+SHA **a second time**. Compare canonical receipt and independently rebuilt data, not merely first-pass success.
5. Always delete all temporary source/build binaries, original RAR, eight FLACs and any synthetic files before metadata-only public Artifact. Retain **only** receipt.json, collect.log, verify.log and SHA256SUMS for 30 days; never upload GPL binary/source, original recordings, decoded PCM, original CSV rows or waveforms.

Only complete source/PCM readback yields **REALMAN_D2_S3R_GYM_8_PCM_MD5_VERIFIED_RESEARCH_ONLY**. Any failure yields **REALMAN_D2_S3R_PCM_BYTES_NOT_ADMITTED**, with exact reason; do not relax thresholds or try alternative files.

## CI governance / 自动化治理

Reuse existing GitHub source-vetting workflow and offline Verify tests. One S3R job, no separate controller and no duplicate S1/S2 original RAR transfer or T0 reference build on S3R-only source changes. Require actual hosted original 8/8 source proof and independently hashed metadata Artifact, exact PR-head full Verify required summary success, zero unresolved reviews and active strict squash-only main Ruleset 21804005. Protected expected-head squash only after complete evidence; distinct fresh-main Verify, Release and original source-vetting replay before [#711](https://github.com/jiying2007/audio-pipeline/issues/711) closure.

## Restrictions / 研究边界

Noncommercial RealMAN source with attribution, GPL reference CLI built ephemerally without redistribution. Exposed-development file/codec integrity, NOT blind testing. Passing 8/8 cannot prove synchronized capture sample-zero clocks, microphone phase response, physical DOA ground truth, BF array gain, AEC/NS quality, camera timestamp alignment, SSC305 CPU/RAM/p99, E001 HIL or commercial product authorization. Original D1 CSV still BLOCKED due 544 Car-Electric -10000 distances. Frozen I025–I040 and shipping C/ABI unchanged.
