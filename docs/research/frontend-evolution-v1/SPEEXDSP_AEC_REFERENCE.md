# Pristine SpeexDSP AEC reference / 原版 SpeexDSP AEC 对照

Experiment: `FE04-SPEEXDSP-AEC-REFERENCE-V1`.
Base: `8b75b95a0a3496e5df2233c223476d20eff56818`.
Preregistration: #657 comment `6009185210`.

The source-preflight run `37413140795` verified 16 exact upstream Git blobs at
SpeexDSP commit `7a158783df74efe7c2d1c6ee8363c1e695c71226` / tree
`234a15ae4271403465237879b8670601af95bf0f`. Its source artifact is
`11389769210`, GitHub/upload-reported SHA256
`bb4d39ed346e0fccc87ee0bc05e064837f94b4f2d37aa071b7d0084ec1af6bd2`.
This digest is not described as an independent local rehash.

Execution admission is limited to pristine `mdf.c + fftwrap.c + smallft.c` and
required headers/notices. Upstream configure/autotools files are review inputs only.
No Speex preprocessor, residual suppressor, NS, AGC, resampler, jitter code, model,
weight or dataset is admitted. The adapter uses `speex_echo_cancellation` directly;
it never uses the playback/capture API with its two-frame playback buffer.

## Fixed comparison

Both arms consume the exact post-BF microphone/render observation retained by #667, then one deterministic
S16 boundary. BF near target and known BF echo are quantized by the same saturating
nearest/ties-away-from-zero rule and retained. The current control dequantizes that S16
to the unchanged public Activity + MDF AEC. Speex receives the same S16 directly and
uses its own upstream continuous-learning/two-path behavior; Activity is monitor-only
for that arm and is explicitly not used to gate Speex.

Only six already disclosed development cases run:
pair0/pair1 × ULA4-70 × FIR33 × none/steer/path. There is no tail, geometry, bank,
threshold or level sweep. Requested Speex filter length is 1024 samples; runtime
readback must report 160-sample frames, 16 kHz and its actually rounded impulse-response
size. The direct API has no playback-buffer delay; output is available after the full
10 ms frame. This does not claim zero physical/system latency.

Score actual far-only output residual and complete mixed output relative to the quantized
BF near target. Do not subtract a separately adapted echo shadow in double talk. Relative
recovery is reported with nulls and absolute final residual; a weaker baseline must not
turn an easier relative criterion into a promotion claim.

Native, ASan/UBSan and AArch32/QEMU execute finite functional controls. Host timing,
binary size and source structure are engineering observations only, not SSC305 CPU/p99/
RSS/thermal evidence. The fixed decision is
`SPEEXDSP_AEC_REFERENCE_DIAGNOSTIC_NO_PROMOTION` regardless of score.

中文边界：本批是“完整 AEC 实现之间的参考对照”，不能把差异全部解释成 DTD。
即使 SpeexDSP 在已披露开发场景更好，也不能直接替换产品默认；后续机制迁移、
SYNC/RES 联合或产品选择都需要新的预登记和独立确认。
