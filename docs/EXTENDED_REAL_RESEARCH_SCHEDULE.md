# Extended Real research scheduling boundary

The active `.github/workflows/extended-real-automation.yml` has only
`schedule` and `workflow_dispatch` triggers. The old
`extended-real-post-release` repository-dispatch listener and tag/SHA
publication authority were removed. Each run binds the actual current
`main` commit SHA and forwards it to the canonical
`validation-extended-real.yml` research measurement workflow.

The scheduled dataset selection remains **exactly the old reviewed,
CC-BY-4.0-only subset**, whose historical catalog key is
`commercial-plus`. This is a *dataset license filter / compatibility
identifier*, **not** commercial readiness, shipping certification or a
publication requirement. Renaming that key can occur only after updating
all affected source-lock, evaluator and policy contracts together; silently
replacing it with the much broader `research` profile would admit
conditional and noncommercial datasets to unattended execution.

The full `research` dataset profile retains its manual, explicit
source-rights/review path. In particular, a conditional or NC dataset
is not unrestricted merely because the project is research-only.

`EXTENDED_REAL_ENABLED=true` must reflect an actually available controlled
runner and correctly materialized source cache. A disabled or missing runner
results in explicit failure, not a fabricated success, and real-audio,
DUT, provenance, acoustics and resource evidence remains independent and
hash-bound. The scheduled workflow never creates a GitHub Release or
certifies product shipping.

No historical measured result, license snapshot, artifact or repository
release has been altered by this trigger migration.
