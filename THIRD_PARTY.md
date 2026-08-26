# Third-party references and clean-room policy

The repository implementation is original code built around standard/published DSP concepts and public architecture observations. It does **not** vendor DSP source from the references below.

| Project | Design role | Source handling |
|---|---|---|
| jensen199105/aispeech-earbuds | embedded module/fixed-float/platform/memory organization | reference only; no source copied |
| athena-team/athena-signal | AEC/RES/DOA/MVDR/GSC/NS/VAD/AGC decomposition | reference only |
| xiph/speexdsp | published MDF/AUMDF concepts and low-footprint preprocessing practices | reference only; `src/ap_aec_mdf.c` is an independent implementation |
| WebRTC Audio Processing | production AEC3/NS/AGC/VAD/residual-echo behavior and integration lessons | reference only; no source vendored |
| xiph/rnnoise | compact neural denoising reference | reference only |
| Rikorose/DeepFilterNet | neural enhancement research/embedded tradeoffs | reference only |

The in-tree MDF/AUMDF-lite backend uses repository-specific 2 ms partitions, bounded half-spectrum state, normalized frequency-domain adaptation and cyclic time-domain support constraints. The frequency-dependent residual suppressor, clock-drift/sample-slip controller, runtime and public telemetry are likewise in-tree implementations, not ports of the projects above.

Standard algorithm names such as NLMS, MDF/AUMDF, Wiener filtering, STFT, delay-and-sum, normalized cross-correlation and sample-slip clock correction do not imply copied source.

Any future vendored/linked third-party backend must add its exact version/commit, license/notices, build isolation and target-board CPU/RSS measurements before becoming a default dependency.
