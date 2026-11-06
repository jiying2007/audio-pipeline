# SYNC credit exact source continuation V1

This is a separately frozen mechanical source-preservation task. The original
70-member measurement archive contains logs, diagnostic scratch sources and
normal-cadence state/reference bytes, but not the complete measured Git object
chain. This continuation preserves that missing chain without rerunning DSP.

## Stored identity and scope

`source-continuation.bundle.b64` encodes one Git bundle. Decode it as base64;
`manifest.json` records both encoded and decoded lengths and SHA-256 hashes.
The captured head is `f3f4d7247e77fcc54a05924a84a1f93e2b9e4a3b`, including this
task's freeze. The bundle includes:

- Original measured merge `5728a4f1b43d9d66f6cea8467ac3443efe14297e`.
- Credit freeze `86c96af3fb8754eb7451f8bca2f83c3d003493f9`.
- Actual tested source `a64090d73dd4206fffc9f1f69d7f139e9c158996`.
- Raw evidence `85f998b984fa4147c24f7122be750318da432fd4`.
- Truthful budget correction `0ef16a767e0cc7efd73dd42da5237a397167e24e`.
- Preservation freeze `f3f4d7247e77fcc54a05924a84a1f93e2b9e4a3b`.

Its **only prerequisites** are the two durable public parent sources:
`a920beed8e2c66ea9d90442d31af9632f5c75a23` and
`b1f40864fb0fc941561950a656041ade6e8b9b89`. The temporary PR merge is included,
not required as an external prerequisite. The later commit storing this bundle
and manifest is deliberately not included in its own payload.

## Actual isolated restoration

The recorded execution initialized a new repository with no alternates and
fetched only the two public prerequisite histories by explicit SHA from the
local repository. It confirmed that merge5728 was absent before importing the
bundle. It then decoded the actually stored base64 bytes, verified the bundle,
imported it, and compared all six raw commit objects and tree IDs with the source.
It checked out a64090d and compared the actual SYNC implementation/header,
observation regression, unchanged original drift test and CMake bytes. Finally,
it checked out the captured head, confirmed the original elapsed-budget failure,
and passed `git fsck --full --no-reflogs`.

This local restoration verifies the container and prerequisite boundary. It is
not a claim that another remote checkout or a new DSP run occurred.
`restore-execution.json` preserves every actual command, working directory,
exit code, stdout/stderr and duration.

## Reproduction outline

1. Decode the stored base64 file and verify its decoded SHA-256 against the manifest.
2. Initialize an isolated Git repository and fetch the two public prerequisite
   commits plus their reachable histories from the authoritative repository.
3. In that repository, run `git bundle verify /absolute/path/decoded.bundle`.
4. Run `git fetch /absolute/path/decoded.bundle refs/heads/work/dualmic-sync-credit:refs/heads/restored`.
5. Check out the desired exact commit from the list above and run
   `git fsck --full --no-reflogs`.

Do not replace a64090d with a later version/API successor when reconstructing
these measurements. The original 604.192941-second overall budget remains FAIL.
No source, version, API, CMake, test threshold or R7 preparation is changed.
