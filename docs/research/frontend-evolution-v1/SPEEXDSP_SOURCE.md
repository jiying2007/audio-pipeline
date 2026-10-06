# SpeexDSP AEC source preflight / SpeexDSP AEC 源码预检

This stage pins pristine SpeexDSP to commit `7a158783df74efe7c2d1c6ee8363c1e695c71226`
and tree `234a15ae4271403465237879b8670601af95bf0f`.

The preflight is intentionally **not execution admission**. CI checks the exact commit/tree and
Git blob identities, copies only the locked minimal AEC files/notices, generates a transparent
stdint type header from the upstream template, hashes the materialized bytes, and runs one
tamper-negative. No SpeexDSP source is compiled or executed in this first step.

Scope is limited to the floating-point MDF echo canceller plus its SmallFT wrapper:
`mdf.c`, `fftwrap.c/.h`, `smallft.c/.h`, required headers, `COPYING`, `AUTHORS`,
and upstream build declarations used only to review version/dependency intent. Upstream
preprocess/RES/NS/AGC/resampler/jitter/buffer code and build scripts are not execution inputs.

The license review records the BSD-style redistribution conditions from upstream COPYING and
per-file notices. No model, weight or dataset is involved. Research evidence must retain notices.

Only after the source-preflight artifact is inspected may a separate admission receipt authorize
the explicit source list for an offline AEC reference. The later comparison is preregistered in
#657 comment 6009185210 and cannot promote a shipping default from disclosed development data.

中文边界：本步骤只证明“拿到的是哪一份源码字节以及许可范围”，不证明能编译、
算法有效、性能达标或可进入产品。后续适配必须继续区分源码准入、算法执行、
效果比较、产品 SDK 和 E001 物理资格。
