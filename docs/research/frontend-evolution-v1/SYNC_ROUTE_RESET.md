# FE04 SYNC route-jump AEC reset diagnostic

This tranche isolates one production semantic that FE04-SYNC-FAULTS-V1 intentionally omitted:
when public SYNC emits route_jump, the composed pipeline resets the AEC state before processing
the current capture frame. Activity and SYNC are not reset by that event.

The experiment consumes the sealed same-run FE04-SYNC-FAULTS-V1 artifact. It does not regenerate
speech, geometry or transport faults. The candidate uses the same public SYNC trajectory and the
same Activity/MDF AEC constants, adding only ap_module_aec_reset on route_jump.

Causal guards are fail-closed:
- the candidate CSV trace must be byte-identical to the predecessor public-SYNC trace;
- AEC reset count must equal route_jump event count;
- if the predecessor emitted no route_jump, candidate and control F32 output must be byte-identical.

This matters because the predecessor exposed both false route events (static/drift) and missed
true route events. Resetting AEC can therefore help after a true route change, harm a stable path,
or do nothing when the route event is missed. All outcomes are retained.

The data are disclosed diagnostics, RES/NS/AGC remain absent, and the fixed decision is
SYNC_ROUTE_RESET_DIAGNOSTIC_NO_PROMOTION. Nothing in this tranche changes the shipping API,
preset, version, E001 identity or DUT qualification.
