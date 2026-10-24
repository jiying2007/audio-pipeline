# FE09 T3-S3 F1 R1: target lifetime and executable-image RSS preregistration

## R1 authority and exact recovery boundary / R1 权限与恢复边界

**DRAFT_FOR_REVIEW_NOT_FROZEN — F0_MAIN_D_QUALIFIED; FINAL_GUARDED_B,
IMPLEMENTATION, FINAL_C_AND_EXTERNAL_FREEZE_PENDING.**

本轮交付仅为新的 R1 五文件预登记。F0 主线 D 已独立闭环；F1 实现、静态编译、
工程进程与 DSP 均未执行。未来先以 `SOURCE_METADATA_ONLY` 接入 guard，待含 guard
的实际 B 自身主线闭环后，才可冻结最终 C 并进入测量。仅更新文档的最终 C 也必须
由实际 B 的 guard 强制安排 F1 job，不能通过 fast-docs 提前宣告完成。

This is a **new R1**, experiment `FE09-T3S3-F1-TARGET-LIFETIME-AND-IMAGE-RSS-R1`, at `docs/research/frontend-evolution-v1/FE09_T3S3_F1_RSS_PREREGISTRATION_R1_20261024`.
It is not byte recovery of the three lost reviewed JSON files. The old README
and EXECUTION_BASELINE exact bytes are archived at
[49ab8e67731d93abdee9cecef853a58eb4b231d7](https://github.com/jiying2007/audio-pipeline/commit/49ab8e67731d93abdee9cecef853a58eb4b231d7).
The old test-contract, source-lock and negative-controls bytes remain unavailable;
their recorded hashes are historical identity witnesses only, never executable
inputs. `EXECUTION_BASELINE.json.recovery` lists all five prior byte identities.
The original139-control count is not a quota or a recovered R1 inventory.

The drafting anchor is D `92a7546a75cfe0d8aca132c7ee5996dcf0005c74`, tree `894253393823d842f620be408ec12339a61771d2`. D has its own independent
[Verify40111373922/a1](https://github.com/jiying2007/audio-pipeline/actions/runs/40111373922/attempts/1)
(81 jobs:80 success,1 expected fast-docs skip; summary120931623192/App15368), and
[Release40114080519/a1](https://github.com/jiying2007/audio-pipeline/actions/runs/40114080519/attempts/1)
plus convergence. Its original main artifact12566987972 was downloaded and fully
reread with the unchanged source-bound F0 verifier; artifact SHA256
`e602c9de118d0b34754b67ff99f4d86f40a5e19c37abd6544619e82a52afaa02`.
The independently published closure is
[#841 comment6390447705](https://github.com/jiying2007/audio-pipeline/issues/841#issuecomment-6390447705).
The new recovered-session reread report is a new record, SHA256
`025a74e9fcaf040466e36373118e90b4b91b68b1d497b0fa21b64394615247e4`;
the earlier report's lost bytes are not claimed recovered. All observed source,
run, job, artifact and reread identities are retained in the baseline. D closure
does not make D the unknown future protected B, nor permit an F1 process.

Current root authorization is documentation and bounded metadata reconstruction
only. No F1 implementation, test implementation, static compilation, launcher,
engineering fixture, DSP collection or remote mutation is performed here. Root
will independently review/checkpoint these five files before separately
authorizing source/static preparation. No valid execution-freeze comment or final
B/C identity is asserted by this draft.

## One causal question / 唯一测量问题

F0's independently read local Native original records all retain a child-lifetime
`wait4` peak of 54,632,448 B. The [additive F0 readback](../FE09_T3S3_F0_LOCAL_DIAGNOSTIC_READBACK_20261024.md)
preserves those numbers, the first Sanitized exit failure and their exact measured
source `87eace16b9cacbf0cb911eab02b91ca941cc6eff`. It explicitly leaves post-exec
executable-image RSS and working set unmeasured. F1 asks whether an independently
identified target, forked by an already-execed small native launcher, can supply
a clearer lifetime record plus separately bounded current-image observations.
It does not change an algorithm or select a smaller numeric RSS result.

F0's contract SHA-256 remains
`42496ab0f6f01d5b36f03d23f670f585a5f57c120ecf9fc0237a27d5aa2f34f2`;
its 88-member source lock remains
`16cd84381647bef1015fc8ef338bb9b10dd09ce4669248355ac4f48745d8a4ff`.
F1 keeps all those source/input bytes and the F0 probe, private build and verifier
unchanged. New F1 checkpoint code intentionally produces new privately linked
ELFs. These are not represented as the original F0 ELF bytes or as an unchanged
F0 execution. Their full new build and binary identities require separate review.

## Why two observations are necessary

Linux [getrusage(2)](https://man7.org/linux/man-pages/man2/getrusage.2.html)
preserves resource-use metrics across exec. CPython's
[3.12 subprocess documentation](https://docs.python.org/3.12/library/subprocess.html#disabling-use-of-vfork-or-posix-spawn)
allows internal vfork; the name `_fork_exec` alone does not establish that an
actual launch used ordinary fork. Equal F0 maxima do not quantify a Python
contribution. F1 does not reconstruct or subtract one.

An ordinary [fork](https://man7.org/linux/man-pages/man2/fork.2.html) starts new
child resource history while inheriting the launcher's current address space.
Linux [dup_mm](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/fork.c)
initializes the new mm high-water value from current RSS. Therefore F1 must first
exec the small native launcher and only then ordinary-fork the real target.
The outer Python collector's wait4 on the launcher remains a separately labelled
supervisory record; its PID or RSS can never stand in for the target's.

Linux [task_mem](https://raw.githubusercontent.com/torvalds/linux/v6.12/fs/proc/task_mmu.c)
prints VmHWM from the current mm, while
[exec](https://raw.githubusercontent.com/torvalds/linux/v6.12/fs/exec.c) preserves
the old mm maximum in lifetime accounting. However,
[proc_pid_status(5)](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html)
explicitly calls VmHWM/VmRSS inaccurate. The
[statm manual](https://man7.org/linux/man-pages/man5/proc_pid_statm.5.html)
describes kernel accounting optimizations and the slower smaps alternatives.
An accurate instantaneous mapping snapshot would still not record all intervening
peaks. F1 does not introduce smaps polling or a working-set claim.

Linux [wait_task_zombie](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/exit.c)
uses RUSAGE_BOTH; [getrusage](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/sys.c)
can incorporate accounted-for descendants. An exact target PID is necessary but
does not turn wait4 into an exclusive-main-image or simultaneous-process-tree RSS
measurement. The runner's actual kernel release, page size and ABI are retained;
the v6.12 source citations explain the reviewed design, not a claim that a future
hosted kernel is exactly v6.12.

## Proposed finite observation protocol

1. The Python collector starts the pinned native launcher. The stage and target
   deadlines already run; no clock is restarted at fork, exec or a checkpoint.
2. A single-threaded launcher finishes bounded setup, then calls ordinary fork
   exactly once for this science invocation. No shell, vfork, posix_spawn, PATH
   search, Python preexec callback, injected preload or resource-limit trick is
   an alternative implementation of this contract.
3. The real child emits PREEXEC and blocks. The launcher retains its raw host
   `/proc/<pid>/status`, identity and start-time record before ACK. The child's
   own preexec getrusage is retained as an **observed floor**, not a complete
   preexec upper bound. The reviewed child path then execs the exact target.
4. A thin new `--wrap=main` observer emits ENTRY before calling the unchanged
   original main, and RETURN after that main returns. Each message blocks until
   the launcher captures host status/identity and replies. The original F0 call
   timers stay inside the unchanged original main. The new shim and handshakes
   remain part of the F1 process-memory and total-wall scope, with no subtraction.
5. The launcher calls wait4 for the specific fork-returned child PID and preserves
   raw wait status and rusage through final exit. An exec-error-pipe EOF alone is
   insufficient: the matching ENTRY, RETURN, complete science body and successful
   final exit are all required for a successful case.

There are three raw status/identity observations: PREEXEC, ENTRY and RETURN.
They share the exact child PID, process start ticks and namespace mapping. PPid
must remain the launcher. ENTRY/RETURN identify the actual new executable;
PREEXEC identifies the launcher image in the child. One per-invocation nonce,
case/repeat/variant, ordered channel records and original argv bind the protocol.
The private build must establish the wrapper and original-main symbol wiring;
[GNU ld --wrap](https://sourceware.org/binutils/docs/ld/Options.html) is the proposed
mechanism, not a claim that this draft has compiled or exercised it.

For QEMU the native launcher execs the pinned host QEMU binary with separately
pinned guest ELF and sysroot. Both checkpoints cause the launcher to read the
host PID's proc files; guest `/proc` interpretation is not used as authority.
The [QEMU user-mode documentation](https://www.qemu.org/docs/master/user/main.html)
describes its host-system-call and threading model. No host-emulator RSS is
renamed as ARM hardware, guest-only RSS or SSC305 memory use.

## Immutable interpretation boundaries / 不可放宽的口径

- `wait4_target_lifetime_rss_bytes` is the Linux-reported target-lifetime maximum,
  converted from raw KiB by exactly 1024. It includes the target's launch/preexec
  history and may include waited-for descendants; it is not a concurrent tree sum.
- `preexec_observed_rss_floor_bytes` is retained without subtraction from any
  other quantity. A larger final lifetime maximum does not locate its origin.
- ENTRY/RETURN VmHWM are approximate **current-mm-window** observations after a
  confirmed image transition. They include image construction/loading, harness,
  libc, runtime and F1 measurement costs. They are not pure DSP or exact working set.
- The RETURN snapshot ends before wrapper return and subsequent C-runtime,
  destructor, atexit, sanitizer or emulator cleanup. That later interval is not
  covered by the RETURN VmHWM claim. Only the final lifetime record extends to exit.
- Sanitized runs retain the original ASan/UBSan flags and leak detection. ASan has
  its own [memory overhead](https://clang.llvm.org/docs/AddressSanitizer.html);
  [LSan](https://clang.llvm.org/docs/LeakSanitizer.html) runs an exit-time phase.
  Complete raw frames followed by a nonzero/signal exit are rejected, as in F0.
- `H_return > H_entry` supports only a reported high-water increase after ENTRY
  in the same validated mm history. `H_return == R_wait` means that reported
  final value is also present in the after-exec current-image observation. Neither
  statement proves first/exclusive peak origin, exact timing, descendant absence
  or a mathematically exact physical-memory upper bound.
- Disagreement between related counters is retained as an accounting observation.
  It cannot be repaired by changing numbers, tolerances, units, scope or execution
  selection. Interpretation may remain inconclusive even with a complete matrix.
- No current-mm reset, clear_refs write, parent-max subtraction, polling peak,
  RSS-saving algorithm change, additional input selection or numeric RSS admission
  threshold is authorized. All shipping/acoustic/device promotions remain false.

## Fixed science matrix and separate process accounting

The exact sequence is target `[native, sanitized, arm]`, case `[ALL_P, PAP]`,
repeat `[1, 2, 3]`, then variant `[reference, measured]`.
That is **36 actual science targets and 21,600 frames**, plus **36 distinct native
launcher processes**, not 72 science targets. Every target retains all 600 frames;
zero warmup frames are excluded. All three repetitions remain separate. Raw PCM,
beam output and every canonical public frame metric must match same-target
reference/measured and all repetitions; the original B3 semantic checks remain.
The original F0 raw call timings, quantile definition and storage disclosure remain
part of the measured variant and are recomputed separately for each repetition.

No target is rerun, replaced, reordered or selected because of its RSS. An early
failure preserves its partial current case and stops the cohort; the receipt
retains attempted targets, raw executed frames and validated frames separately.
A partial result is never combined with a replacement attempt to label this
cohort complete. Local execution never supplies the hosted-image qualification.

`negative-controls.json` contains **178 new R1 planned metadata controls**:
174 complete peer-draft control objects retained verbatim plus four explicit
bootstrap/actual-B/docs-only activation controls. None recovers the lost old139
inventory. All178 remain NOT_IMPLEMENTED_NOT_RUN. Metadata mutations
run on copies of complete evidence and add zero DSP frames. Seven separately
labelled native engineering fixture invocations are proposed for later protocol
verification: seven fixture launchers, seven direct fixture children and at most
one descendant in the one registered descendant case. Their maximum fifteen
processes and ten-second aggregate runtime are separate from the science counts
and inside the same stage budget. The fixtures contain no DSP. None exists or has
run in this drafting tranche.

## Budgets and the 64 KiB accounting proof

The proposed hookup is a **separate `frontend-rss-f1` job inside the existing
Quality reusable workflow**, using the same pinned image, `ubuntu-24.04` runner,
15-minute job limit. Existing `inputs.run_extended` is preserved; an additional
protected-B-derived `inputs.run_f1` forces the registered execution obligation
when final C changes only preregistration documents. It does not add
a new standalone/scheduled workflow or append F1 to `frontend-reference`. F0's
collector, contract, original job deadline and hard-coded job-name selector remain
unchanged. No monkey-patching of F0 globals or pretending the F1 job is local is
an admissible integration.

This choice follows original F0 evidence, not an assumed F1 runtime. In
[PR Verify 40108346153/a1](https://github.com/jiying2007/audio-pipeline/actions/runs/40108346153/attempts/1),
job `120915025432` (`quality / frontend-reference`), artifact `12565534873`, original
`receipt.json` SHA-256
`1bb6e95ecfe10acf70bac94db8997fafee09756a1038e1706a2fc4d224f378d3`,
the stage used 65.91799439299996 seconds of an effective 171.116872549057 seconds.
The recomputable remainder after that stage and the 60-second archive reserve
was only about **105.199 seconds**, before any subsequent work. That does not
provide the registered 180-second F1 window for a fresh build, handshakes, seven
engineering fixtures, 36 targets and final verification/sealing. This draft does
not claim F1 fits the smaller tail or plan to enlarge budgets after a first timeout.

The new job's first executable step independently retains its own bounded original
Jobs API response/request and 900-second deadline before checkout or collection.
F1 admits only the exact observed job name `frontend-rss-f1` or
`quality / frontend-rss-f1`, with the original API selecting one unique in-progress
job and binding its positive ID/run/attempt/head/start. Its own environment paths
are `FE_T3S3_F1_JOB_DEADLINE_FILE` and
`FE_T3S3_F1_JOB_API_OBSERVATION_DIR`. The F0 observation/deadline is not reused.
The Jobs API itself uses the existing actions-read permission. The separate
external-freeze protocol additionally needs issues-read and pull-requests-read.
No token or private credential is passed to target processes. F1 keeps the exact
tuple rules in its own reviewed selector rather than assigning to F0's function
or constants. The exact caller/child permission changes are listed below.

The limits remain 180 seconds for the complete stage, 30 seconds per science
invocation including launcher/setup/handshakes/exit/reap, 60 seconds per build/tool
command, 900 seconds for the dedicated F1 job and a 60-second archive reserve.
Before build or science execution, that job's original bounded API bytes and
request record must independently bind exact ID/name/run/attempt/head/start to
its own original deadline. In CI the effective stage limit is exactly
`min(180, original_job_deadline - stage_started_epoch - 60)`; a nonpositive value
rejects before work. This draft additionally requires the whole 180-second window
at collector admission: if the result is less than 180, retain
`INSUFFICIENT_F1_STAGE_WINDOW` and start zero science targets or process fixtures.
Thus setup before the collector may consume at most 660 seconds of the original
900-second job; the clock is never restarted. Local mode retains original_job=null
and exactly 180 seconds. Verification, fixture controls, cleanup and final sealing
consume that same clock. The independent job makes a full window available by
design; it does not promise that unmeasured F1 work will finish successfully in it.

The new job does not rerun the entire frontend-reference research sequence or
consume a same-run F0 artifact as its predecessor. Immutable independently closed
F0/main evidence remains the prerequisite. The existing Verify `quality` reusable
call and `summary` dependency on `quality` carry the job outcome; failures cannot
use continue-on-error or a fake success. The proposed artifact prefix is
`frontend-rss-f1-{run_id}-{run_attempt}` and original failure bytes are uploaded
under the registered cap/reserve. Source-only mode remains explicit while the
external pin ingress or activation is pending: JSON/source checks only, no science
targets or engineering process fixtures. Both the gate wiring and exact action
pins are subject to implementation review before activation.

Each successful case's new RSS/protocol metadata is partitioned below. Limits
apply to **retained serialized bytes**, including JSON escaping and newlines;
uncompressed sizes count. No category borrows from another.

| Retained category | Fixed count / individual cap | Maximum bytes |
| --- | --- | ---: |
| Original proc status bytes: PREEXEC/ENTRY/RETURN | 3 × 8,192 | 24,576 |
| Identity records including original stat text and exe identity | 3 × 4,096 | 12,288 |
| Ordered control transcript, child messages and parent ACKs | 6 × 1,024 serialized records | 6,144 |
| Actual-target wait4 record | 1 × 4,096 | 4,096 |
| Outer supervisor record | 1 × 4,096 | 4,096 |
| Bounded launcher/protocol diagnostic log | at most 24 × 256-byte lines | 6,144 |
| Case index with complete bounded argv and declared runtime environment | 1 × 4,096 | 4,096 |
| Failure/overflow context (empty record on success still counts) | 1 × 4,096 | 4,096 |
| **Total** | | **65,536** |

This arithmetic covers all three status/identity pairs and the launcher log; it
does **not** hide the target stdout/stderr inside a smaller envelope. The single
combined target stdout/stderr log retains its separate existing **1 MiB** cap.
The existing timing file also retains its 1 MiB cap. All of these bytes count
toward the 8 MiB temporary-case limit and the 32 MiB complete-artifact limit.
Thirty-six full metadata envelopes total 2,359,296 B inside that artifact cap.

To keep identity/index encoding bounded, the contract separately caps raw stat
text at 1,536 B, exe/path strings at 512 B, science argv at 2,048 B, launcher argv
at 3,072 B, declared runtime environment at 512 B and each wire message at 256 B.
The science argv/environment live in the case index; complete launcher argv lives
in the separate supervisor record. Namespace vectors remain in original status
bytes and are parsed there, rather than duplicated inside identity records. Both the
field caps and the final serialized category cap must hold; one does not imply
the other. A host proc status is admitted only if its complete original bytes fit
8,192 B. No actual F1 host has been measured in this draft, so this is a strict
admission envelope, not a claim that arbitrary Linux status files always fit.
Future engineering preflight must check the envelope before any science target.
Excess bytes cause rejection, not truncation-and-success or a larger budget.
Bounded failure preservation retains exactly the observed prefix and a separate
overflow indication; it never labels an incomplete proc file complete.

The exact member field sets are listed in the machine contract. An identity
record carries raw stat, exe identity, PIDs/start ticks, observation interval and
a digest of the registered case-binding subset; it contains no argv/environment
copies. The case-binding digest covers only the declared case/nonce/child-argv/
environment/output/image-identity fields, not the case-index file itself. The
supervisor record has the complete launcher argv and bounded supervisory outcome;
the actual target wait4 record remains separate. Field caps are admission checks;
the independently enforced final serialized cap is authoritative for every file.

## Two-stage source closure and non-circular freeze

The lock contains **109 rows**:96 exact unchanged original source/authority files,
four concrete new R1 document rows, six future implementation rows and three future
hookup rows. Its own member hash is omitted. The96 originals are exactly the88
F0 source-lock rows plus F0's four preregistration files, original F0 readback,
private CMake, measured probe and collector/verifier. Their D bytes do not change.
The nine future rows carry null final identities and explicit pending states;
no empty placeholder implementation is asserted. Every pending row blocks
measurement. Complete compile/link/include/import and generated-input closure is
specified in `test-contract.json.build_closure`.

1. After root independently freezes this R1 document design, root may separately
   authorize source/test editing, syntax checks, static compilation and pure
   in-process offline metadata controls. **No produced F1 launcher, fixture or DSP
   executable runs.** Preparatory compiled products never replace a registered
   fresh build from final C.
2. If actual protected B has no F1 guard, first introduction is
   **SOURCE_METADATA_ONLY**, with zero F1 launchers, zero engineering processes,
   zero DSP targets and zero frames. Independent root source/wiring review is
   required. A candidate comment cannot authorize bootstrap measurement or claim
   that a nonexistent B guard ran. Protected-squash that guard/bootstrap source
   and independently close its own distinct main Verify/summary and
   Release/convergence before selecting the resulting actual guarded B.
3. Finalize a new actual execution C against this closed guarded B. Fill real B
   closure evidence, all implementation/source hashes and exact control mappings.
   The lock hashes README/contract/negative/baseline and all source inputs, but
   not itself. It contains neither C nor its own digest nor a future comment ID.
   The locked verifier does not embed the lock digest. A pending baseline cannot
   be waived by a boolean or external comment.
4. Root independently reviews complete C/tree and all external byte digests, then
   posts the strict issue845 freeze. C and locked baseline do not acquire that
   future ID/body hash; those are runtime/additive evidence. Wait for a later
   provider second before opening the registered PR or publishing its new
   synchronization event. A docs-only C still forces actual F1 scheduling.
5. Actual final C execution requires the real B guard, complete live PRE authority
   before build or any F1 process, the single bounded fixture/science cohorts,
   complete POST authority and deadline-safe cleanup/seal. Root's independent
   original-artifact/provider readback follows. The protected squash main S has
   its own distinct source-bound execution and gates; a PR result is not main
   evidence.

This R1 remains draft. A later approved protocol status may become
`PROTOCOL_REVIEWED_EXTERNAL_COMMENT_REQUIRED_AT_RUNTIME`; it still cannot predict
its approving comment. A changed source, full tree, base, method or budget needs
a new independently reviewed C and a new comment. Existing attempts/failures stay
separate; no automatic retry, result selection or retrospective RSS correction.

## Fixed external freeze authority: issue #845

| Field | Exact value |
| --- | --- |
| Repository | `jiying2007/audio-pipeline`, REST id `1347377137` |
| Issue | [#845](https://github.com/jiying2007/audio-pipeline/issues/845) |
| Issue REST / node identity | `6015285792` / `I_kwDOUE9X8c8AAAABZon6IA` |
| Issue created_at | `2026-10-24T16:50:18Z` |
| Actual author | `jiying2007`, id `33591504`, type `User` |
| Registered head | `research/fe09-t3s3-f1-rss-20261024` in the same repository |
| Registered base / events | `main`; `pull_request` and actual protected squash `push` |

The complete strict JSON Schema is `test-contract.json.external_freeze.body_schema`.
It binds exact protocol/version/experiment/repository/issue/author/scope, qualified
D/tree(D), protected B/tree(B), reviewed C/tree(C), lock/contract/baseline/negative
SHA256 bytes, explicit root independent review decision and real UTC review time.
All object schemas reject unknown fields; duplicate keys, non-finite numbers,
boolean-as-integer coercion, malformed dates and markdown wrappers reject. The
16384-byte body limit includes actual UTF8 bytes. Placeholder patterns in this
draft are not final identities.

**Derive actual C/B before freeze selection.** On main first bind actual S, read
the complete S-associated PR list and unique real merged PR, then derive head C
and B from S's immutable sole parent. Only then inspect freeze records for C.
Candidate CLI pins and same-tree lookalikes are not the lookup authority.

At each PRE and POST, retain issue-before, the full `per_page=100&page=1`
comments page without `since`, the selected direct comment and issue-after.
Both issue `comments` counts must equal full array length<=100; IDs are unique
positive integers, no next-page Link, missing page or truncated body. Both issue
observations bind fixed REST/node/repository/creator/creation identity and cannot
be a pull request. Issue title, body and open state are not execution authority.

Only actual fixed-author comments can approve. Non-JSON conversation is
nonauthoritative; that author's JSON-object comments are reserved for this strict
protocol and must parse completely. Exactly one valid actual-C record is required,
including rejection of identical duplicates. A valid other-C record cannot be
selected by equal tree. Direct selected bytes/identity must match the full list.
Require `created_at == updated_at`, review time<=creation, and creation strictly
before the **original run.created_at**, never job/rerun start or asserted local
time. Equal-second boundaries reject.

POST repeats the entire count/list/uniqueness/direct-record procedure and actual
source binding, then requires identical selected ID/node/author/issue/timestamps/
body bytes/hash. Fetching only the old ID misses duplicates and is insufficient.
Deletion, edits, ambiguity, incompleteness or unreadability reject qualification
while preserving attempted evidence. Independent root readback reacquires live
provider records and exact original run/job/artifact identity. These finite
observations do not prove that no transient edit occurred; this is not a
cryptographic-immutability or hostile-runner guarantee.

## Request inventory and unchanged limits

The first executable dedicated-job step acquires its own original Jobs body
before checkout:1 GET. Each subsequent sweep is exactly the following bounded
route order. On PR the association row is omitted, so the count is15; on main
there are **1+8+8=17 GETs**. No retries or extra pagination are allowed.

| Sweep order | Canonical path after `/repos/jiying2007/audio-pipeline` | PR / main |
| ---: | --- | --- |
| 1 | repository itself | both |
| 2 | `/actions/runs/{actual_run_id}/attempts/{actual_run_attempt}` | both |
| 3 | `/commits/{actual_S}/pulls?per_page=100&page=1` | main |
| 4 | `/pulls/{actual_associated_PR_number}` | both |
| 5 | `/issues/845` before | both |
| 6 | `/issues/845/comments?per_page=100&page=1` complete | both |
| 7 | `/issues/comments/{unique_actual_C_comment_id}` | both |
| 8 | `/issues/845` after | both |

The first Jobs route is `/actions/runs/{actual_run_id}/attempts/{actual_run_attempt}/jobs?per_page=100`.
It requires unique job IDs and `0<len(jobs)==total_count<=100`, no next Link,
exactly one registered in-progress F1 name, and actual run/attempt/head/start.
Main association completeness instead uses its full bounded array/no-next proof;
no nonexistent endpoint total count is invented.

All API work is bounded by **5s whole-request wall time**, **60s aggregate**,
**8MiB original control-plane bytes**, the same original900s job and the
collector's180s stage. First Jobs alone precedes collection but consumes aggregate
API/job time and is revalidated inside it. A socket timeout is not a whole-request
proof: an owned bounded Python API worker is monitored by monotonic parent time,
including DNS/TLS/body/encoding/cleanup. At most one first-Jobs worker and one
reused PRE/POST worker are allowed (two metadata-only helper PIDs, zero DSP and
separate from the science/engineering counts). No respawn/retry; late cleanup
rejects. Request records retain ownership and final reap without credentials.

The exact serialized categories are in `control_plane_budget`: their maxima sum
to7,798,784B, leaving589,824B unused within8,388,608B. No category borrows. Stage
control data and all build/measurement/failure bytes remain within the unchanged
32MiB complete-artifact cap. Byte caps apply during reading before JSON parse;
only bounded incomplete prefixes may be preserved on overflow. All endpoints
require canonical authenticated api.github.com GET/200; redirects, anonymous
fallback, cached projections or caller JSON are rejected. Tokens remain outside
compiler/launcher/fixture/science environments.

## Event roles, protected B guard and docs-only activation

For PR: provider PR/head and run/job head are C, base is actual B; checkout and
GITHUB_SHA are test merge M with ordered parents `[B,C]` and full tree(M)=tree(C).
Both head/base repository IDs and exact registered branch/main refs must match.
For main: event/run/job/checkout are S, push-before and sole actual S parent are B,
tree(S)=tree(C), and exactly one complete associated merged PR binds actual head C,
registered branch and merge_commit_sha S. Mutable current PR base data cannot
replace S's immutable sole parent. PRE and POST repeat the source binding.

The expected guard/policy is extracted from actual qualified **B**, with its
commit/tree/blob/byte identity retained. Candidate C cannot remove a protected
path from policy and approve that removal. The standalone guard mode is bounded
local Git/event metadata and standard library only; it invokes no project side
effects, compiler, HTTP, launcher, engineering or DSP processes.

The existing Verify **impact** path invokes the B guard and emits strict
`f1_required`; both **fast-docs and fast-code** invoke it again through the
existing docs gate. Even if the final C changes only baseline/contract/lock/docs,
`f1_required=true` must schedule the existing Quality caller and pass a narrowly
scoped default-false `run_f1` boolean. Only the F1 child uses
`inputs.run_extended OR inputs.run_f1`; unrelated jobs retain their existing
run_extended selection. The caller retains `needs: [impact, fast-gate]` and its
condition requires fast-gate success plus `(run_quality OR f1_required)`.
Summary's `EXPECT_QUALITY` uses that same OR. Quality also exposes the actual
F1 receipt disposition through job/workflow outputs; when f1_required is true,
summary requires the exact complete F1 decision, so an empty/skipped/source-only
result cannot hide behind other successful Quality jobs. Missing output, missing B policy/diff, ambiguous scope or
skipped required F1 outcome fails Verify summary. Fast-docs alone cannot complete
the registered execution obligation.

Other PRs, forks, main changes and workflow_dispatch produce only
`F1_SOURCE_METADATA_ONLY_OUT_OF_SCOPE` after actual B proves protected-source
noninterference. A protected source/authority/guard/route change on an unregistered
event rejects `F1_OUT_OF_SCOPE_PROTECTED_CHANGE` or requires separately reviewed
preregistration. The actual registered execution event with missing freeze fails;
it cannot hide as unrelated. Bootstrap is separately and explicitly zero-process.
For actual C, all three whole hook files are locked. Later unrelated shared-hook
changes may pass a precise structural noninterference proof over F1 inputs,
selection, permissions, invocation, guard and result propagation; uncertainty
rejects. This requires independent protected-source review, not candidate trust.

## Minimal permissions and exact hookup files

GitHub documents [issue-read access](https://docs.github.com/en/rest/issues/issues#get-an-issue),
[comment access](https://docs.github.com/en/rest/issues/comments#list-issue-comments),
[commit-associated PR access](https://docs.github.com/en/rest/commits/commits#list-pull-requests-associated-with-a-commit)
and [reusable-workflow permission limits](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows#nesting-reusable-workflows).
The reviewed caller and F1 child each explicitly declare **contents/packages/
actions/issues/pull-requests: read**. An explicit block must list all five;
omitted capabilities do not inherit from a smaller prior block.

| Existing hookup file | Required bounded change |
| --- | --- |
| `.github/workflows/verify.yml` | Exact five-read block at Quality call only; actual-B impact guard and f1_required output; force caller and pass run_f1; preserve unrelated permissions, existing run_extended and required summary behavior. |
| `.github/workflows/quality.yml` | Default-false run_f1 input and dedicated frontend-rss-f1 job with same pinned image/15min/five-read block; F1 condition run_extended OR run_f1; retain all other jobs/defaults. |
| `.github/scripts/verify-docs-gate.sh` | Bounded actual-B guard on both fast paths, no F1 process. |

There are exactly three pending hookup files plus six pending implementation/test/
build files. No PAT, admin permission, write scope, new secret or unrelated-job
permission increase is requested; existing CodeQL security-events write remains
separate. Action pins and actual final hook routing require independent review.

## Negative inventory and honest execution status

The new machine inventory retains every original174 R1 peer-draft control object
and adds N175..N178 for bootstrap zero-process admission, docs-only forced F1
scheduling, actual-B guard provenance and guarded-B own main closure. These178
are planned single semantic mutations with a passing positive base and exact
expected first violated predicate. In-memory derived transport resealing cannot
alter independently expected pins or peer raw observations. No extra compiler,
HTTP, launcher or DSP is invoked by a metadata negative.

Selectors currently describe logical validator views; `test-contract.json` names
the serialization/raw-parser aliases. Future implementation must supply reviewed
one-to-one entrypoint/selector/reason mappings before final freeze. Unmapped or
generic-exception controls block execution; no inventory padding or silent skip.
Seven separately counted engineering fixtures remain exactly P01..P07, max15
processes including one bounded waited descendant, zero DSP,1s per invocation and
10s aggregate inside180s. Every fixture fixes its work deadline at800ms from the
original launcher-invocation origin and reserves200ms within that same1s for
owned kill/reap and bounded encoding. P04's registered timeout reason occurs at
the800ms work deadline; SIGKILL9/exact wait4/evidence must complete by1s. Late
cleanup is a budget failure, never a passing expected rejection. No clock is
restarted and no enclosing limit grows. They can run only after closed guarded B, final C and
valid live PRE freeze. All178 controls and all7 fixtures are currently
**NOT_IMPLEMENTED_NOT_RUN**.

The first execution decision remains with root after actual prerequisites and
independent review. This draft completes no FE work package, rolling recovery,
public SDK, working-set, whole-stack, heap-peak, physical device or E001 evidence
gap. All shipping/acoustic/device promotion remains false.
