# Mandarin oracle-DT V1: baseline identity failure

Actual first execution ran once under outer timeout180. Outer Python exited1 at the CALL baseline control.csv exact-equality check. The CALL process itself exited0 with629frames and zero observer errors. Seven Float32 tap files matched historical originals byte-for-byte. Final S16 PCM also matched. However, control.csv differs in noise_rms_dbfs on8frames and metricsJSONL differs in6reported fields (5VAD probabilities and1ERLE). Therefore BASELINE_IDENTITY_FAILED is the only valid outcome. ASSISTANT baseline and both candidate profiles were not run:1 baseline DSP execution,0 candidate execution. No candidate quality result, threshold relaxation, selective rerun or advancement.

The frozen gate required all7taps/control/PCM/metrics identity before any candidate. Tiny diagnostic differences are still a failure of that gate; zero waveform difference does not waive it. Full command, start/exit/stdout/stderr receipts and original first failure remain. Compiler/source preparation completed; source-end checks at the bottom of run.py were not reached, so successful complete end-binding verification is not claimed.

## Read-only diagnosis, not causal proof

The retained library is the exact historical D1 observer static library. It has dynamically resolved log10f calls; NS noise_rms_dbfs, ERLE and VAD paths use logarithmic operations. Original build metadata identifies GCC13.3; current wrapper was linked with GCC14.2 and local glibc2.41. Local libm/libc/loader bindings are saved. Observed changes are consistent with host floating-library/build differences but the unique cause has not been experimentally isolated.

The source ZIP retains source, generated headers, the static library and compiler executable evidence, but not an immutable historical libm/libc/loader closure. The same floating runtime cannot currently be reconstructed from these assets alone. No installation, container substitution, recompilation of DSP, old-binary rerun or runtime bypass was performed after failure. Reconstructing a verified historical execution environment, or independently defining a new baseline contract, is separate work; it must not retroactively turn this failed experiment green.

## Scientific boundary

The proposed oracle changes only returned Activity DT after the real function, retaining internal states and far gate. Its mask comes from already inspected raw engineering near waveform support and may include background/noise and phase-misaligned boundaries. It is not human VAD, an online detector, an independent blind evaluation, or a guaranteed quality upper bound. None of its effect was measured because the baseline gate stopped execution. This result does not demonstrate that DT protection helps or harms Chinese quality.

No main/production source change, model/TTS/ASR/KWS call, paid compute, scheduler, Codex/Work or hardware execution occurred.
