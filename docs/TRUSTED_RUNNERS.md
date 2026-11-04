# Trusted scientific runner readiness

Current authority: **technical research only**. Use [research execution boundaries](RESEARCH_ONLY_EXECUTION.md) and the [physical HIL guide](../hil/README.md). The manually dispatched `Research Runner Readiness` workflow verifies **infrastructure prerequisites**, not product certification, acoustic performance or real-world data permission.

## Source and role boundaries

Each check binds an explicitly chosen 40-character source SHA. The checkout must resolve that exact commit; a branch name, the newest `main`, a historical Release tag or an earlier green run is never an interchangeable identity. Recheck readiness when the target source, runner toolchain, board/route, cache, data terms or sensors change.

| Scientific role | Required self-hosted labels | What readiness checks | What it cannot prove |
| --- | --- | --- | --- |
| Public-data validation | `self-hosted, linux, audio-validation` | Linux tools and licensed/public cache, dataset seal or Extended Real catalog | independent real speech or physical hardware performance |
| Cross-build research | `self-hosted, linux, audio-builder` | exact target C compiler, sysroot and toolchain root | any signed/shipping SDK or actual DUT execution |
| Physical board research | `self-hosted, linux, audio-target` | board manifest, ALSA/codec route and optional sensor/source inputs | measured CPU, acoustic or long-soak PASS before an actual experiment |

The former `certification-archive` role and its publication/immutable lifecycle command are **retired** from live readiness. Historic records remain in Git/Actions history only. Nothing in this workflow can approve a sale, a GitHub Release, a shipping SKU or a product certificate.

## Verify the offline preflight

```sh
python3 tools/runner_preflight.py --self-test
```

Typical calls use real absolute local paths, never private files committed to the public repository:

```sh
# Public corpus: lawful source rights and exact seal must be checked separately
python3 tools/runner_preflight.py --role audio-validation \
  --source-revision "$SOURCE_SHA" --data-root /srv/audio-validation \
  --seal /srv/audio-validation/datasets.seal.json \
  --writable-path /srv/audio-validation --output /tmp/research-validation-readiness.json

# Experimental AArch32 cross-build profile; no shipping artifact is implied
python3 tools/runner_preflight.py --role audio-builder \
  --source-revision "$SOURCE_SHA" \
  --target-cc /opt/toolchain/bin/arm-linux-gnueabihf-gcc \
  --target-sysroot /opt/toolchain/sysroot \
  --target-toolchain-root /opt/toolchain \
  --writable-path /tmp --output /tmp/research-builder-readiness.json

# Actual isolated device: board identity and route must be independently reviewed
python3 tools/hil_board.py preflight \
  --board /etc/audio-pipeline/board.json --output /tmp/hil-preflight.json
python3 tools/runner_preflight.py --role audio-target \
  --source-revision "$SOURCE_SHA" \
  --board-manifest /etc/audio-pipeline/board.json \
  --writable-path /tmp --output /tmp/research-target-readiness.json
```

`READY` is only infrastructure readiness. `NOT_READY`, missing datasets or missing device sensors must remain visible; do not convert them into sound quality or SSC305 measurements. For actual physical experiments `hil-soak.yml` is **manual only**, uses an exact SHA plus an isolated real `audio-target` runner and requires `HIL_ENABLED=true`. Optional 600 s, 1 h, 8 h, 24 h and 72 h research durations are not mandatory certification tiers. Unavailable hardware must be `NOT_RUN`/`BLOCKED`, not PASS. Extended Real has a separate rights-bounded `EXTENDED_REAL_ENABLED` gate.

## Invalidate stale evidence

Repeat the exact-source preflight if the SHA, toolchain, kernel/governor, ALSA route, microphone/speaker geometry, board revision, dataset seal, input rights, codec, thermal/power sensors, writable paths or external mount changes. Treat all old `certification-archive`/shipping-builder receipts and release-tag instructions in earlier Git history as **historical only**, not current scientific authority.
