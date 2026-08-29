# HIL board farm

`hil/` defines the hardware-in-the-loop contract used by `.github/workflows/hil-soak.yml`.

## Runner onboarding

1. Register each trusted product board or board controller as a GitHub self-hosted runner with labels `self-hosted`, `linux`, `audio-target`.
2. Install the product shipping compiler/toolchain dependencies, CMake, Python 3 and ALSA userspace tools required to build and exercise the real audio route.
3. Copy `hil/board.example.json` to `/etc/audio-pipeline/board.json` and replace every placeholder with stable hardware identity and the real default product route.
4. Configure `thermal_sensor` and, when available, `power_sensor`. Product certification must not invent missing thermal/power measurements.
5. Keep reset/cleanup implementation in board-local hooks (`power_cycle_hook`, `cleanup_hook`), not in repository code.
6. Run `python3 tools/hil_board.py preflight --board /etc/audio-pipeline/board.json --output /tmp/preflight.json` locally before enabling automation.
7. Set repository variable `HIL_ENABLED=true` only after the runner is healthy. Until then scheduled/post-release HIL jobs are intentionally skipped.

## Scheduling

- trusted PR candidate: manually dispatch `accelerated-pr` against the reviewed SHA;
- daily schedule: `nightly-1h` when `HIL_ENABLED=true`;
- weekly schedule: `weekly-24h` when `HIL_ENABLED=true`;
- successful Release workflow: `release-8h` when `HIL_ENABLED=true`;
- release/SKU qualification: manually dispatch `certification-72h`.

The repository is public. Never configure HIL to automatically execute untrusted fork pull-request code on self-hosted hardware.

## Board metadata

The local manifest deliberately records hardware identity separately from Git history. At minimum it identifies board/revision, SoC, RAM, kernel family, codec, mic-board revision and speaker revision. Optional route metadata enables scheduled jobs to use the runner's own capture/playback devices without repository-specific board names.

Preflight/cleanup and route evidence are uploaded together and sealed with `SHA256SUMS`. A lab setup problem is classified as `INFRA_FAILURE`; XRUN or route/runtime failures remain product/HIL failures.

See `docs/TESTING.md` or `docs/TESTING.zh-CN.md` for the complete policy.
