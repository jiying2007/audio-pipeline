# FE03 A2 D2-S5-T0 — pinned pure-Python PDF toolchain, synthetic only / 无付费 PDF 解码参考资格

## Separate from original failed S5 / 独立协议

[T0 prereg #718](https://github.com/jiying2007/audio-pipeline/issues/718) is an independent synthetic-only reference-tool study. Original [S5 #716](https://github.com/jiying2007/audio-pipeline/issues/716) and **Draft PR #717** have not passed: [Source Vetting 38106174694](https://github.com/jiying2007/audio-pipeline/actions/runs/38106174694) failed due to `S5_PREINSTALLED_PDF_TEXT_TOOL_MISSING`. Immutable negative evidence [Artifact 11690216460](https://github.com/jiying2007/audio-pipeline/actions/runs/38106174694/artifacts/11690216460), ZIP SHA256 `96644eb6cb4c9211f328a159fd7950138e91718c7e4e1a0ba08b36707b5d7c2b`. Do not retrofit #716/#717 to accept alternate parsers; synthetic T0 is not paper clock proof.

## One frozen official source / 唯一授权工具链

Official [py-pdf/pypdf](https://github.com/py-pdf/pypdf) tag `5.4.0`; annotated tag object `6e3ae92515aefb7add4dae40fc840ad77274ba57`, exact source commit **`f20954f2241640feb484800e191373f8fbdfa44b`**, Git tree **`291be0904e532421cbc6e209e5a7875fdd610fb6`**. BSD 3-Clause-style source notice and attribution preserved. Shallow sparse checkout into ephemeral runner directory, <=128MiB total source+git, <=120s fetch. Preinstalled Git and Python>=3.11 only. Direct import from pinned clean source, no pip, apt, wheel, installed executable, package or source redistribution. Retain interpreter and Git binary versions/digests, source path, origin, commit, tree and LICENSE SHA.

## Synthetic-only bitwise tests / 严格参考输入

- First-party standard library constructs one minimal 1-page Helvetica PDF <64KiB with fixed ASCII phrase `SYNTHETIC CLOCK SOURCE TEST 257 UNMODIFIED`; no original NeurIPS paper, audio, RAR, FLAC, PCM or CSV row.
- Two fresh pinned `PdfReader(strict=True)` instances must read exactly one page and identical sentence; truncated PDF must be rejected; equal-length tampered text must never match. Run another independent Python interpreter process from the same pinned source, regenerate and compare synthetic PDF SHA, extracted text SHA and source tree.
- Wrong Git revision/tree, unclean source, altered LICENSE, changed package version/import source, malformed original PDF, corrupted fixture or duplicate JSON must fail closed. No alternate upstream revision, paid runner or fuzzy text tolerance.

## Decision, licensing and CI / 研究边界与治理

Success is only `REALMAN_D2_S5_T0_PINNED_PYPDF_SYNTHETIC_QUALIFIED_ONLY`; otherwise `REALMAN_D2_S5_T0_PDF_REFERENCE_NOT_QUALIFIED`. Both expressly imply no original NeurIPS publisher PDF was downloaded and no proof of any original Gym sample-zero, four-channel common hardware capture clock, DOA/BF/AEC/NS scores, product shipping or commercial authorization.

Reuse existing research source-vetting workflow in one strictly T0 path-scoped job. Original 447MB Gym RAR, source CSV and original S5 publisher-PDF fetch all skipped. Execute first-party offline negative fixtures through canonical Verify docs gate. Clean all Git source/parser files and synthetic temporary data before publishing **only** receipt.json, collect.log, verify.log and SHA256SUMS for 30 days. Protected expected-head squash only after exact-head full Verify required summary success, hosted T0 synthetic source proof, independent Artifact SHA and zero unresolved threads; distinct fresh-main Verify/Release/source proof before #718 closure.

After successful full T0 closure, a future **separately preregistered S5R** may use the *same* immutable pypdf toolchain, a fresh same-runner synthetic proof, and the one official NeurIPS paper under finite source/readback limits. Original S5 #716 strict preinstalled-only failure and S4 #713 unresolved clock classification remain immutable historical evidence.
