#!/bin/sh
# One offline documentation/assurance gate for docs-only and full verification.
# I010 is terminal: validate the current registry, never require retired live inputs.
set -eu

# F1_R1_SOURCE_SCOPE_GUARD_BEGIN
# Actual protected-B bytes; local Git/event only, no execution authority.
if [ "${1:-}" != --a3-scope-only ]; then
# This entry decides routing only and never acquires provider execution authority.
if [ -n "${GITHUB_EVENT_NAME:-}" ]; then
  python3 - <<'PY'
import json, os, pathlib, subprocess, sys, tempfile, time
entry_started_monotonic_ns = time.monotonic_ns()
# F1_R1_LOCAL_GIT_READER_BEGIN
import selectors
import signal

LOCAL_METADATA_DEADLINE_NS = None


class LocalMetadataReadError(RuntimeError):
    def __init__(self, reason, observation=None):
        self.reason = reason
        self.observation = observation or {}
        super().__init__(reason)


def local_metadata_environment(source=None):
    """No inherited Git overrides, credentials, protocol or demand fetching."""
    source = os.environ if source is None else source
    env = {key: value for key, value in source.items()
           if not key.startswith('GIT_') and key not in ('GH_TOKEN', 'GITHUB_TOKEN')}
    env.update(GIT_ALLOW_PROTOCOL='', GIT_NO_LAZY_FETCH='1',
               GIT_NO_REPLACE_OBJECTS='1', GIT_OPTIONAL_LOCKS='0',
               GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_SYSTEM='/dev/null', GIT_CONFIG_GLOBAL='/dev/null',
               GIT_LITERAL_PATHSPECS='1')
    return env


def local_git_argv(root, args):
    if not args or args[0] not in ('show', 'rev-parse', 'cat-file', 'ls-tree', 'diff'):
        raise LocalMetadataReadError('F1R1_SOURCE_GIT_COMMAND_NOT_READ_ONLY')
    if args[0] == 'diff' and not all(flag in args for flag in
                                  ('--no-renames', '--no-ext-diff', '--no-textconv')):
        raise LocalMetadataReadError('F1R1_COMPLETE_LOCAL_DIFF_REQUIRED')
    return ['git', '--no-pager', '--no-lazy-fetch', '--no-replace-objects',
            '-c', 'safe.directory=' + str(root), '-c', 'protocol.allow=never',
            '-c', 'core.fsmonitor=false', '-C', str(root), *args]


def local_metadata_deadlines(start_ns, duration_ns=5_000_000_000):
    # Save the admitted integer duration. Never reconstruct it by subtracting
    # large floating point timestamps. Cleanup is inside the same total limit.
    if type(start_ns) is not int or type(duration_ns) is not int or duration_ns < 500_000_001:
        raise LocalMetadataReadError('F1R1_SOURCE_METADATA_DEADLINE')
    return {'started_monotonic_ns': start_ns, 'admitted_duration_ns': duration_ns,
            'work_deadline_monotonic_ns': start_ns + duration_ns - 500_000_000,
            'final_deadline_monotonic_ns': start_ns + duration_ns}


def bounded_metadata_append(buffer, chunk, cap):
    # The sentinel byte is observed but is never retained in the bounded buffer.
    if len(buffer) + len(chunk) > cap:
        raise LocalMetadataReadError('F1R1_SOURCE_METADATA_BYTES_LIMIT')
    buffer.extend(chunk)


def bounded_local_command(argv, *, env, stdout_cap, stderr_cap=65536,
                          duration_ns=5_000_000_000):
    """Drain before cap, then kill/reap within one original monotonic deadline.

    A new session is owned by this call. The leader is not polled/reaped before
    an exceptional group kill, so its PID cannot be recycled before that kill.
    Late or unreaped cleanup is rejection, never a successful bounded read.
    """
    if any(type(cap) is not int or cap < 0 for cap in (stdout_cap, stderr_cap)):
        raise LocalMetadataReadError('F1R1_SOURCE_METADATA_BYTES_LIMIT')
    clock = local_metadata_deadlines(time.monotonic_ns(), duration_ns)
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    selector = selectors.DefaultSelector()
    process = None
    failure = None
    reaped = False
    returncode = None
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=env, close_fds=True, start_new_session=True)
        for stream, name, cap in ((process.stdout, 'stdout', stdout_cap),
                                  (process.stderr, 'stderr', stderr_cap)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, (name, cap))
        while selector.get_map():
            remaining = clock['work_deadline_monotonic_ns'] - time.monotonic_ns()
            if remaining <= 0:
                raise LocalMetadataReadError('F1R1_SOURCE_METADATA_DEADLINE')
            for key, unused_mask in selector.select(remaining / 1_000_000_000):
                name, cap = key.data
                try:
                    chunk = os.read(key.fileobj.fileno(), min(65536, cap - len(buffers[name]) + 1))
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                bounded_metadata_append(buffers[name], chunk, cap)
        remaining = clock['work_deadline_monotonic_ns'] - time.monotonic_ns()
        if remaining <= 0:
            raise LocalMetadataReadError('F1R1_SOURCE_METADATA_DEADLINE')
        returncode = process.wait(timeout=remaining / 1_000_000_000)
        reaped = True
    except LocalMetadataReadError as exc:
        failure = exc.reason
    except subprocess.TimeoutExpired:
        failure = 'F1R1_SOURCE_METADATA_DEADLINE'
    except (OSError, ValueError):
        failure = 'F1R1_SOURCE_GIT_READ_FAILED'
    finally:
        # No communicate(), unbounded read(), implicit context-manager wait(),
        # retry, or new cleanup deadline is allowed here.
        if process is not None and not reaped:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                failure = failure or 'F1R1_SOURCE_METADATA_REAP_FAILED'
            remaining = clock['final_deadline_monotonic_ns'] - time.monotonic_ns()
            if remaining > 0:
                try:
                    returncode = process.wait(timeout=remaining / 1_000_000_000)
                    reaped = True
                except subprocess.TimeoutExpired:
                    failure = failure or 'F1R1_SOURCE_METADATA_REAP_FAILED'
            else:
                failure = failure or 'F1R1_SOURCE_METADATA_DEADLINE'
        selector.close()
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
    stdout, stderr = bytes(buffers['stdout']), bytes(buffers['stderr'])
    finished = time.monotonic_ns()
    observation = {**clock, 'finished_monotonic_ns': finished,
                   'elapsed_ns': finished - clock['started_monotonic_ns'],
                   'owned_process_reaped': reaped, 'returncode': returncode,
                   'stdout_bytes_retained': len(buffers['stdout']),
                   'stderr_bytes_retained': len(buffers['stderr'])}
    if finished > clock['final_deadline_monotonic_ns'] or not reaped:
        failure = failure or 'F1R1_SOURCE_METADATA_DEADLINE'
    if failure:
        raise LocalMetadataReadError(failure, observation)
    return stdout, stderr, observation


def local_git_read(root, args, *, cap=2097152):
    duration = 5_000_000_000
    if LOCAL_METADATA_DEADLINE_NS is not None:
        duration = min(duration, LOCAL_METADATA_DEADLINE_NS - time.monotonic_ns())
    return bounded_local_command(local_git_argv(root, args),
                                 env=local_metadata_environment(), stdout_cap=cap,
                                 duration_ns=duration)
# F1_R1_LOCAL_GIT_READER_END

LOCAL_METADATA_DEADLINE_NS = entry_started_monotonic_ns + 59_000_000_000
root = pathlib.Path.cwd().resolve()
source = 'tests/validation/frontend_evolution/fe09_t3s3_f1_rss_qualification.py'
event_path = os.environ.get('GITHUB_EVENT_PATH', '')
if not event_path:
    raise SystemExit('F1R1_ACTUAL_EVENT_REQUIRED')
with pathlib.Path(event_path).open('rb') as event_stream:
    raw = event_stream.read(2097153)
if len(raw) > 2097152:
    raise SystemExit('F1R1_EVENT_BYTES_LIMIT')
event = json.loads(raw)
env = local_metadata_environment()
env['FE_F1_SOURCE_METADATA_DEADLINE_NS'] = str(LOCAL_METADATA_DEADLINE_NS)
def git(*args):
    stdout, unused_stderr, observation = local_git_read(root, args)
    if observation['returncode'] != 0:
        raise SystemExit('F1R1_SOURCE_GIT_READ_FAILED')
    return stdout
parents = git('show', '-s', '--format=%P', 'HEAD').decode().split()
kind = os.environ['GITHUB_EVENT_NAME']
if kind == 'pull_request':
    base = event['pull_request']['base']['sha']
elif kind == 'push':
    base = event['before']
elif kind == 'workflow_dispatch' and len(parents) == 1:
    base = parents[0]
else:
    raise SystemExit('F1R1_SOURCE_RANGE_REQUIRED')
if len(base) != 40 or any(c not in '0123456789abcdef' for c in base) or base == '0' * 40:
    raise SystemExit('F1R1_SOURCE_OID_REQUIRED')
git('cat-file', '-e', base + '^{commit}')
member = git('ls-tree', base, '--', source)
output = pathlib.Path(os.environ.get('FE_F1_SCOPE_RECEIPT', os.environ.get('RUNNER_TEMP', '/tmp') + '/f1-source-scope.json'))
with tempfile.TemporaryDirectory(prefix='f1-protected-guard-', dir=os.environ.get('RUNNER_TEMP', '/tmp')) as tmp:
    if member:
        if not member.startswith(b'100644 blob '):
            raise SystemExit('F1R1_SOURCE_FILE_MODE')
        size = int(git('cat-file', '-s', base + ':' + source))
        if size > 2097152:
            raise SystemExit('F1R1_SOURCE_METADATA_BYTES_LIMIT')
        guard = pathlib.Path(tmp) / 'protected_f1_guard.py'
        guard.write_bytes(git('show', base + ':' + source))
        origin = ['--guard-origin', base]
    else:
        # First introduction has no B guard. Candidate bootstrap code can only
        # emit zero-process SOURCE_METADATA_ONLY; independent root review owns it.
        guard = root / source
        origin = []
    argv = [sys.executable, str(guard), 'source-guard', '--root', str(root),
            '--event', event_path, '--event-name', kind, '--output', str(output)] + origin
    if os.environ.get('GITHUB_OUTPUT'):
        argv += ['--github-output', os.environ['GITHUB_OUTPUT']]
    stdout, stderr, observation = bounded_local_command(
        argv, env=env, stdout_cap=65536,
        duration_ns=entry_started_monotonic_ns + 60_000_000_000 - time.monotonic_ns())
    if stdout:
        sys.stdout.buffer.write(stdout)
    if stderr:
        sys.stderr.buffer.write(stderr)
    if observation['returncode'] != 0:
        raise SystemExit('F1R1_PROTECTED_SOURCE_GUARD_REJECTED')
PY
elif [ "${GITHUB_ACTIONS:-false}" = true ]; then
  echo 'F1R1_ACTUAL_EVENT_REQUIRED' >&2
  exit 1
fi
if [ "${1:-}" = --f1-scope-only ]; then
  exit 0
fi
python3 tests/validation/frontend_evolution/test_fe09_t3s3_f1_rss_qualification.py
fi
# F1_R1_SOURCE_SCOPE_GUARD_END

python3 tests/validation/frontend_evolution/test_contracts.py
python3 scripts/ci_impact.py --self-test
python3 tests/validation/test_immutable_whitespace.py
python3 tests/validation/frontend_evolution/test_device_capture.py
python3 scripts/github_governance.py --self-test
python3 scripts/resource_baseline.py --self-test
python3 scripts/docs_consistency.py --self-test
python3 tests/test_ci_evidence_transport.py
python3 scripts/research_registry.py --self-test
python3 scripts/prepare_release.py --self-test
python3 scripts/release_manifest.py --self-test
python3 scripts/post_release_status.py --self-test
python3 scripts/qualification_fingerprint.py --self-test
python3 .github/research/continuous-optimization/hosted-validation/public_candidate_pair.py --source-root . --self-test
python3 .github/program/acoustic_terminal_registry.py --self-test
python3 .github/program/acoustic_terminal_registry.py --check
python3 tests/validation/i010_ns_vad_observation.py --self-test
python3 tests/validation/i010_apply_vad_pre_ns_candidate.py --self-test
python3 tests/validation/i010_vad_pre_ns_candidate.py --self-test
python3 .github/research/continuous-optimization/source_candidate_authority_v2.py --self-test
python3 .github/research/continuous-optimization/source_candidate_execution_v2_contract.py --self-test --check
python3 -m json.tool .github/research/evidence-index.json >/dev/null
python3 -m json.tool .github/research/qualification-policy.json >/dev/null
python3 scripts/docs_consistency.py
python3 tests/validation/frontend_evolution/test_libfvad_reference.py
python3 tests/validation/frontend_evolution/array_qualification.py --self-test
python3 tests/validation/frontend_evolution/test_speech_spatial.py
python3 tests/validation/frontend_evolution/doa_observability_a0.py --self-test
python3 tests/validation/frontend_evolution/doa_gccphat_a1.py --self-test
python3 tests/validation/frontend_evolution/realman_source_metadata_d0.py --self-test
python3 tests/validation/frontend_evolution/realman_val_csv_d1.py self-test
python3 tests/validation/frontend_evolution/realman_scene_tree_d2_s0.py self-test
python3 tests/validation/frontend_evolution/realman_single_archive_d2_s1.py self-test
python3 tests/validation/frontend_evolution/realman_flac_quartets_d2_s2.py self-test
python3 tests/validation/frontend_evolution/realman_flac_decoder_toolchain_d2_t0.py self-test
python3 tests/validation/frontend_evolution/realman_pcm_reference_d2_s3r.py self-test
python3 tests/validation/frontend_evolution/realman_timebase_authority_d2_s4.py self-test
python3 tests/validation/frontend_evolution/realman_pypdf_toolchain_d2_s5_t0.py self-test
python3 tests/validation/frontend_evolution/realman_paper_clock_witness_d2_s5r.py self-test
python3 tests/validation/frontend_evolution/realman_gym_lag_diagnostic_d2_s6.py self-test
python3 tests/validation/frontend_evolution/fe09_array_abi_contract_r1.py --self-test
python3 tests/validation/frontend_evolution/fe09_array_abi_contract_r1.py --check
# Bind the reviewed patch-maintenance bytes, then run both original preflights
# and their negatives on exact reconstructed historical source copies.
python3 tests/validation/frontend_evolution/fe09_runtime_maintenance_rebind.py --self-test --check
python3 tests/validation/frontend_evolution/fe09_b1a_ingress_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b1b0_src_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b1b1_single_bf_qualification.py --self-test
# Preserve six original scientific self-tests and verify the versioned
# historical/current source boundary plus its independent receipt negatives.
python3 tests/validation/frontend_evolution/fe09_runtime_source_boundary.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b0_capture_only_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b1s0_owner_spsc_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b1s1_source_chunks_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2c0_quiescent_fallback_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s0_resource_census_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s1_compact_handoff_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2a_atomic_spool_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b0_manifest_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1a_immutable_root_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1bf0_seq17_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1ba1_anchor_root_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1ba2_finite_retirement_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_t3s3_f0_call_resource_qualification.py --self-test
python3 tests/validation/frontend_evolution/test_fe09_same_run_artifact_visibility.py
python3 tests/validation/frontend_evolution/test_speech_download_retry.py
python3 tests/validation/frontend_evolution/test_speech_source_stage_budget.py
python3 tests/validation/frontend_evolution/test_speech_source_recovery.py
python3 tests/validation/frontend_evolution/speech_pinned_snapshot.py --self-test
python3 .github/program/workflow_pin_only_scope.py --self-test
python3 .github/program/workflow_pin_only_replay_t1.py --self-test
python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --self-test
python3 .github/program/workflow_pin_pr_consumer.py --self-test
python3 .github/program/test_dechorate_event_source_t1m3.py --self-test
# Live GitHub bot Git-object probe only when this very qualifier is modified
# in a PR. Avoid an external network dependency for unrelated Verify runs.
if [ "${GITHUB_EVENT_NAME:-}" = pull_request ]; then
  test "${GITHUB_BASE_REF:-}" = main
  # A pull_request checkout may expose only refs/pull/<n>/merge, not origin/main.
  # Its first immutable parent is the checked-out protected PR base tree.
  set -- $(git -c "safe.directory=$PWD" rev-list --parents -n 1 HEAD)
  test "$#" -eq 3
  case "$2" in
    *[!0123456789abcdef]*|'') echo 'M1_PR_BASE_OID_MALFORMED' >&2; exit 1 ;;
  esac
  test "${#2}" -eq 40
  changed_t1m1=$(git -c "safe.directory=$PWD" diff --name-only "$2...HEAD" -- \
    .github/program/workflow_pin_only_actual_tree_t1m1.py)
  if [ "$changed_t1m1" = .github/program/workflow_pin_only_actual_tree_t1m1.py ]; then
    python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --probe-real --review 2026-10-20
  fi
fi
