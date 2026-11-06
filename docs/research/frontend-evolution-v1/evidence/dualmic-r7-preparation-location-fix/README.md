# R7 preparation evidence location correction

The first PR #918 Verify run **failed** in impact before docs/source routing.
`failure-receipt.json` binds the actual PR source head, base, merge checkout,
run/job and complete decoded job log. `impact-original.log.b64` losslessly
transports the original UTF-8 bytes, including BOM/ANSI and line endings:

```sh
base64 --decode impact-original.log.b64 > impact-original.log
sha256sum impact-original.log
```

The expected decoded SHA256 is
`74d068964914804b60fe22e61e233ec210a972c0584ecbe377ac50ac93272194`
and its size is 51,051 bytes. This is the connector-decoded log, not a claim
about GitHub's original archive compression bytes.

Four original preparation records move from `validation/research/evidence/`
to the existing `docs/research/frontend-evolution-v1/evidence/` research tree.
Every original file, including its manifest, retains its bytes and hash.
Only AUTHOR_VALIDATION's relative link changes. The existing protected-base
classifier and SemVer rules remain unchanged; preparation retains 2.3.61.

The source preparation originally completed in 800.565 seconds. Its separate
wording clarification took approximately 152 seconds against 120 seconds
and did **not** pass that budget. Neither result is rewritten by this move.
This stage does not build or execute DSP and cannot establish CI success;
the new exact PR head still needs its actual Verify and independent review.
