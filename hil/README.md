# HIL research measurement on a physical audio target

**Current authority: technical research only.** The active
[`hil-soak.yml`](../.github/workflows/hil-soak.yml) is an explicitly requested
`workflow_dispatch` experiment. It does **not** accept schedules,
`repository_dispatch` post-release events, release tags, shipping approval,
or product-certification prerequisites. Historical product-certification
procedures, labels and results remain in immutable Git/Actions history; they
do not authorize new research and must not be rewritten as new measurements.

## Physical runner and rights preflight

1. Use a real isolated board or controller with labels
   `self-hosted`, `linux`, `audio-target`. Never run unreviewed PR/fork
   source on the physical runner.
2. Install CMake, Python 3, ALSA tools, actual codec and route dependencies.
3. Configure the board-local manifest using `hil/board.schema.json`
   (copy `hil/board.example.json` to a private absolute board path).
   Bind board revision, SoC, RAM, kernel, codec, microphone/speaker versions,
   actual capture/playback path, optional power/thermal sensors, and
   reset/cleanup hooks.
4. Preflight locally:
   `python3 tools/hil_board.py preflight --board /etc/audio-pipeline/board.json --output /tmp/preflight.json`.
5. Set repository variable `HIL_ENABLED=true` **only** after the real
   isolated runner, route and sensors exist. If unavailable, a requested HIL
   experiment fails visibly (`HIL_REQUIRED_BUT_DISABLED`) rather than
   manufacturing PASS. Do not enable it for hosted/QEMU simulators.

## Manual research experiment

Dispatch the current `HIL Research Soak (manual, exact-source)` workflow
with **a verified 40-character source SHA**, an authorized board manifest
(optional only when the runner has a correctly configured private default),
and one of these experimental durations:

| Tier | Duration | Scientific purpose |
| --- | --- | --- |
| `accelerated-pr` | 600 s | bounded XRUN/fault-injection diagnostic |
| `research-1h` | 3600 s | short physical-route stability |
| `research-8h` | 28800 s | medium-duration runtime observation |
| `research-24h` | 86400 s | daily/thermal resource study |
| `research-72h` | 259200 s | optional long-duration research soak |

The 72-hour duration is **not mandatory** for source admission, ordinary
research CI, data preparation, acoustic development, or publication. It is
only a separately requested measurement. The runner builds the exact source,
verifies actual board/route identity, records ALSA health and optional
sensors, classifies infrastructure versus XRUN/hardware failures, and
uploads a sealed hash-bound summary. Missing hardware, duration or
sensor readings cannot become successful measured results.

This workflow retains the real HIL runtime, immutable SHA256 evidence,
non-silent failure and resource/latency/soak diagnostics. A hosted success
or branch status cannot be interpreted as physical SSC305 measurements.
Do not upload private speech, credentials or unrestricted board dumps.
