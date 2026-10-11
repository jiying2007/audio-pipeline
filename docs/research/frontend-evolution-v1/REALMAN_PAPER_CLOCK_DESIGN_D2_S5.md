# FE03 A2 D2-S5 — NeurIPS RealMAN published shared-clock recording system / 官方论文共享时钟证据

## Independent preregistration / 先验研究范围

The separately preregistered [issue #716](https://github.com/jiying2007/audio-pipeline/issues/716) is **unblocked only after** the preceding [D2-S4 #713](https://github.com/jiying2007/audio-pipeline/issues/713) was closed on protected main **`373008e89f2ebaabc298d2c9613420b1d4811c78`**, exact-main [Verify `38104075774`](https://github.com/jiying2007/audio-pipeline/actions/runs/38104075774) **64 success + one skip, required `summary=success`**, exact-SHA [Release `38105765036`](https://github.com/jiying2007/audio-pipeline/actions/runs/38105765036) **2/2 success**, and original source [Vetting `38104075673`](https://github.com/jiying2007/audio-pipeline/actions/runs/38104075673) **8/8 success** with independently verified metadata-only Artifact **11688862857**, ZIP SHA256 **`cf0b7993c8a3b6cf795a5809d3eb4ff44bbef984c1004e54ddc95a5ef9776a3d`**. Frozen S4 decision `REALMAN_D2_S4_CAPTURE_TIMEBASE_UNRESOLVED` is unchanged.

**This study is exposed/disclosed, not a blind experiment.** Before preregistration the official NeurIPS RealMAN paper had been read at recording-system §3.1 and annotation §3.4. The paper describes **four clock-synchronized eight-channel RME OctoMic II microphone preamplifiers** recording 32-ch BP899 microphone arrays at 48kHz via RME Digiface USB and a HIKVISION fisheye camera described as synchronized with audio. This is a legitimate **authors' published system design assertion** absent from the three files examined at S4, not an independent measurement of the distributed audio clips.

## Frozen paper source and finite budget / 唯一审查资源

- Yang et al., RealMAN, *NeurIPS 2024 Datasets and Benchmarks*, DOI **10.52202/079017-3363**, publisher official paper **[PDF](https://proceedings.neurips.cc/paper_files/paper/2024/file/bf8f6f5b017dc60d0c4e28a7a9a4ee7b-Paper-Datasets_and_Benchmarks_Track.pdf)**; exactly this URL over HTTPS, no redirects/mirrors/arXiv alternate or body substitution. Expected 23-page paper, §3.1 **PDF page 4**, §3.4 **PDF page 7**.
- Max 16MiB publisher PDF, <=90s source transfer, one first pass and one independently fetched **bitwise identical** second pass. Do not infer a PDF pre-registration SHA: it was **not hashed before this preregistration**. Receipt explicitly retains `publisher_pdf_binary_sha_preregistered=false`; both actual run-time SHA256 and original byte length must match exactly across two independent provider fetches and separately across PR vs fresh main.
- Only host-preinstalled, version/SHA-recorded `pdftotext` for short excerpts **in process memory**, no apt/pip/sudo, paid service, third-party binary, alternate OCR/PDF source, or PDF/text redistribution. If executable or publisher unavailable, fail with `REALMAN_D2_S5_PAPER_SOURCE_OR_CLAIMS_NOT_ADMITTED` and preserve its original failure, never change question after seeing outcome.

## Exactly three author-reported claims / 实际可证明边界

| Authority dimension | Required evidence on pinned paper | Can claim? |
| --- | --- | --- |
| Common recording clock *design* | §3.1 states four clock-synchronized eight-channel preamps and Digiface USB at 48kHz | **Yes, as author-stated hardware design only** |
| General camera-to-audio sync *design* | §3.1 describes a fisheye camera capturing the recording in sync | **Yes, as author-stated acquisition design only** |
| Source location label sampling | §3.4 fixes source annotation resolution to 100ms | **Yes, as coarse label cadence only** |
| Exact archived Gym CH1/3/5/7 file sample-zero | No per-clip acquisition start-offset receipt | **No** |
| Measured per-clip channel skew/drift/polarity or gain | No per-microphone calibration time series | **No** |
| Numeric source-video-to-PCM frame origin | No exact per-recording camera-audio sample offset | **No** |
| Exact frozen Gym FLAC hash-to-CSV timestamp/row join | Original D1 CSV remains blocked and S4 lacks row-level clock proof | **No** |

Result limited to **`REALMAN_D2_S5_PUBLISHED_SHARED_CLOCK_DESIGN_COHORT_TIMEBASE_UNRESOLVED`** on complete independently repeated publisher evidence. Failure/unavailable source gives **`REALMAN_D2_S5_PAPER_SOURCE_OR_CLAIMS_NOT_ADMITTED`**, not generic UNKNOWN. Neither result authorizes sample-perfect TDOA/DOA ground truth nor BF array-gain/NS/AEC comparison.

## Privacy, security, regression and end-state governance

Only canonical `receipt.json`, `collect.log`, `verify.log`, `SHA256SUMS` metadata are uploaded as 30-day Artifact; original PDF is deleted from ephemeral runner storage **even after failure**. No audio/CSV/RAR/FLAC/PCM, no publisher paper contents, no code/binary package or waveform. Original frozen Gym RAR identity 447127176 bytes SHA256 `8175dad412a752a34bdf2722f7e9b5ee671b62e67dfe5179f7a769d63912b2ea`, eight static/moving physical CH1/3/5/7 and S3R decoded PCM-MD5 remain unchanged; no redownload.

Existing canonical Source Vetting gets one path-scoped S5 job and suppresses redundant S1 original RAR and D1 original CSV transports. Existing fast docs/Verify gate exercises false synchronized-text, altered hardware clock claim, forged source position and sample-zero, unexpected source and duplicate JSON negative fixtures. The S5 workflow must fail on any missing preinstalled PDF tool or mismatched publisher bytes/claims. Review protected main Ruleset 21804005, exact-head required Verify `summary=success`, source-only Artifact and zero unresolved threads before expected-head protected squash. Fresh-main Verify, exact-SHA Release and second independent official paper source Artifact required before closing #716.

**Research only:** RealMAN CC BY-NC conservatively applied to AISHELL recordings; original NeurIPS paper has separate publisher rights and is not redistributed. No per-recording hardware HIL, PCR02/SSC305 runtime or physical mic validation, full D1 CSV positive admission, E001 shipping code or I025–I040 NS parameter reopening.
