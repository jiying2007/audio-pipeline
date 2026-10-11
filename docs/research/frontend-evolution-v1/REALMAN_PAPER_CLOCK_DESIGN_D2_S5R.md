# FE03 A2 D2-S5R — Official RealMAN Paper Clock-Design Witness / 原始论文时钟设计证据

## Scope, chronology and disclosure / 研究边界

S5R is independently preregistered in [#720](https://github.com/jiying2007/audio-pipeline/issues/720). Implementation begins **only after** T0 [#718](https://github.com/jiying2007/audio-pipeline/issues/718) CLOSED on exact protected main \`d3f89e54beed483fcc0f8ce59e74b28533ed19b5\`, with fresh [Source Vetting 38110668124](https://github.com/jiying2007/audio-pipeline/actions/runs/38110668124) 9/9, [Verify 38110668384](https://github.com/jiying2007/audio-pipeline/actions/runs/38110668384) 64/64 success + one skip and required summary success, and automatic exact-main [Release 38112340555](https://github.com/jiying2007/audio-pipeline/actions/runs/38112340555) success. Independently downloaded Artifact 11691277965 SHA256: \`d4071e579fc3d45d8f47df3892c053a78a6745baad73979b0f1dc54e2db37be1\`; all four internal metadata items match their manifest.

**Historical failure is not replaced.** Strict preinstalled-extractor S5 [#716](https://github.com/jiying2007/audio-pipeline/issues/716) and unmerged Draft [#717](https://github.com/jiying2007/audio-pipeline/pull/717) failed \`S5_PREINSTALLED_PDF_TEXT_TOOL_MISSING\`; original run 38106174694 and failure Artifact 11690216460 SHA \`96644eb6cb4c9211f328a159fd7950138e91718c7e4e1a0ba08b36707b5d7c2b\` remain immutable. This study was designed after reading the publicly available recording-system sections; it is **hypothesis-informed, not blind discovery**.

## Frozen public sources / 固定唯一来源

Only the original publisher [Yang et al., RealMAN, NeurIPS 2024 Datasets and Benchmarks PDF](https://proceedings.neurips.cc/paper_files/paper/2024/file/bf8f6f5b017dc60d0c4e28a7a9a4ee7b-Paper-Datasets_and_Benchmarks_Track.pdf), DOI \`10.52202/079017-3363\`, may be acquired. Two **separate** exact-URL HTTPS downloads must be bit-identical under max 16MiB / 90s per download, no redirects, mirrors or fallback. The PDF original **SHA256 was not preregistered**; the first successful observation is explicitly identified as post-preregistration. Both publisher downloads must yield 23 pages under pinned \`PdfReader(strict=True)\`.

Use the same, separately approved official \`py-pdf/pypdf\` Git source tag \`5.4.0\`, immutable commit \`f20954f2241640feb484800e191373f8fbdfa44b\`, tree \`291be0904e532421cbc6e209e5a7875fdd610fb6\`, no package installation. Same-runner T0 623-byte synthetic-PDF readback and both negatives **precede** the first original paper download. The second original-PDF capture is independently checked after a fresh synthetic subprocess and pinned-source validation.

Only three published **author statements** can be admitted: (1) page 4 §3.1 four clock-synchronized eight-channel RME OctoMic II preamps, 48kHz and RME Digiface USB, (2) same page fisheye video recording synchronized with microphones, and (3) page 7 §3.4 100ms source-location annotation interval. A statement about hardware design is **not** a measured per-clip clock witness. These fixed semantic statements are checked in two independent Python subprocess parses of separately downloaded publisher PDF bytes.

## Decision, limits and artifacts / 决策与限制

If and only if the source, synthetic preflight, 23-page/title/three statements, two publisher original byte hashes, and independently re-parsed page-content digests all match, the research-only decision is:

\`REALMAN_D2_S5R_PUBLISHED_SHARED_CLOCK_DESIGN_COHORT_TIMEBASE_UNRESOLVED\`

Otherwise fail-closed:

\`REALMAN_D2_S5R_PUBLISHER_SOURCE_OR_DESIGN_NOT_ADMITTED\`

**Explicitly UNKNOWN:** exact original Gym CH1/3/5/7 eight-FLAC sample-zero/ADC origin; cross-channel residual skew/drift; mic gain, phase and polarity; camera-to-audio numeric sample offset; exact original Gym stem-to-CSV row time join. S3R 8/8 PCM MD5 equality is only codec-integrity evidence. D1 original full CSV remains **BLOCKED** because of 544 Car-Electric \`-10000\` distances. Neither the paper nor the 100ms label cadence supplies sample-accurate DOA ground truth, BF improvement, AEC/NS performance, physical SSC305/PCR02 qualification, shipping or commercial rights.

Artifact retention: only \`receipt.json\`, \`collect.log\`, \`verify.log\`, \`SHA256SUMS\` for 30 days. Never upload publisher PDF, extracted page text, parser Git source, binary, recordings or raw CSV. Original paper and parser temporary workspace is deleted on success **and failure** before artifact upload. No paid runner, apt/pip/sudo, shipping C/API/ABI, frozen I025–I040 NS, or E001 edits.

## Reproduction and closeout / 可复现实验与准入

Run the offline, no-network negative suite as part of canonical Verify:

\`\`\`bash
python3 tests/validation/frontend_evolution/realman_paper_clock_witness_d2_s5r.py self-test
\`\`\`

A single scope-isolated first-party Source Vetting job performs collect → independent verify → temporary deletion → SHA256SUMS → metadata-only Artifact. **Do not close #720** until PR head full Verify required \`summary=success\`, actual hosted original paper job success and independently rehashed four-file Artifact, active strict Ruleset 21804005 with no unresolved threads, protected expected-head squash merge, then **distinct new-main** Verify, Release and original-paper Source Vetting with new independently verified Artifact. The absence of a preregistered original PDF hash cannot be hidden by silently switching source versions.
