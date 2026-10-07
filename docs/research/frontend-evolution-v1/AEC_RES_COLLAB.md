# FE04 exact-timestamp AEC → time-domain RES collaboration diagnostic

This tranche isolates the existing time-domain residual echo suppressor after the unchanged MDF AEC.
Transport alignment is held at the exact synthetic timestamp authority already qualified in
FE04-SYNC-TIMESTAMP-AUTHORITY-V1. NS/frequency-domain RES, AGC and VAD are absent.

The candidate reproduces the current composed-pipeline ordering:
1. exact timestamp observation;
2. route_jump resets AEC only;
3. get synchronized reference;
4. Activity;
5. MDF AEC;
6. compute pre-RES residual energy;
7. time-domain RES in AP_QUALITY_FULL.

RES is intentionally **not reset** on route_jump because the current production pipeline does not
reset RES there.

The candidate output stores pre-RES AEC output, post-RES output and reference. The pre-RES AEC lane
and reference lane must be bitwise identical to the sealed exact-timestamp predecessor, making RES
the only changed audio operation.

Near-end preservation cannot be judged from SI-SDR alone because SI-SDR is scale-insensitive.
Evidence therefore includes frame-level RES gain, phase RMS attenuation, double-talk frames below
0.99/0.95 gain, and gain release behavior in addition to far-only residual metrics.

This is disclosed synthetic research evidence. A far-only improvement does not authorize promotion
if double-talk or near-end level preservation regresses. The fixed decision is
AEC_RES_COLLAB_DIAGNOSTIC_NO_PROMOTION.
