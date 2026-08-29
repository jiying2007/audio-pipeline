# Certification policies

A `product-certified` v4 record must use a checked-in policy whose `shipping_approved` field is `true` and whose `sku` exactly matches the certification request. Example or `not-for-shipping` policies are rejected by both the collector and validator.

`cortex-a32-low-shipping.json` is the repository's formal LOW Cortex-A32 shipping policy baseline. Its existence is **not** a certification result: the SKU becomes product-certified only after the exact shipping build is deployed to real hardware, the real corpus and sensor gates pass, the required 72-hour route soak passes, the evidence bundle is attested, and the lifecycle archive returns a valid immutable receipt.

Threshold changes are product acceptance changes. Update the policy in a reviewed pull request; never tune a policy inside a certification run to make a failing result pass. The policy bytes are SHA-256-bound into every certification record.
