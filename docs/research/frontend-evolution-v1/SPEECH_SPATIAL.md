# FE03 recorded-speech spatial diagnostics / 真实语音固定空间对照

Preregistered in #657 comment 5990919882, before acquisition and scoring.
Base: `c4280f111e9dd56233e3cf610704da4752eb20b9`. B0/v2.3.55 and E001 are unchanged.
Machine scope: `.github/research/frontend-evolution-v1/speech-spatial-v1.json`.
This is a fixed diagnostic, not a parameter search or shipping promotion.

## What is real and what is simulated

The utterances are actual LibriSpeech dev-clean recordings, not tones or synthesized
speech. Their provenance is OpenSLR SLR12 (https://www.openslr.org/12/), prepared by
Vassil Panayotov, Daniel Povey, Guoguo Chen and Sanjeev Khudanpur from LibriVox.
The corpus is CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Retain the
original corpus LICENSE.TXT, README.TXT, SPEAKERS.TXT and derivative attribution.
No audio, decoder or externally copyrighted source is vendored into this Git tree.

The microphones and sound field are **simulated free-field plane waves**. No room
response, enclosure, motor, automatic DOA, AEC or physical array was measured.
Exact target directions are supplied as an oracle; this does not quantify a DOA
estimator or the previous confidence controller. The fixed four-microphone C
research core is executed unchanged, not promoted into the installed 2.x SDK.

## Source selection and admission

Acquire only the official `dev-clean.tar.gz`; check published MD5
`42e2234ba48799c1f50f24a7926300a1`, size bounds and a separately retained SHA256.
Select the eight lowest numeric speaker IDs and their first four utterances ordered
by numeric chapter and utterance. Validate native FLAC mono/16-bit/16kHz metadata,
losslessly decode, concatenate, and take the first four seconds. Do not select by
energy, score, gender, transcription or outcome. Insufficient duration fails;
there is no reselection or padding. Original FLAC members and decoded-window hashes
are retained. Decoder version/ELF identity are observed per run, not silently
assumed from the hosted image; the admitted audio bytes are invariant.

Before any BF scoring, an actual source-only artifact is independently reviewed.
`speech-admission-v1.json` binds its archive identity, complete selected-file hashes,
original-to-window provenance and speaker roles via a canonical SHA256 digest.
Decoder logs may change with the host; the decoded data/selection may not. Signed
Ubuntu repository FFmpeg packages are explicitly installed only on the research
host, never in the SDK. A missing decoder is an infrastructure failure, not a VAD,
BF or speech-quality result. Network inputs are fetched without project credentials.

Adjacent selected speakers form target/interferer pairs. Pairs 0/1 are development
diagnostics and pairs 2/3 speaker-disjoint confirmation diagnostics. All four arms
are frozen before either set runs; there is no mode/threshold selection. This is
not a blind benchmark, an independent-room corpus, a confidence interval based on
hundreds of independent speakers, or Chinese KWS qualification. Viewed confirmation
results cannot become a new blind set for later tuning.

## Fixed matrix and signal reference

Three 70mm-aperture geometries: dual line, uniform linear four and circular four.
All use physical microphone 0 at (-35mm,0,0) as time/reference origin, not a per-case
best channel. This is **same aperture**, not same spacing. The known target and
interferer azimuths are (0,90), (60,150) and (90,90) degrees from +X. The last is a
co-located negative control. Four pairs x three geometries x three scenes gives
36 mixtures. Four arms give 144 mixed-speech outputs, not 144 independent subjects.

Arms are reference mic, arithmetic mean, known-target linear delay-and-sum and
known-target cubic Lagrange delay-and-sum. Mean is an explicit research reference,
not a claim to have executed the production B0 BF or its full frontend.

The first-party offline renderer uses 63 Hann-windowed sinc taps with double
arithmetic and zero extension. It is noncausal stimulus preparation, not candidate
lookahead. It differs from the two/four-tap C BF under test. For each pair, source
RMS values rT/rI and normalized peak values pT/pI give a common headroom
h=0.25/(pT+pI); target gain=h/rT and interference gain=h/rI. Gains are identical
across geometries/arms for that pair and are recorded. There is no post-BF gain
normalization or clipping. Unexpected input clipping fails instead of silently
changing the data. Co-located sources cannot be spatially separated; spectral
coloring may still change scalar energy metrics and is not a spatial win.

Target and interference renderings are quantized separately to S16, then summed
exactly with a no-clipping check. Each arm separately processes target, interference
and mixture so the linear decomposition is testable. Float output is not converted
to S16 before measurement. The numerical decomposition bound is 2e-6 absolute,
not an acoustic quality threshold. Previous bitwise/acoustic gates are untouched.

Metric spans exclude 1,600 samples at each boundary and use 60,795 target samples
for every arm. Reference/mean have zero algorithmic delay; both C BF modes have
five declared samples. Only this fixed delay is compensated. The raw mean's
geometric phase response is NOT aligned per case to maximize SI-SDR. Therefore
SI-SDR is accompanied by component SIR gain, interference attenuation, target
transfer gain/error and output range. Neither total-energy attenuation nor an
aggregate SI-SDR alone proves isolated BF improvement.

`validation/tools/run_validation_engine.py:si_sdr_span` is the unchanged canonical
speech metric. Component-energy transfer is a first-party diagnostic calculation,
not a new product evaluator. All losses and co-located cases remain visible. Report
by pair/geometry/scene; summaries have only two pairs per data role.

## Execution and evidence

```sh
python3 tests/validation/frontend_evolution/test_speech_spatial.py
python3 tests/validation/frontend_evolution/speech_source.py --output /tmp/fe-source
python3 tests/validation/frontend_evolution/speech_spatial.py \
  --source /tmp/fe-source --output /tmp/fe-spatial --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/speech_spatial.py \
  --output /tmp/fe-spatial --execution-source "$(git rev-parse HEAD)" --verify
python3 tests/validation/frontend_evolution/test_speech_spatial.py --evidence /tmp/fe-spatial
```

Evidence contains original admitted data/notices, source and experiment snapshots,
compiler commands/identity, native renderer and C BF binaries, geometry/gains,
all target/interferer/mixture inputs and outputs, repeated C BF outputs, exact case
counts, recomputable canonical/component metrics and checksums. Renderer and BF
oracles additionally check a predeclared finite sample grid; this is NOT a full
independent sample-by-sample proof. Re-sealed negative tests cannot authorize a
fake score, omitted arm/case, role change, real-array claim or shipping promotion.

The existing Quality/Verify includes a native speech job; no new workflow, public
API or runtime is created. Current AArch32 analytic/transition tests remain in
the existing array job; this speech matrix is native-only unless a future explicit
Arm execution is retained. No host time is labelled SSC305 CPU/p99 or physical soak.
Actions artifacts have finite retention; retain original ZIPs with the reviewed
checkpoint. Data retrieval/decoding failure is never reported as acoustic failure.

## 中文边界与下一步

本轮用真实英文朗读语音检验已实现的双/四麦 C 核心，不再用解析信号代替音质
对照。但空间传播是明确的自由场合成，不是真实房间、机器人外壳或阵列采集。
固定参考、固定方向、固定采样窗、固定四种处理方法，保留每个说话人对和负例。
“降低了干扰”和“没有损伤目标语音”分别报告，不自动判定四麦或三阶插值获胜。

结果只支持这一小规模已知方向诊断，不支持 DOA、语音打断、AEC、中文 KWS、
真实 CPU 或 C4 产品认证。随后应由具体失真/噪声残留选择固定 FIR、多波束或
BF/AEC 联合研究；不得用本轮已查看的确认说话人反复调参，再宣称独立确认。
