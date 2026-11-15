# Proposed fixed-oracle-input NS/RES DT-control isolation

Status: PLAN_ONLY_AWAITING_AUTHORIZATION_AND_INDEPENDENT_IMPLEMENTATION_REVIEW. No new compile, module, pipeline or historical-runtime run. Base main 6ff1ab8990e0a4c8be62802f48c20a06d611a11b; only open PRs #925 ALSA test and #714 dependency update at readback.

## Question and non-duplication

On saved #954 oracle NS residual/echo inputs, how much does replacing only DT control with the original baseline DT sequence change NS output? #955 isolated AGC allow on fixed NS output, not this module. D40 uniformly disabled enable_frequency_res; this proposal leaves enable_frequency_res unchanged and substitutes DT. D41–49 changed innovation/noise/amplitude mappings, not this fixed-oracle-input intervention.

DT affects both frequency-RES activation and inactive residual_gain_bins release alpha in unchanged ap_ns.c. Both paths remain; do not name this a pure frequency-enable ablation. Ordinary NS/FFT/tracker behavior is unchanged code but its input is fixed at oracle values. Result is a conditional NS/RES control effect, not additive decomposition of the total DT effect, isolated speech quality or production advice.

## Frozen data and exact admission

Two profiles CALL and ASSISTANT; 629 sequential frames, 160 samples each, original ap_ns_init once per arm. Saved oracle ns_input and echo Float32 remain fixed. Original ns_mode, ns_floor, frequency_enabled and far controls remain fixed; initial oracle DT is used for both admission runs. Candidate changes DT alone to saved original baseline DT. No per-frame state injection/reset, new audio, fitted lag, tail flush or tuning.

Use original source-identified historical libaudio_pipeline.a and unchanged original headers/build definitions, not a new DSP implementation. A minimal new harness must be independently reviewed and source/ELF frozen before execution. Both profiles must exactly match every historical oracle NS Float32 output sample AND each exported frequency_active, residual_gain, noise_rms_dbfs and speech_probability field (decimal float fields restored to Float32) for all 629 frames, before either candidate. Also assert original control/config sequences unchanged. There is no tolerance. Any mismatch stops immediately with BASELINE_IDENTITY_FAILED, all receipts/partials retained and zero candidates. No retry/alternate compiler/math/omitted field permitted.

Historical full FFT/OLA/tracker/bin state was not saved. Matching output and exported statistics cannot be called a full-internal-state replay proof. Initialization/recurrence must be continuous unchanged code.

## Runtime barrier and proposed bounded authorization

Current native runtime previously differed in CALL noise_rms_dbfs at frame14 (-78.2526474 versus -78.2526398). Read-only evidence shows the new oracle and historical baseline first100frames have byte-identical NS inputs, echo and output, with the same frame14 target. Do not omit the field or repeatedly run the known-risk native admission to manufacture progress. This plan does not grant permission to use the private historical runtime.

If separately approved, propose exactly four isolated NS-module processes maximum using the already verified Ubuntu 2.39-0ubuntu8.9 private loader/libc/libm: two sequential admission processes then, only if both all-field gates pass, one candidate process per profile. No whole pipeline, new full-pipeline oracle-DT, additional benchmark process, software download/install or system change. If first baseline fails only one module run; if second fails only two; if both pass maximum four. The previous four full-pipeline authorization is exhausted and is not reused.

Before first launch: reject all LD_* and GLIBC_TUNABLES; check original library/source/input/output/config/runtime hashes; verify ELF dynamic dependencies offline, then private-loader --list with --inhibit-cache and private --library-path. Only exact verified libc/libm/loader mappings plus one complete VDSO line are accepted. One dependency-list process per ELF (same harness for all arms), not a DSP invocation. No network, credentials, installation scripts, privileged write or paid resource. Check ELF/input/runtime identities before and after every invocation; fail closed.

Budget proposal: one harness compile <=30s; one loader-list <=10s; each of maximum4 module invocations <=15s; independent analysis <=30s; outer whole operation <=150s. No favorable retry or search. Any safety/identity/timeout failure stops and preserves partials.

## Measurements and restrictions

Reuse unchanged previous math.fsum/null formulas and all13 fixed windows; NS output offset160, common physical[0,100480), output[160,100640). Retain every52 group (13 x 2profiles x 2arms), positive/negative/null. Actual endpoint is Float32 NS, not final S16, ASR/CER/MOS. Preserve raw-near engineering-domain and stage-transform caveats.

Record actual per-process elapsed and one CLOCK_THREAD_CPUTIME_ID complete629frame processing duration per arm, excluding input/file validation. There is only one observation per arm, not a benchmark distribution or speedup claim. No acoustic promotion threshold or production changes; decision CONDITIONAL_NS_RES_DIAGNOSTIC_NO_PROMOTION regardless of favorable score. Publish failure equally.

Before execution: freeze code and all dependencies; independent safety/scientific pre-review required after authorization. After execution: independent read-only output/metric/identity audit before any protected docs-only PR. Do not rerun DSP for audit.
