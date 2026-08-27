# Third-party references and clean-room policy

The repository implementation is original code built around standard/published DSP concepts and public architecture observations. It does **not** vendor DSP source from the references below.

| Project | Design role | Source handling |
|---|---|---|
| jensen199105/aispeech-earbuds | embedded module/fixed-float/platform/memory organization | reference only; no source, tables, models or resources copied |
| athena-team/athena-signal | AEC/RES/DOA/MVDR/GSC/NS/VAD/AGC decomposition and published MCRA-style NS practice | Apache-2.0 reference; no source copied |
| xiph/speexdsp | published MDF/AUMDF concepts and low-footprint preprocessing practices | reference only; `src/aec/ap_aec_mdf.c` is an independent implementation |
| WebRTC Audio Processing | production AEC3/NS/AGC/VAD/residual-echo behavior and integration lessons | reference only; no source vendored |
| xiph/rnnoise | compact neural denoising reference | reference only |
| Rikorose/DeepFilterNet | neural enhancement research/embedded tradeoffs | reference only |

The optional MCRA-lite noise estimator is a clean-room implementation of the public minimum-controlled recursive-averaging concept. Its constants, state layout and update equations were selected for this repository's 10 ms/8-16 kHz low-compute profile rather than copied from Athena Signal. EMA remains the default production estimator until MCRA demonstrates a useful acoustic benefit on the shipping corpus together with acceptable target-board CPU/thermal headroom.

The static 8/16 kHz sine half-window tables are generated from this repository's existing analysis/synthesis formula and are not copied from AISpeech Earbuds. AISpeech Earbuds is used only as an architectural reference for explicit embedded modules, memory/resource separation and compile-time product composition; because this repository does not rely on a license grant from that project, no source, coefficient table, model or binary resource is incorporated.

The in-tree MDF/AUMDF-lite backend uses repository-specific 2 ms partitions, bounded half-spectrum state, normalized frequency-domain adaptation and cyclic time-domain support constraints. The frequency-dependent residual suppressor, clock-drift/sample-slip controller, Linux runtime and public telemetry are likewise in-tree implementations, not ports of the projects above.

Standard algorithm names such as NLMS, MDF/AUMDF, MCRA, Wiener filtering, STFT, delay-and-sum, normalized cross-correlation and sample-slip clock correction do not imply copied source.

Any future vendored/linked third-party backend must add its exact version/commit, license/notices, build isolation and target-board CPU/RSS measurements before becoming a default dependency.
