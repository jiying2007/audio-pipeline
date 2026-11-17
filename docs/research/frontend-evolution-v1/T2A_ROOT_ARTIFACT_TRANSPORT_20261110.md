# T2A / T3S2B1A exact-run transport correction

Frozen before implementation: 2026-11-10. Base 5981de02a84d99beab1027eab2fe26aa54d3aa5e.

Observed Verify 42890141867 attempt 1: T2A job 130090946653 and T3S2B1A job 130090946381 passed their collectors and original verification, uploaded four-member artifacts, then failed immediate name-based download with Artifact not found. REST subsequently exposed both unexpired artifacts. This establishes the failing boundary, not the backend cause of initial invisibility.

T2A artifact 13796649881: 6133 bytes, SHA256 ee7986d5b09e04250cab4b248f211ce40644ab7d59a9879cb4a0ef311b471732.
T3S2B1A artifact 13797813111: 6711 bytes, SHA256 945f950ab6f816a962a1e3f3fec729cc62b6b13385362ee239b093077a35f93e.
Original run/jobs/artifacts stay unchanged. No blind rerun, overwrite or deletion.

Hypothesis: using the already qualified T3S1 transport path for these two observed failures will bind the pinned REST downloader to the exact uploaded artifact after bounded visibility witnessing. Per-attempt names avoid future same-run upload conflicts without replacing old evidence.

Scope: only these two workflow transports, exact name admission in the existing visibility helper, offline identity/refusal tests, and this failure record. No new downloader, dependency, scientific collector/readback change, DSP, threshold or timeout change.

Acceptance: both stages keep their original collector, four-member source/hash/scientific readback, timeout and 30-day retention. New names must match exact run and attempt; preserve strict ID/name/repository/head/execution-source/timestamp/size/digest checks, no redirects, eight total metadata requests, two-second bounded pauses, immediate hard-error rejection. Tests include wrong attempts, prior evidence coexistence, wrong ID/name/source, exhausted budget and workflow wiring. Existing A1/B1/T3S1 behavior remains. Full exact-head Verify and independent review precede protected squash merge; exact fresh main must independently pass. Old main failure is not relabeled.

Data role: synthetic API metadata tests plus original public GitHub job evidence only. No new acoustic experiment, private data, physical qualification or quality promotion. If the unchanged bound still fails, preserve the new failure and diagnose; do not increase limits to obtain PASS.
