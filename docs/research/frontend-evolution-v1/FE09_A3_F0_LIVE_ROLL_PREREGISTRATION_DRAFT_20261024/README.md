# FE09 A3-F0: real-source finite rolling continuation

**DRAFT_FOR_ROOT_REVIEW. No A3 implementation, build, fault experiment or
measurement is authorized by these four draft files.** Review precedes an
immutable registration, implementation authorization, complete source closure
and a separate first-execution decision.

Proposed identity: `FE09-A3-F0-LIVE-SOURCE-ROLL-33-49-V1`.

The proposed leaf connects the real first-party source/BF/S1 path to a finite
17-slide archive continuation: real sequence 33 onward, a 16-record window,
actual backpressure, and restart of the outboard worker while the source
service and external root coordinator survive. Its success decision is
`LIVE_SOURCE_EXTERNALLY_ANCHORED_FINITE_ROLL_AND_HOSTED_OUTBOARD_WORKER_RESTART_ONLY`.
It does not close the broader scopes of #791/#796, alter I025–I040, or confer
acoustic, installed-SDK, cold-system-boot, device-resource or physical-power-loss
authority. The machine draft is `test-contract.json`.

## Qualified baseline and the concrete gap

The baseline is `7138b17acd6246cc779efa7597d25771ddfc8c7a`. Its own Verify
`40107399403/attempt-1` completed with 80 successful jobs and one skip;
summary `120920642884` belongs to that SHA and Actions App `15368`.
Release `40110388667/attempt-1`, release job `120920690038` and convergence
`120920758167` succeeded. Provider readback is recorded in
`EXECUTION_BASELINE.json`. These are baseline facts, not A3 results.

A2 issue #825 is completed. `source-lock.json` freezes original inputs at
7138 and proves their equality to 5187c5e...; A3 does not depend on CALL
resource numbers from #841/PR #844 or its separate F1 continuation.

| Existing interface | Relevant restriction |
| --- | --- |
| S1 init/step/drain | Init needs a fresh source. Callback function/context are pinned. Sequence can naturally exceed 32; there is no live rebind or BF/source restore API. |
| A0 bind/name/sink | Finite contiguous prefix, cap at most 32. Bind takes directory/config/map/cap, with no S1 callback parameter. Full/ambiguous storage withholds ACK. |
| A1 FRM2 | Fixed high-water 32 and window 17..32; no ACK or prune. |
| A2 FPR1 | One fixed 1..32 → 17..32 retirement; requested head/tail 32; external expected anchor; no source ACK. Its exported record validator rejects >32. |
| Internal A0 byte validator | The pure checks are not inherently capped at 32. Exposing them is a new read-only validation authority, not an extension of public A0 admission. |

The old A2 fixture constructs finite original-codec/ring input. That is not
live source production through 33. A3 must call actual B1S0 producers and
actual S1 step/drain from sequence 1; hand-setting a ring, fabricating A0
admission or resetting source state at 32 cannot substitute for this path.

## Fixed data and why the endpoint is 49

Both profiles are C4 ULA, 16 kHz, 10 ms, Render enabled, microphone x positions
0/0.035/0.070/0.105 m, slot map `[2,0,3,1]`, unchanged FIR33_HANN BF and one
source generation. K1 uses source depth 2; K2 depth 4. Exact IDs, generation,
PCM arithmetic and geometry are in the machine draft.

Successful fixtures have Capture 1..49 and 49 real Render owner events:
PRESENT 1..32, ABSENT 33..34, PRESENT 35..49. This is 47 actual Render PCM
frames. Original `ref_submit` requires association sequence to advance on
both event types. ABSENT 33/34 uses epoch 1/reason 1; reentry 35 uses epoch
2 and `FE_B1S0_RENDER_GAP`; later PRESENT keeps epoch 2 without GAP. The
actual Render DSP ordinal at Capture 35 is 33. Generation never changes.
APX3 local sequence remains 1; FBS1 global sequence advances naturally.
ABSENT has no APX3 Render channel and no substituted zero PCM.

After actual A2, append 33 changes 17..32 to 18..33. Append 48 yields 33..48,
replacing the whole inherited window. Append 49 yields 34..49 and retires
the first record created by A3. These are 17 finite slides, not arbitrary
duration rolling qualification. Original S2 layout gives 1,760 APX3 bytes
for PRESENT and 1,440 for ABSENT; with each original 200-byte FBS1 row, the
49-frame stream is **95,400 bytes**. Runtime must obtain the same sizes from
`fe_s2_layout`, without a second encoder.

## Real owners, transport and A0/A1/A2 handoff

A surviving Python coordinator owns child lifecycle and trusted root state.
One persistent C source process has four distinct pthreads: Capture, Render,
BF/S1 producer and S1 consumer. One C outboard worker owns filesystem I/O.
Only the outboard worker is restarted in this leaf.

Before source threads start, the worker performs real A0 bind with cap 32
on an empty exclusive directory and reports bound-ready. The source then
binds fresh BF/B0/B1S0 and initializes S1 with one stable proxy function and
context address. The proxy forwards unchanged original bytes; the worker
calls the actual A0 sink for 1..32. Only that sink's real exact-byte ACK
permits the original S1 drain to advance. This proxy composition is new and
must itself be qualified; an A0 struct is never manufactured for handoff.

The parent brokers bounded binary transport, holds at most one pending
source packet, and receives the original source row independently of the
worker root proposal. It never re-encodes PCM/APX3/FBS1 or runs BF. Delivery
is bound to actual receive length/hash, nonce and worker incarnation. Fresh
workers receive paths, external metadata and the same pending original
bytes, but no old data descriptor, A0 object, BF state or source owner.

At 32, a new barrier generation removes all next-frame credits. Each owner
reports PAUSED after its last API returns, binding that barrier generation
and its last command/return sequence. Acquire loads must show both source
queues and S1 empty at 32. This live observation backs actual A1 bind/publish
and A2 prepare/acknowledge/publish/resume on the genuine bound A0/A1 objects.
The same four threads then continue. No reinit, rebind, counter seeding,
source generation change or Capture BF reset is allowed.

Mid-run code never cross-reads non-atomic source/BF metrics or snapshots a
live source container. It uses API return witnesses and atomic queue fields.
Final non-atomic counts and BF information are inspected only after all four
joins. Pointer-containing container hashes cannot be used as cross-process
equivalence oracles. Worker-owned outputs/receipt can be compared around a
FULL call without examining another owner's state.

## New outer root and unchanged record bytes

New `A3R1` is 3,656 bytes: a 256-byte header, one unchanged 200-byte left row
and 16 unchanged retained rows. The exact header layout is in the contract.
It binds source/map/K/depth, absolute window/high-water, generation 0..17,
previous **raw** A3 root SHA-256 and original FPR1 raw SHA-256. The self digest
zeroes only its registered field; the external anchor hashes all final root
bytes. SHA-256 remains original `fe_b1s1_sha256`.

R32 has generation 0, left row 16, and window 17..32. The unchanged A2 parser
validates FPR1, which contains original row 16. Retained 17..32 is reread
through the original codec/validator before genesis. R33..R49 shift exactly
one row and append the living-source row. The parent constructs the expected
next root before accepting the worker proposal.

FRM2/FPR1 retain their fixed formats and separate namespaces. Old readers
continue failing closed after their original source window disappears.
Legacy data keeps A0 names; new data 33..49 uses A3 names containing absolute
ID/generation/sequence and full-row/APX3 hashes. No published file is reused
modulo or overwritten. After deletion, the left row is only a source-bound
metadata anchor; retired PCM is not reverified from a digest.

A thin adapter may include locked A0.c once and expose unchanged
`source_ok`/`valid_record` checks. Its metadata-only view is not a bound A0
owner and grants no sink, ACK or prune authority. The original A0 must not
also be compiled separately. This new finite validator, its actual object
and call entry, source/map binding, domain and whole-row previous hash need
independent qualification. Old public A0/A2 caps remain unchanged.

## Ordered transaction and external trust

There is one pending original packet/nonce. The worker writes the full data
temp O_EXCL, fsyncs it, publishes without clobber, removes the same-inode temp
alias, fsyncs the data directory and reopens/replays the record. The parent
accepts exactly one pending next-root proposal. The worker writes/fsyncs and
publishes that root, removes its temp alias, fsyncs the root directory and
rereads it. The surviving parent then promotes its trusted current root.

Only afterward may the worker unlink the exact retiring record, fsync the
data directory, verify all 16 current records, remove the old A3 root, fsync
the root directory, and obtain final per-call commit authorization. Only
then can it return the original byte ACK. S1 drain alone advances S1 tail.
Root visibility, parent promotion, retirement completion and source ACK
are four distinct reported facts.

A pending proxy call remains in the living source process across a worker
cut. One fresh worker may explicitly repeat current barriers/readback and
finish that same packet. It cannot rerun Capture BF, create a duplicate root
generation or ACK twice. Duplicate promotion is rejected; a separate resume
authorization can finish an already promoted pending transaction. Read-only
entry points cannot sync, publish, unlink or ACK.

Fresh trust comes from the surviving coordinator's current/pending roots,
nonce, directory device/inode and live source observation. Missing external
authority is BLOCKED. Self-consistent disk SHA or the largest filename cannot
prove freshness. A coherent stale caller anchor cannot be detected without
a surviving monotonic authority. Loss of parent/source state and whole-system
restart are explicitly unresolved; no source/BF restore API exists here.

Steady data capacity is 16; a slide reserves a seventeenth distinct inode.
A known final/temp pair may briefly give 18 names for 17 inodes. Arbitrary
aliases fail. Bootstrap actually has 32 A0 records: lifetime peak is not 16.
If the extra reservation fails, withhold ACK; never delete first to fit.

## Exact finite matrix

Native, ASan+UBSan+LSan, ARM32/QEMU and native TSan each run one suite, in that
order. No hidden retry, best-of selection, skip or sanitizer disable.

| Per target | Cases | C processes/case | Starts | Capture admitted = BF processed = S1 published | S1 ACK |
| --- | ---: | ---: | ---: | ---: | ---: |
| Positive K1/K2 | 2 | 2 | 4 | 98 | 98 |
| C01..C16 cuts at 33 and 49, K2 | 32 | 3 | 96 | 1,536 | 1,532 |
| F01..F12 I/O failure at 33, K1 | 12 | 3 | 36 | 396 | 384 |
| C metadata batch | 1 | 1 | 1 | 0 | 0 |
| **Per target** | **47 case/batch protocols** | | **137** | **2,030** | **2,014** |
| **Four targets** | | | **548** | **8,120** | **8,056** |

The Python collector and compiler/link/version/ELF commands are separately
budgeted. One ARM invocation is one host QEMU process with one guest target.
These are proposed counters, not observations.

At cut 33, no source owner receives credit for 34: admitted/processed/published
and unique callback sequence are exactly 33, with ACK 32. At cut 49 they are
49/48. C02 (empty data temp) and C08 (empty root temp) permit only fresh
read-only HOLD. No cleanup, repair, fresh packet delivery or later frame is
allowed. Thus four cut cases do not recover to 49; the other 28 explicitly
resume once to 49/49. Every I/O case stops at 33/32 and only gets a fresh
read-only inspection, preserving actual/reported syscall outcomes.

Only the positives deliberately fill queues. Consumer 33 blocks before data
temp creation. K1 publishes S1 through 33 and fills source queues through 35;
K2 publishes S1 through 34 and fills source queues through 38. Staged credits
avoid incidental early FULL calls. One additional Capture submit, Render
submit and S1 step must return FULL without publication/tail/ACK changes;
worker-owned outputs/receipt remain unchanged. Release drains queued frames
and finishes 49. Each positive therefore has 50 Capture, 50 Render and 50
step calls, exactly 49 successes and one FULL in each category.

The draft enumerates 19 C metadata controls, six coordinator controls and
eight sealed-artifact controls. They use authentic retained bytes and actual
validators/dispatcher, without claiming extra live-source frames or crashes.
Original codec replay counts are separate from live BF frame counts.
Same-target K1/K2 streams and beam/reference results agree per frame; each
other case agrees with its applicable positive prefix. Integer PCM/APX3/FBS1
agree across targets. ABSENT is no emitted reference, not stale/zero PCM.
No cross-ISA floating tolerance or acoustic threshold is introduced.

## Bounded resources and source closure

Proposed limits: collect/build/test/cleanup/seal 600 s; each target suite 120 s;
child 30 s; tool command 60 s, all additionally bounded by remaining enclosing
deadlines. A dedicated job in existing quality.yml has 900 s and 300 s archive
reserve. It does not extend another job or add a workflow. A complete original
Jobs API observation binds the actual job/start/run/attempt/head before DSP.

The 65,536-byte **new owner/proxy/control** envelope reserves workspace 32,768,
new persistent owner/proxy/receipt/control state 8,192, new-code local call
chain 16,384 and new read-only data 8,192. Compiler layout/section/stack/call
graph evidence must enforce it. New C transaction/proxy code has no heap.
Workspace includes two 3,656-byte roots, **two full 5,320-byte record buffers**,
18 bounded inventory entries, names/digests/decoded fields: 24,064 named bytes,
leaving 8,704 within the workspace for real layout/alignment. Hidden APX3
copies or omitted buffers fail the contract.

Original BF state/work, B1S0 queues, B0 reference state, S1 K×5,324-byte slots
and original 5,120-byte step scratch, A0/A1/A2 state/work, original helper
stack, pthread/libc, sanitizer, QEMU, Python buffers and page cache have
separate ledger rows. The parent holds at most one full pending record and
two raw roots. None is a hidden exclusion from a claimed whole-system 64 KiB.
Full dynamic stack, RSS attribution, board RAM and real timing are NOT_MEASURED.
Source-fixture allocations are separate even when the new driver allocates
them: Capture PCM 1,280 bytes, Render PCM 320 bytes, beam/reference output
640 bytes each, BF state/work reservations 16,384/32,768 bytes and actual
compiler-sized original receipts. The 64 KiB envelope is not a claim about
all storage introduced by the test executable.

Each active filesystem fixture is capped at 1 MiB. A dedicated binary IPC
channel allows 256 KiB per direction/process and at most 8,192 bytes/message.
Diagnostic stdout/stderr each retain a separate 64 KiB cap. Source record
bytes are retained once/fixture, with actual receive hash/length witnesses
for forwarded deliveries. All channels still count toward artifacts:
collect.log 16 MiB compressed/64 MiB fully decoded, receipt 4 MiB, verify log
1 MiB, ZIP 32 MiB. Compression preserves exact bytes and order; overflow
cannot truncate into PASS. Every failed attempt remains preserved.

The lock freezes original payloads but marks all future A3 files/hookups
pending. Planned additions are one original-validator adapter, private owner
header/C, real-source multiprocess driver and collector/read-only verifier.
The original A2 source graph is reused with A0 included exactly once. No
old regression, installed source/header, global CMake or shipping behavior
is changed.

Before execution, independently review the complete actual source/include/
generated-header/compiler/link/ELF/sysroot/launch closure. Complete the lock,
including the new verifier; it must not embed that same lock's digest. Commit
source C. External review pins C/tree and lock/contract/baseline hashes; the
lock omits its own hash and containing commit. Candidate JSON or an untrusted
`--source` value alone is not authority. Resolve actual CI test-merge versus
reviewed C before any automatic target run.

After root review: immutable registration, authorized implementation, exact
fixed matrix, independent original-artifact readback, complete exact-head
Verify, protected expected-head merge, distinct new-main Verify and same-SHA
Release/Convergence are the leaf's delivery gates. #657/#767/#791/#796 and
physical #58 retain their own unsatisfied scopes.
