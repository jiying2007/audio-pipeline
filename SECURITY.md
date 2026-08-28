# Security Policy

## Supported versions

Security fixes are applied to the current `main` branch and the latest tagged release. Pre-1.0 releases may contain intentional hard-cut API changes; security fixes do not restore removed compatibility layers.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could enable memory corruption, denial of service, unsafe realtime behavior, or unintended exposure through an integration. Use GitHub's private security advisory/reporting channel for this repository when available. Include the affected commit/tag, build profile, reproduction input, impact, and whether the issue reproduces under ASan/UBSan/TSan.

## Scope

The synchronous DSP API is designed to be caller-owned, bounded and allocation-free. Linux runtime/control-plane code, build tooling, example applications and packaging are also in scope. Acoustic-quality disagreements without a security or safety impact belong in normal issue tracking.
