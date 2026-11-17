# T3-S1 transport failures retained

Verify 42847765892, exact head 44b2e22597a45171fdf83d657856958ff1af4720, execution source d3f94cf50f1f6dd53258e7cb2274931385ad7dd5. Full decoded job logs retain GitHub credential masking. The first failed mandatory readback was followed by one failed-jobs-only retry. Attempt 2 exposed the run-only naming collision; no further retry or artifact deletion occurred.

- Attempt 1: job 129942358773, artifact 13778683373, ZIP SHA256 7923195e8927dc41fd80dede475a8393c224d297996db994a50976685ebbf03a.
- Attempt 2: job 129964573573, artifact 13782800825, ZIP SHA256 eaaf68699212fd35ee47c542163918684da04388dcef33cc95475270722f67d2.

Both ZIPs were independently downloaded through the public GitHub connector and the exact archive hashes and all manifest member hashes checked. Both contained SHA256SUMS, collect.log, receipt.json, verify.log. Both receipts identify the execution source above and actual_compiled_targets_complete=true, decision FE09_T3S1_TWO_SLOT_SOURCE_BF_HANDOFF_RESEARCH_ONLY. Independent retrieval does not turn either failed mandatory CI job into a pass. Original artifacts remain subject to their existing 30-day GitHub retention; this directory preserves complete failure logs and identities, not the ZIP payloads.

The follow-up transport change isolates new T3-S1 names by run attempt and keeps strict name/ID uniqueness, source, timestamp, bounded requests and downstream pinned download/member verification. It does not fix or establish the cause of the first-attempt downloader visibility discrepancy, which must still fail closed if repeated.
