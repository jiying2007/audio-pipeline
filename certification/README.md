# Target Certification Records

Repository CI proves build, functional, memory-safety and hosted regression contracts. It does not certify Cortex-A7, Cortex-A32 or any other shipping SoC performance.

Create one record per shipping SKU using `record.schema.json`. Attach raw benchmark/eval logs outside the source repository when product confidentiality requires it, but keep the record's immutable hashes and build fingerprint.

A product-certified record must include:

- exact audio-pipeline commit/tag and `ap_build_info()` fingerprint;
- SoC/revision/core count, compiler/ABI/SIMD and fast-math state;
- kernel, governor/DVFS, cpuset/IRQ affinity and codec/ALSA geometry;
- product resource class, compiled modules, AEC/NS/resampler backends and geometry caps;
- active/idle CPU, p95/p99 DSP time, RSS, cache/context-switch data;
- XRUN/input-full/output-drop/overrun counts;
- far-only, near-only, double-talk, path-change, clock-drift and noise corpus metrics;
- thermal/power measurements;
- 8-hour soak outcome;
- artifact/corpus revision hashes.

A missing board result must be recorded as `pending`; never substitute hosted x86 or cross-build results.

## Product policy gate

`product-certified` now requires an explicit SKU policy and thermal/power evidence. Validate with:

```bash
python3 certification/validate_record.py record.json --policy product-policy.json
```

The repository example policy is not a shipping requirement; product owners must define and version their own thresholds.
