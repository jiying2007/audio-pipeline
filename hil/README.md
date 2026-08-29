# HIL board farm

`hil/` defines the hardware-in-the-loop contract used by `.github/workflows/hil-soak.yml`.

## Runner onboarding

1. Register each trusted product board or board controller as a GitHub self-hosted runner with labels `self-hosted`, `linux`, `audio-target`.
2. Install CMake, Python 3, ALSA userspace tools and the engineering dependencies required to exercise the real audio route. Formal shipping certification is built separately on the trusted `audio-builder`; the DUT is not the formal build controller.
3. Copy `hil/board.example.json` to `/etc/audio-pipeline/board.json` and replace every placeholder with stable hardware identity and the real default product route.
4. Configure `thermal_sensor` and, when available, `power_sensor`. Product certification must not invent missing thermal/power measurements.
5. Keep reset/cleanup implementation in board-local hooks (`power_cycle_hook`, `cleanup_hook`), not in repository code.
6. Run `python3 tools/hil_board.py preflight --board /etc/audio-pipeline/board.json --output /tmp/preflight.json` locally before enabling automation.
7. Set repository variable `HIL_ENABLED=true` only after the runner and real route are healthy. Scheduled/post-release HIL is fail-visible: if policy requires it while `HIL_ENABLED!=true`, the availability gate fails rather than silently skipping or manufacturing PASS.

## Scheduling and revision binding

- trusted PR candidate: manually dispatch `accelerated-pr` against the reviewed SHA;
- daily schedule: `nightly-1h`, pinned to the schedule event SHA;
- weekly schedule: `weekly-24h`, pinned to the schedule event SHA;
- newly published immutable Release: Release sends explicit `hil-post-release` `repository_dispatch`; `release-8h` runs against the exact immutable release SHA;
- release/SKU engineering soak: manually dispatch `certification-72h` against an explicitly reviewed ref.

An already-existing Release does not emit a new post-release HIL event, so repeated main pushes cannot create false 8 h release-HIL history.

The repository is public. Never configure HIL to automatically execute untrusted fork pull-request code on self-hosted hardware.

## Board metadata

The local manifest deliberately records hardware identity separately from Git history. At minimum it identifies board/revision, SoC, RAM, kernel family, codec, mic-board revision and speaker revision. Optional route metadata enables scheduled jobs to use the runner's own capture/playback devices without repository-specific board names.

Preflight/cleanup and route evidence are uploaded together and sealed with `SHA256SUMS`. A lab setup problem is classified as `INFRA_FAILURE`; XRUN or route/runtime failures remain product/HIL failures.

## Formal product certification boundary

HIL tiers provide operational and release-history evidence, but formal `product-certified` schema-v4 evidence uses the separate trusted topology:

`audio-builder -> audio-target -> certification-archive`

The shipping binary is built with the exact declared compiler/sysroot/toolchain/CFLAGS on `audio-builder`, deployed unchanged to `audio-target`, and archived with an immutable `product-lifecycle` receipt. Build/deployed/executed binary SHA-256 values must match. The shipping-approved Cortex-A32 LOW policy requires a minimum 72 h soak; 1 h / 8 h / 24 h HIL tiers do not replace that certification.

See `docs/TESTING.md`, `docs/TESTING.zh-CN.md`, `docs/PRODUCT_ASSURANCE.md` and `certification/README.md` for the complete policy.
