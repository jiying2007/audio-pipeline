# FE09 T3-S3 F1: target lifetime and executable-image RSS observation

## Draft authority / 草案权限

**DRAFT_FOR_REVIEW_NOT_FROZEN — PENDING_F0_MAIN_CLOSURE.**
This directory is a reviewable preregistration draft. No F1 measurement code,
test implementation, binary, fixture execution or DSP/resource result exists
in this tranche. Root authorized drafting only. Root must separately approve
the final contract, implementation scope and first execution. A readable JSON
file, a content hash or this document does not grant execution authority.
Implementation editing and static compilation may later be authorized while F0
main closure is pending. That transition does not authorize invoking an F1
launcher, engineering process fixture or DSP target. All such first execution
still requires the closed predecessor, final reviewed C and external freeze.

The drafting checkout is PR [#844](https://github.com/jiying2007/audio-pipeline/pull/844)
head `5bd8e3dde8809c30b4330ea8b0badf78a40a53ae`, tree
`894253393823d842f620be408ec12339a61771d2`. This is a source anchor, **not an
approved F1 execution baseline**. The actual F0 merged-main commit, its Verify,
required summary, matching Release/convergence and independent original-artifact
readback remain null in `EXECUTION_BASELINE.json`. They must come from real
evidence after F0 main closure; neither the F0 PR head nor its test merge may be
substituted for the future protected-main prerequisite.

The later read-only observation recorded in `EXECUTION_BASELINE.json` sees #844
merged to `92a7546a75cfe0d8aca132c7ee5996dcf0005c74` with the same source tree.
Its own main Verify attempt was still queued when observed; Release/convergence
and main original-artifact closure were not established. That observation is
historical metadata only. The qualified baseline fields remain null and first
execution remains blocked by `PENDING_F0_MAIN_CLOSURE`.

The current scope is exactly five new documentation/metadata files: this README,
`test-contract.json`, `source-lock.json`, `negative-controls.json` and
`EXECUTION_BASELINE.json`. No existing F0, B3, DSP, input, workflow, gate, public
API, shipping default, release identity or historical outcome is modified.

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

`negative-controls.json` contains 139 exact planned negative controls: the original
85 plus 54 freeze/scope/permission/transport controls F1-N086 through F1-N139.
All remain NOT_IMPLEMENTED_NOT_RUN. Metadata mutations
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
15-minute job limit and existing `inputs.run_extended` selection. It does not add
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

## Source closure, pending baseline and non-circular freeze

`source-lock.json` has two deliberately different kinds of rows. Existing F0/B3
source/input/authority rows have real byte counts and hashes from the drafting
commit. Future F1 code and gate-hook rows have null final hashes and explicit
pending states; they are not fake empty files or admitted executable inputs.
Every pending row blocks first execution. The final implementation must establish
the complete compile/link/include/import closure, including generated fixture
source, host launcher, checkpoint observer and separately retained guest image.

The freeze order permits implementation and predecessor closure to progress in
parallel without a self-reference:

1. Root may separately authorize source/test editing, static syntax checks and
   static compilation while D is pending. No produced F1 launcher, fixture or DSP
   executable may run in that state. Static preparatory build products cannot be
   substituted for the registered fresh build from final C.
2. Independently close the real F0 main predecessor **D**. Fill the baseline only
   with observed PR/main run, job, artifact and summary identities. If the final
   protected base **B** is later than D, independently close B's applicable gates
   too and verify that it descends from D and preserves the frozen originals.
3. Finalize all implementation, contract, exact negatives and gate wiring. Fill
   all pending source rows with real bytes. The lock hashes README, contract,
   negatives, baseline and executable inputs, including the future verifier; it
   omits only its own member hash. It contains neither its own digest nor C nor
   a future comment/run/artifact ID. The locked verifier does not embed this lock's
   digest. Pending baseline fields cannot be waived by an approval boolean.
4. Commit the complete reviewed inputs as **C**, with exact protected base B and
   full Git tree. Root independently reviews C and all external freeze digests,
   then posts the strictly typed freeze record specified below. C and its locked
   baseline do not acquire that future comment's ID or hash. Those are runtime
   evidence; a later repository record must be additive and refer back to C.
5. After provider time has moved beyond the freeze comment's timestamp, root may
   open the PR or publish a synchronization that activates CI. For an already-open
   PR, freezing must precede the new push/synchronize event, not merely its first
   creation. The collector checks live PRE authority before builds or any F1
   process, and complete POST authority before success and final sealing. Root's
   independent final readback reacquires the actual provider records.

D's gates precede C's first execution. C's future PR execution cannot qualify D.
The final locked baseline continues to say that it does not independently
authorize execution: it proves prerequisite closure only. Before C is finalized,
root may change the draft protocol state to
`PROTOCOL_REVIEWED_EXTERNAL_COMMENT_REQUIRED_AT_RUNTIME`; the actual selected
comment identity stays a runtime fact, so no final source field needs to predict
it. A source, budget, method, base or full-tree change needs a newly reviewed C and a
new freeze comment; neither an edited comment nor a candidate-supplied CLI value
is an amendment. Source-only preparation is the current state, not evidence that
this ordering has already completed.

## Fixed external freeze authority: issue #845

The control-plane identity was independently read from the actual provider:

| Field | Exact value |
| --- | --- |
| Repository | `jiying2007/audio-pipeline`, REST id `1347377137` |
| Dedicated issue | [#845](https://github.com/jiying2007/audio-pipeline/issues/845) |
| Issue REST / node identity | `6015285792` / `I_kwDOUE9X8c8AAAABZon6IA` |
| Issue created_at | `2026-10-24T16:50:18Z` |
| Author | `jiying2007`, id `33591504`, type `User` |
| Registered head branch | `research/fe09-t3s3-f1-rss-20261024` in the same repository |
| Registered target branch | `main` |
| Science event classes | `pull_request`; the actual protected squash `push` to main |

The machine contract contains the complete JSON Schema for the eventual comment.
It requires exact protocol/version, experiment, repository/issue/author, branch
and event scope, protected B, reviewed C, full tree(C), closed D, the complete
source-lock/contract/baseline/negative byte SHA-256 values, explicit root decision
and review time. Hash fields are patterns and comparison rules in this draft,
not fabricated final identities. The only allowed decision is the registered
F1 PR/main execution approval; the comment cannot override limits, substitute
pending evidence, add a target or promote a result. No valid freeze comment is
asserted by this draft or by the issue's existence.

First derive C from the actual PR/run association or, on main, from the unique
real merged PR of S. A candidate CLI C is not the lookup authority. At PRE and
POST, independently GET the fixed issue, its full comments list using
`per_page=100&page=1` without a `since` filter, the selected comment by exact ID,
and the issue again. Require both issue observations' count to equal the list
length, at most 100, unique positive comment IDs, no next-page Link, correct
canonical endpoints and HTTP 200. Preserve exact response bytes and headers with
bounded request metadata. Both issue observations must retain the fixed identity,
repository, creator and creation time, and must not be a pull request. Issue title,
body and open/closed state are not execution authority or implicit revocation.

Only actual comments from the fixed author can supply authority. Non-JSON
conversation is nonauthoritative. JSON-object comments from that author are
reserved for this freeze protocol and must strictly decode with no duplicate
keys, NaN, coercion, unknown fields or markdown wrapper. Require exactly one valid
record for C, including when duplicates have identical bytes. For that record,
require API `created_at == updated_at`, review time no later than creation, and
creation strictly before the actual Actions run's provider `created_at`. The
run's original creation time is not its rerun/job start time or a locally asserted
time. An equal-second boundary rejects; root waits for a later second before
activating the run. Ordinary untrusted comments never gain authority by copying
the JSON or the trusted user's login string.

POST repeats the **entire** issue/list/uniqueness check, then requires the same
comment ID/node ID, author, issue association, timestamps, original body bytes and
body SHA-256 as PRE. Fetching only the old comment ID would miss a newly inserted
duplicate. Missing, deleted, edited, duplicate, truncated, unreadable or changed
records reject qualification and preserve the attempted cohort. Root's independent
Connector readback repeats the complete check and binds original run/job/artifact
identity; a self-consistent archived response cannot attest its own provider.

These are observations at checkpoints. API timestamps have finite precision;
`created_at == updated_at` and stable PRE/POST bytes do not mathematically prove
that no transient edit ever occurred. The trusted owner must not edit freeze
comments. Root's separate review and final provider readback remain required, and
this protocol makes no cryptographic immutability or hostile-runner guarantee.

## Event scope and the source-only boundary

For the registered PR, require actual provider PR/run association, same repository
ID for head and base, the exact registered head branch, main base, reviewed head C
and protected base B. The test-merge **M** has exact parents `[B, C]` and full
`tree(M) == tree(C)`. Actual checkout/GITHUB_SHA/execution source is M; PR event
head and Actions run/job `head_sha` are C. These roles cannot be interchanged.

For the registered protected main result **S**, read the complete bounded
commit-to-PR association and actual PR detail. Require exactly one matching merged
PR, its original registered branch and head C, `merge_commit_sha == S`, same
repository/main target, sole actual Git parent B, and full `tree(S) == tree(C)`.
Main event/run/job/checkouts all bind S. A mutable live PR base field cannot replace
S's immutable sole parent. An arbitrary same-tree commit or the first item of an
association list is insufficient. Both PRE and POST recheck the binding.

All other PRs, main commits and workflow_dispatch events may perform only
source/metadata checks for this leaf, with zero F1 launchers, engineering processes
or DSP targets and an explicit `F1_SOURCE_METADATA_ONLY_OUT_OF_SCOPE` disposition.
That disposition is not an F1 science PASS. The actual registered branch/event
with absent or bad authority fails; it cannot fall back to source-only. A fork
using the same branch spelling is not the registered same-repository PR.

Before any out-of-scope return, the source guard must compare the actual event's
base/execution diff using the trusted protected-base policy. Changes to the F1
implementation leaves, these five preregistration inputs, its guard or its
invocation/permission/selection/summary route cannot be called unrelated: reject
with `F1_OUT_OF_SCOPE_PROTECTED_CHANGE` or require a separately reviewed new
preregistration. A branch allowlist alone is no waiver. For the first introduction, B has no F1 guard yet: the registered C must receive
independent root review and the external freeze before execution; no nonexistent
base policy is claimed. That bootstrap supplies source/metadata checks only.
After integration, the actual protected-base guard is the comparison authority.
The guard runs in the
existing docs gate on both fast-docs and fast-code paths, even when Quality's
`run_extended` job is not selected. If the required diff, base policy or scope
proof is unavailable or ambiguous, reject rather than assume unrelated.

Whole hookup files are source-locked for C's actual execution. For later unrelated
maintenance, an exact structural proof may show that the F1 job, caller permissions,
inputs/selection, summary route and docs-gate invocation/dependency closure did not
change; unrelated CodeQL or other job edits need not freeze all repository work.
If that bounded proof cannot exclude an F1 effect, fail the source check. Candidate
changes cannot redefine the protected path set or guard to approve themselves;
independent protected-source review remains part of the acceptance boundary.

The freeze approves source/event scope, not a successful result or automatic retry.
Every provider run/attempt is retained as a separate cohort. The collector never
retries, replaces or combines attempts. Any later manual re-execution requires a
separate explicit root decision; unchanged C may retain its same source freeze,
whose time still must precede that run's original creation. This draft does not
create a retry or scheduled execution facility.

## Minimal read permissions and hookup scope

For the chosen authenticated endpoints, GitHub documents
[issues-read for Get an issue](https://docs.github.com/en/rest/issues/issues#get-an-issue),
[either issues-read or pull-requests-read for comments](https://docs.github.com/en/rest/issues/comments#list-issue-comments),
and [pull-requests-read for commit-to-PR association](https://docs.github.com/en/rest/commits/commits#list-pull-requests-associated-with-a-commit).
Reusable calls [cannot elevate the caller's permissions](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows#nesting-reusable-workflows).
An explicit permissions block sets omitted permissions to none, so all five
required read capabilities must be listed together at these two locations:

| Future existing-file hookup | Exact bounded purpose |
| --- | --- |
| `.github/workflows/verify.yml` | Only the `quality` reusable-call job gains an explicit contents/packages/actions/issues/pull-requests read block. Preserve top-level permissions, CodeQL's separate security-events write block, call inputs and summary behavior. |
| `.github/workflows/quality.yml` | Add the dedicated F1 job with the same explicit five read capabilities, provider binding and preregistered collector. Keep workflow-level and all other jobs' existing three read permissions. |
| `.github/scripts/verify-docs-gate.sh` | Add bounded source/JSON/scope validation on both existing fast paths; no F1 launcher, process fixture or DSP invocation. |

There are **three** pending hookup files, in addition to six pending F1
implementation/test/build files. No PAT, administration permission, write scope,
repository secret or permissions increase to unrelated jobs is requested. The
read token remains only in bounded API acquisition and is removed from all build,
launcher, target and fixture child environments. Authenticated requests are fixed
to api.github.com, require 200 and do not follow cross-host redirects or fall back
to anonymous data, cached snapshots or caller-supplied JSON as live authority.

External-control bytes are stage-level evidence, outside the per-case 64 KiB
partition but inside the unchanged 32 MiB artifact. The contract allocates at most
8 MiB to all original Jobs/run/PR/issue/comment API responses and bounded request
records. At most 17 requests include the first-step Jobs observation plus two
complete PRE/POST sweeps. Acquisition has a five-second per-request cap and a
60-second aggregate cap, both bounded by remaining original job/stage time; no
API retries or pagination search extends either clock. PRE/POST acquisition,
metadata negatives, readback, cleanup and final seal consume the same 180-second
collector window, except the original first-step Jobs request which consumes the
same original 900-second job and is retained/validated inside collection. POST
cannot spend the 60-second archive reserve to turn a late result into success.
The category maxima sum to 7,798,784 B, leaving 589,824 B unused inside the
8,388,608 B control-plane cap; categories cannot borrow from one another. All
request records omit Authorization, cookies and private environment values. The
exact serialized partition and overflow refusal are in the machine contract.

The first-execution decision remains with root after actual prerequisite closure
and independent review. This draft closes no FE work package, rolling-recovery,
public SDK, working-set, whole-stack, heap-peak, device or E001 evidence gap.
