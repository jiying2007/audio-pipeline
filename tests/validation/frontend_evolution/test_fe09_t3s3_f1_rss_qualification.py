#!/usr/bin/env python3
"""Pure in-process F1 bootstrap/scheduling controls; no process or HTTP fixtures.

These tests establish only metadata predicates. They do not claim execution of
the planned178 full-evidence negatives or any real launcher/HTTP lifecycle.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE = Path(__file__).with_name("fe09_t3s3_f1_rss_qualification.py")
SPEC = importlib.util.spec_from_file_location("fe09_f1_metadata", MODULE)
F1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F1)
B, C, M = "1" * 40, "2" * 40, "3" * 40


def pr_event(branch=F1.REGISTERED_BRANCH):
    return {"repository": {"id": F1.REPOSITORY_ID, "full_name": F1.REPOSITORY},
            "pull_request": {"head": {"sha": C, "ref": branch,
                                      "repo": {"id": F1.REPOSITORY_ID}},
                             "base": {"sha": B, "ref": "main",
                                      "repo": {"id": F1.REPOSITORY_ID}}}}


def routing():
    paths = ["frozen/original.c", F1.SOURCE]
    return {"candidate_protected_paths": paths[:], "protected_B_paths": paths[:],
            "fast_docs": ["F1_R1_SOURCE_SCOPE_GUARD"],
            "fast_code": ["F1_R1_SOURCE_SCOPE_GUARD"],
            "caller_permissions": dict(F1.FIVE_READ),
            "child_permissions": dict(F1.FIVE_READ),
            "top_permissions": dict.fromkeys(("contents", "packages", "actions"), "read"),
            "continue_on_error": False, "guard_source": B, "B": B,
            "B_main_closed": True, "bootstrap_launchers": 0,
            "docs_only_execution_C": True, "f1_required": True,
            "caller_called": True, "run_f1": True, "child_selected": True,
            "summary_expect_quality": True, "summary_checks_disposition": True}


class MetadataTests(unittest.TestCase):
    def reject(self, reason, callback, *args, **kwargs):
        with self.assertRaises(F1.Rejected) as error:
            callback(*args, **kwargs)
        self.assertEqual(error.exception.reason, reason)

    def test_bootstrap_execution_gate_is_false(self):
        self.assertIs(F1.SCIENCE_EXECUTION_ENABLED, False)

    def test_strict_json_positive(self):
        self.assertEqual(F1.strict_json(b'{"a":1}'), {"a": 1})

    def test_duplicate_keys_rejected(self):
        self.reject("F1R1_DUPLICATE_JSON_KEY", F1.strict_json, b'{"a":1,"a":2}')

    def test_nonfinite_rejected(self):
        self.reject("F1R1_NONFINITE_NUMBER", F1.strict_json, b'{"a":NaN}')

    def test_size_before_parse(self):
        self.reject("F1R1_SERIALIZED_BYTES_LIMIT", F1.strict_json, b'x' * 257, 256)

    def test_booleans_not_numbers(self):
        self.assertFalse(F1.integer(True))
        self.assertFalse(F1.finite(False))
        self.assertTrue(F1.integer(0))

    def test_actual_PR_role_positive(self):
        roles = F1.parse_event("pull_request", pr_event(), M, [B, C])
        self.assertEqual((roles["B"], roles["C"], roles["checkout"]), (B, C, M))
        self.assertFalse(roles["provider_merged_PR_authority"])

    def test_PR_parents_reversed(self):
        self.reject("F1R1_EXACT_PR_MERGE_PARENTS", F1.parse_event,
                    "pull_request", pr_event(), M, [C, B])

    def test_main_immutable_parent(self):
        event = {"repository": pr_event()["repository"], "ref": "refs/heads/main",
                 "before": B, "after": M}
        self.assertEqual(F1.parse_event("push", event, M, [B])["B"], B)
        self.reject("F1R1_IMMUTABLE_MAIN_PARENT_B", F1.parse_event,
                    "push", event, M, [C])

    def test_fork_spelling_not_registered(self):
        event = pr_event()
        event["pull_request"]["head"]["repo"]["id"] += 1
        self.assertFalse(F1.parse_event("pull_request", event, M, [B, C])["registered_candidate"])

    def scope(self, *, registered=True, guard=True, ready=True, changed=True, origin=B):
        roles = F1.parse_event("pull_request", pr_event(F1.REGISTERED_BRANCH if registered else "unrelated"), M, [B, C])
        return F1.evaluate_scope(event=roles, changed={F1.REG + "/EXECUTION_BASELINE.json"} if changed else set(),
                                 protected={F1.REG + "/EXECUTION_BASELINE.json"},
                                 base_guard_present=guard, guard_origin=origin,
                                 execution_ready=ready)

    def test_bootstrap_zero_process_disposition(self):
        result = self.scope(guard=False, ready=False, origin=None)
        self.assertEqual(result["disposition"], F1.SOURCE_ONLY)
        self.assertFalse(result["f1_required"])

    def test_bootstrap_invented_guard(self):
        self.reject("F1R1_BOOTSTRAP_METADATA_ONLY", self.scope, guard=False, ready=False)

    def test_bootstrap_execution_attempt(self):
        self.reject("F1R1_BOOTSTRAP_ZERO_F1_PROCESSES", self.scope, guard=False, origin=None)

    def test_candidate_is_not_protected_guard(self):
        self.reject("F1R1_ACTUAL_PROTECTED_B_GUARD_REQUIRED", self.scope, origin=C)

    def test_docs_only_final_C_forces_real_job(self):
        result = self.scope()
        self.assertTrue(result["f1_required"])
        self.assertEqual(result["disposition"], "F1_PROVIDER_ADMISSION_REQUIRED")

    def test_unrelated_protected_change_rejected(self):
        self.reject("F1_OUT_OF_SCOPE_PROTECTED_CHANGE", self.scope, registered=False)

    def test_unrelated_proven_no_change_source_only(self):
        result = self.scope(registered=False, changed=False)
        self.assertEqual(result["disposition"], F1.OUT_OF_SCOPE)
        self.assertFalse(result["f1_required"])

    def test_routing_positive(self):
        F1.validate_routing(routing())

    def mutation(self, key, value, reason):
        positive = routing()
        F1.validate_routing(positive)
        bad = copy.deepcopy(positive)
        bad[key] = value
        self.reject(reason, F1.validate_routing, bad)

    def test_candidate_pathset_cannot_approve_removal(self):
        self.mutation("candidate_protected_paths", [F1.SOURCE], "F1R1_PROTECTED_BASE_POLICY_REQUIRED")

    def test_fast_docs_call_required(self):
        self.mutation("fast_docs", [], "F1R1_GUARD_REQUIRED_ON_FAST_DOCS")

    def test_fast_code_call_required(self):
        self.mutation("fast_code", [], "F1R1_GUARD_REQUIRED_ON_FAST_CODE")

    def test_caller_all_five_reads(self):
        bad = dict(F1.FIVE_READ)
        del bad["issues"]
        self.mutation("caller_permissions", bad, "F1R1_FIVE_READ_CALLER_PERMISSIONS")

    def test_child_all_five_reads(self):
        bad = dict(F1.FIVE_READ)
        del bad["actions"]
        self.mutation("child_permissions", bad, "F1R1_FIVE_READ_CHILD_PERMISSIONS")

    def test_no_top_scope_expansion(self):
        self.mutation("top_permissions", dict(F1.FIVE_READ), "F1R1_PERMISSION_CHANGE_SCOPE")

    def test_no_ignored_F1_failure(self):
        self.mutation("continue_on_error", True, "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION")

    def test_actual_B_guard_source(self):
        self.mutation("guard_source", C, "F1R1_ACTUAL_PROTECTED_B_GUARD_REQUIRED")

    def test_guarded_B_must_close_own_main(self):
        self.mutation("B_main_closed", False, "F1R1_PROTECTED_GUARD_BASE_CLOSURE_REQUIRED")

    def test_bootstrap_no_launcher(self):
        self.mutation("bootstrap_launchers", 1, "F1R1_BOOTSTRAP_ZERO_F1_PROCESSES")

    def test_each_docs_dispatch_link_required(self):
        for key in ("f1_required", "caller_called", "run_f1", "child_selected",
                    "summary_expect_quality", "summary_checks_disposition"):
            with self.subTest(link=key):
                self.mutation(key, False, "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1")

    def test_shared_hook_projection_is_conservative(self):
        raw = b'name: Quality\n\njobs:\n  frontend-rss-f1:\n    run: source-only\n  other:\n    run: a\n'
        changed = raw.replace(b'run: a', b'run: b')
        self.assertEqual(F1.workflow_projection(raw, "quality"), F1.workflow_projection(changed, "quality"))
        touched = raw.replace(b'run: source-only', b'run: no-guard')
        self.assertNotEqual(F1.workflow_projection(raw, "quality"), F1.workflow_projection(touched, "quality"))

    def test_duplicate_workflow_job_rejected(self):
        raw = b'jobs:\n  frontend-rss-f1:\n    run: x\n  frontend-rss-f1:\n    run: y\n'
        self.reject("F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED", F1.workflow_projection, raw, "quality")

    # F1-G01..G15 were fixed in the review-check plan before implementation.
    # These are pure source/metadata controls, not the registered 178 execution
    # negatives and not real timeout, HTTP, launcher or engineering fixtures.
    def test_f1_g01_inherited_git_environment_cannot_enable_transport(self):
        source = {'PATH': '/usr/bin', 'GITHUB_EVENT_PATH': '/event.json',
                  'GITHUB_TOKEN': 'synthetic-only', 'GH_TOKEN': 'synthetic-only',
                  'GIT_CONFIG_PARAMETERS': "'protocol.allow=always'",
                  'GIT_ALLOW_PROTOCOL': 'https:file:ssh', 'GIT_NO_LAZY_FETCH': '0',
                  'GIT_OBJECT_DIRECTORY': '/candidate', 'GIT_TRACE': '/candidate'}
        env = F1.local_metadata_environment(source)
        self.assertEqual(env['GIT_ALLOW_PROTOCOL'], '')
        self.assertEqual(env['GIT_NO_LAZY_FETCH'], '1')
        self.assertEqual(env['GIT_NO_REPLACE_OBJECTS'], '1')
        self.assertEqual(env['GIT_CONFIG_GLOBAL'], '/dev/null')
        self.assertEqual(env['GIT_CONFIG_SYSTEM'], '/dev/null')
        for key in ('GH_TOKEN', 'GITHUB_TOKEN', 'GIT_CONFIG_PARAMETERS', 'GIT_OBJECT_DIRECTORY', 'GIT_TRACE'):
            self.assertNotIn(key, env)
        self.assertEqual(env['GITHUB_EVENT_PATH'], '/event.json')

    def test_f1_g02_only_complete_local_readonly_diff_argv(self):
        argv = F1.local_git_argv('/source', ('diff', '--raw', '-z', '--no-abbrev',
                                           '--no-renames', '--no-ext-diff', '--no-textconv', B, C, '--'))
        for token in ('--no-pager', '--no-lazy-fetch', '--no-replace-objects', 'protocol.allow=never'):
            self.assertIn(token, argv)
        for args in (('fetch',), ('diff', '--name-only', B, C),
                     ('diff', '--no-renames', '--no-ext-diff', B, C)):
            with self.subTest(args=args), self.assertRaises(F1.LocalMetadataReadError):
                F1.local_git_argv('/source', args)

    def test_f1_g03_both_streams_reject_before_buffer_overflow(self):
        for cap in (4, 65536):
            with self.subTest(cap=cap):
                retained = bytearray(b'x' * cap)
                with self.assertRaises(F1.LocalMetadataReadError) as error:
                    F1.bounded_metadata_append(retained, b'y', cap)
                self.assertEqual(error.exception.reason, 'F1R1_SOURCE_METADATA_BYTES_LIMIT')
                self.assertEqual(retained, b'x' * cap)
                F1.bounded_metadata_append(retained, b'', cap)

    def test_f1_g04_integer_five_seconds_includes_reserved_cleanup(self):
        start = 9_876_543_210_123_456
        row = F1.local_metadata_deadlines(start)
        self.assertEqual(row['admitted_duration_ns'], 5_000_000_000)
        self.assertEqual(row['work_deadline_monotonic_ns'], start + 4_500_000_000)
        self.assertEqual(row['final_deadline_monotonic_ns'], start + 5_000_000_000)
        # The entry's original deadline can shorten a later Git read, never
        # create a fresh five-second window beyond the owner lifetime.
        with patch.object(F1, 'LOCAL_METADATA_DEADLINE_NS', start + 3_000_000_000), \
             patch.object(F1.time, 'monotonic_ns', return_value=start), \
             patch.object(F1, 'bounded_local_command', return_value=(b'', b'', {})) as command:
            F1.local_git_read('/source', ('cat-file', '-e', B))
            self.assertEqual(command.call_args.kwargs['duration_ns'], 3_000_000_000)
        for duration in (True, 0, 500_000_000, 5.0):
            with self.subTest(duration=duration), self.assertRaises(F1.LocalMetadataReadError):
                F1.local_metadata_deadlines(start, duration)

    def test_f1_g05_missing_object_never_becomes_a_fetch_or_approval(self):
        observation = {'returncode': 128}
        with patch.object(F1, 'local_git_read', return_value=(b'', b'missing', observation)) as reader:
            self.reject('F1R1_SOURCE_GIT_READ_FAILED', F1.git, Path('/source'), 'show', B + ':missing')
            reader.assert_called_once()
        # A missing blob beneath an existing tree entry is not bootstrap absence.
        with patch.object(F1, 'git', side_effect=[None, b'', b'100644 blob ' + C.encode() + b'\tmissing\n']):
            self.reject('F1R1_SOURCE_GIT_READ_FAILED', F1.object_bytes,
                        Path('/source'), B, 'missing', missing=True)

    def test_f1_g06_no_renames_keeps_both_old_and_new_paths(self):
        raw = (f':100644 000000 {B} {"0" * 40} D\0protected/old.c\0'
               f':000000 100644 {"0" * 40} {B} A\0elsewhere/new.c\0').encode()
        rows = F1.parse_raw_diff(raw)
        self.assertEqual([(row['path'], row['status']) for row in rows],
                         [('protected/old.c', 'D'), ('elsewhere/new.c', 'A')])
        self.assertIn('protected/old.c', {row['path'] for row in rows})

    def test_f1_g07_raw_diff_preserves_and_validates_mode_type(self):
        raw = f':100644 120000 {B} {C} T\0guard.py\0'.encode()
        self.assertEqual(F1.parse_raw_diff(raw)[0]['new_mode'], '120000')
        executable = f':100644 100755 {B} {C} M\0guard.py\0'.encode()
        self.assertEqual(F1.parse_raw_diff(executable)[0]['old_mode'], '100644')
        for bad in (raw.replace(b' T\0', b' M\0'), raw.replace(b' T\0', b' R100\0'),
                    raw.replace(b'120000', b'999999'), raw[:-1], raw + raw):
            with self.subTest(raw=bad[:40]):
                self.reject('F1R1_COMPLETE_LOCAL_DIFF_REQUIRED', F1.parse_raw_diff, bad)

    def test_f1_g08_existing_B_guard_rejects_unready_PR_and_main(self):
        roles = [F1.parse_event('pull_request', pr_event(), M, [B, C]),
                 F1.parse_event('push', {'repository': pr_event()['repository'],
                                        'ref': 'refs/heads/main', 'before': B, 'after': M}, M, [B])]
        for event in roles:
            with self.subTest(event=event['event']):
                kwargs = dict(event=event, changed={F1.SOURCE}, protected={F1.SOURCE}, execution_ready=False)
                self.reject('F1_OUT_OF_SCOPE_PROTECTED_CHANGE', F1.evaluate_scope,
                            **kwargs, base_guard_present=True, guard_origin=B)
                bootstrap = F1.evaluate_scope(**kwargs, base_guard_present=False, guard_origin=None)
                self.assertEqual(bootstrap['disposition'], F1.SOURCE_ONLY)
                self.assertFalse(bootstrap['f1_required'])

    def test_f1_g09_ready_docs_PR_and_main_both_force_provider_job(self):
        path = F1.REG + '/EXECUTION_BASELINE.json'
        for kind, registered in (('pull_request', True), ('push', False)):
            row = F1.evaluate_scope(event={'event': kind, 'B': B, 'registered_candidate': registered},
                                    changed={path}, protected={path}, base_guard_present=True,
                                    guard_origin=B, execution_ready=True)
            self.assertTrue(row['f1_required'])
            self.assertEqual(row['disposition'], 'F1_PROVIDER_ADMISSION_REQUIRED')

    def compatible_a3_workflows(self):
        root = MODULE.resolve().parents[3]
        verify = (root / F1.HOOKS[0]).read_text()
        quality = (root / F1.HOOKS[1]).read_text()
        # These exact adjacent interfaces were agreed with the A3 owner.
        if '        id: a3_scope\n' not in verify:
            verify = verify.replace('      f1_required: ${{ steps.f1_scope.outputs.f1_required }}\n',
                                    '      f1_required: ${{ steps.f1_scope.outputs.f1_required }}\n'
                                    '      a3_required: ${{ steps.a3_scope.outputs.a3_required }}\n')
            verify = verify.replace('      - name: F1 protected-base source scope and mandatory routing\n',
                                    F1.A3_IMPACT_STEP + '      - name: F1 protected-base source scope and mandatory routing\n')
            verify = verify.replace("needs.impact.outputs.f1_required == 'true')", "needs.impact.outputs.f1_required == 'true' || needs.impact.outputs.a3_required == 'true')")
            verify = verify.replace("needs.impact.outputs.f1_required == 'true' }}\n          F1_REQUIRED:",
                                    "needs.impact.outputs.f1_required == 'true' || needs.impact.outputs.a3_required == 'true' }}\n          F1_REQUIRED:")
            verify = verify.replace("      run_f1: ${{ needs.impact.outputs.f1_required == 'true' }}\n",
                                    "      run_f1: ${{ needs.impact.outputs.f1_required == 'true' }}\n"
                                    "      run_a3: ${{ needs.impact.outputs.a3_required == 'true' }}\n")
            verify = verify.replace('          F1_DISPOSITION: ${{ needs.quality.outputs.f1_disposition }}\n',
                                    '          F1_DISPOSITION: ${{ needs.quality.outputs.f1_disposition }}\n'
                                    '          A3_REQUIRED: ${{ needs.impact.outputs.a3_required }}\n'
                                    '          A3_DISPOSITION: ${{ needs.quality.outputs.a3_disposition }}\n')
            verify = verify.replace(F1.F1_SUMMARY, F1.F1_SUMMARY + F1.A3_SUMMARY)
        if '      run_a3:\n' not in quality:
            quality = quality.replace('      run_f1:\n', F1.A3_INPUT + '      run_f1:\n')
            quality = quality.replace('      f1_disposition:\n', F1.A3_OUTPUT + '      f1_disposition:\n')
        return verify.encode(), quality.encode()

    def test_f1_g10_exact_A3_dispatch_additions_preserve_F1_projection(self):
        root = MODULE.resolve().parents[3]
        verify, quality = self.compatible_a3_workflows()
        for name, raw, kind in ((F1.HOOKS[0], verify, 'verify'), (F1.HOOKS[1], quality, 'quality')):
            self.assertEqual(F1.workflow_projection((root / name).read_bytes(), kind),
                             F1.workflow_projection(raw, kind))
        originals = {str(root / name): (root / name).read_bytes() for name in F1.HOOKS}
        originals.update({str(root / F1.HOOKS[0]): verify, str(root / F1.HOOKS[1]): quality})
        with patch.object(F1, 'bounded_file', side_effect=lambda p: originals[str(p)]):
            F1.validate_actual_routes(root)

    def test_f1_g11_unknown_shared_mutations_get_no_projection_exemption(self):
        verify, quality = self.compatible_a3_workflows()
        for bad in (verify.replace(b'      run_f1: ${{ needs.impact.outputs.f1_required == \'true\' }}', b'      run_f1: false'),
                    verify.replace(b'  actions: read\n', b'  actions: write\n', 1)):
            self.assertNotEqual(F1.workflow_projection(verify, 'verify'), F1.workflow_projection(bad, 'verify'))
        for bad in (quality.replace(F1.A3_INPUT.encode(), F1.A3_INPUT.replace('default: false', 'default: true').encode()),
                    verify.replace(F1.A3_IMPACT_STEP.encode(), F1.A3_IMPACT_STEP.replace('--a3-scope-only', '--f1-scope-only').encode()),
                    verify.replace(F1.A3_SUMMARY.encode(), F1.A3_SUMMARY.replace('test "$QUALITY_RESULT" = success', 'true').encode())):
            kind = 'quality' if bad.startswith(b'name: Quality') else 'verify'
            self.reject('F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED', F1.workflow_projection, bad, kind)
        value = "always() && needs.fast-gate.result == 'success' && (needs.impact.outputs.run_quality == 'true' || needs.impact.outputs.f1_required == 'true' || true)"
        self.reject('bad-or', lambda: F1.quality_or_expression(value, caller=True, reason='bad-or'))

    def test_f1_g12_shell_only_explicit_metadata_lines_are_exempt(self):
        root = MODULE.resolve().parents[3]
        raw = (root / F1.HOOKS[2]).read_bytes()
        before = F1.shell_projection(raw)
        for line in F1.COMPAT_METADATA_LINES:
            if line.encode() + b'\n' not in raw:
                self.assertEqual(before, F1.shell_projection(raw + line.encode() + b'\n'))
        # A synthetic digest policy tests identity matching only. It does not
        # qualify or substitute for the independently reviewed actual A3 block.
        fixture = '# A3_R1_SOURCE_SCOPE_GUARD_BEGIN\n# in-memory identity fixture\n# A3_R1_SOURCE_SCOPE_GUARD_END\n'
        if b'# A3_R1_SOURCE_SCOPE_GUARD_BEGIN\n' not in raw:
            marker = b'# F1_R1_SOURCE_SCOPE_GUARD_END\n'
            with patch.object(F1, 'A3_COMPAT_SHELL_SHA256', F1.sha(fixture.encode())):
                combined = raw.replace(marker, marker + fixture.encode())
                self.assertEqual(before, F1.shell_projection(combined))
                self.reject('F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED', F1.shell_projection,
                            combined.replace(b'# in-memory identity fixture', b'exec true'))

    def test_f1_g13_arbitrary_shell_cannot_disappear_from_projection(self):
        root = MODULE.resolve().parents[3]
        raw = (root / F1.HOOKS[2]).read_bytes()
        before = F1.shell_projection(raw)
        for text in ('exit 0', 'trap true EXIT', '. /tmp/unknown',
                     'export GIT_ALLOW_PROTOCOL=https', 'python3 /tmp/unknown.py',
                     'python3 tests/validation/frontend_evolution/fe09_a3_f0_source_admission.py --self-test; true',
                     'python3 "$(unknown)"', 'exec true'):
            with self.subTest(text=text):
                self.assertNotEqual(before, F1.shell_projection(raw + text.encode() + b'\n'))

    def test_f1_g14_extractor_has_identical_bounded_git_reader(self):
        root = MODULE.resolve().parents[3]
        source = MODULE.read_text()
        shell = (root / F1.HOOKS[2]).read_text()
        unused_before, reader, unused_after = F1.marked_block(source, 'F1_R1_LOCAL_GIT_READER')
        unused_before, copied, unused_after = F1.marked_block(shell, 'F1_R1_LOCAL_GIT_READER')
        self.assertEqual(reader, copied)
        unused_before, owned, unused_after = F1.marked_block(shell, 'F1_R1_SOURCE_SCOPE_GUARD')
        self.assertIn('raw = event_stream.read(2097153)', owned)
        self.assertNotIn('subprocess.check_output(', owned)
        self.assertNotIn('.communicate(', reader)
        self.assertIn('stdout, unused_stderr, observation = local_git_read(root, args)', owned)

    def test_f1_g15_frozen_five_docs_and_96_originals_remain_exact(self):
        root = MODULE.resolve().parents[3]
        for name, digest in F1.DOC_DIGESTS.items():
            self.assertEqual(F1.sha(F1.bounded_file(root / F1.REG / name)), digest)
        lock = F1.strict_json(F1.bounded_file(root / F1.REG / 'source-lock.json'))
        rows = [row for row in lock['files'] if row['role'].startswith('IMMUTABLE_ORIGINAL')]
        self.assertEqual(len(rows), 96)
        self.assertEqual(len({row['path'] for row in rows}), 96)
        for row in rows:
            raw = F1.bounded_file(root / row['path'])
            self.assertEqual((len(raw), F1.sha(raw)), (row['bytes'], row['sha256']), row['path'])

    def test_actual_YAML_route_positive_and_single_mutations(self):
        root = MODULE.resolve().parents[3]
        originals = {str(root / name): (root / name).read_bytes() for name in F1.HOOKS}
        with patch.object(F1, "bounded_file", side_effect=lambda p: originals[str(p)]):
            F1.validate_actual_routes(root)
        cases = [
            (F1.HOOKS[0], b" || needs.impact.outputs.f1_required == 'true')", b")", "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1"),
            (F1.HOOKS[0], b"      run_f1: ${{ needs.impact.outputs.f1_required == 'true' }}", b"      run_f1: false", "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1"),
            (F1.HOOKS[1], b"    if: inputs.run_extended || inputs.run_f1", b"    if: inputs.run_extended", "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION"),
            (F1.HOOKS[0], b"          EXPECT_QUALITY: ${{ needs.impact.outputs.run_quality == 'true' || needs.impact.outputs.f1_required == 'true' }}", b"          EXPECT_QUALITY: ${{ needs.impact.outputs.run_quality }}", "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION"),
            (F1.HOOKS[0], b"          F1_DISPOSITION: ${{ needs.quality.outputs.f1_disposition }}", b"          F1_DISPOSITION: made-up", "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION"),
            (F1.HOOKS[1], b"        value: ${{ jobs.frontend-rss-f1.outputs.disposition }}", b"        value: SOURCE_METADATA_ONLY", "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION"),
        ]
        for name, old, new, reason in cases:
            with self.subTest(field=old.decode()):
                self.assertEqual(originals[str(root / name)].count(old), 1)
                mutated = dict(originals)
                mutated[str(root / name)] = mutated[str(root / name)].replace(old, new, 1)
                with patch.object(F1, "bounded_file", side_effect=lambda p: mutated[str(p)]):
                    self.reject(reason, F1.validate_actual_routes, root)

    def test_integer_stage_budget_at_large_epoch(self):
        epoch = 1_792_876_123_987_654_321
        mono = 987_654_321_987_654
        row = F1.stage_admission(epoch + 240_000_000_000, epoch, mono)
        self.assertEqual(row["admitted_stage_duration_ns"], 180_000_000_000)
        self.assertEqual(row["stage_deadline_monotonic_ns"], mono + 180_000_000_000)
        self.reject("INSUFFICIENT_F1_STAGE_WINDOW", F1.stage_admission,
                    epoch + 240_000_000_000 - 1, epoch, mono)

    def test_deadline_never_adds_float_epsilon(self):
        origin = 999_999_123_456_789
        F1.enforce_deadline(origin, origin + 180_000_000_000, 180_000_000_000, "late")
        self.reject("late", F1.enforce_deadline, origin, origin + 180_000_000_001, 180_000_000_000, "late")

    def test_engineering_work_cleanup_model_only(self):
        origin = 123_456_789
        row = F1.engineering_deadlines(origin, origin + 1_000_000_000)
        row.update(fixture="P04", timeout_trigger_monotonic_ns=origin + 800_000_000,
                   reap_finished_monotonic_ns=origin + 850_000_000,
                   encoding_finished_monotonic_ns=origin + 900_000_000,
                   owned_child_reaped=True, signal_number=9,
                   reason="F1R1_ENGINEERING_INVOCATION_TIMEOUT")
        F1.validate_engineering_completion(row)
        late = dict(row, encoding_finished_monotonic_ns=origin + 1_000_000_001)
        self.reject("F1R1_ENGINEERING_INVOCATION_LIMIT", F1.validate_engineering_completion, late)
        self.reject("F1R1_ENGINEERING_FULL_WINDOW_REQUIRED", F1.engineering_deadlines,
                    origin, origin + 999_999_999)

    def test_real_calendar_parse(self):
        self.assertIsInstance(F1.strict_UTC_seconds("2026-10-24T16:50:18Z"), int)
        self.reject("F1R1_STRICT_UTC_TIMESTAMP", F1.strict_UTC_seconds, "2026-02-30T00:00:00Z")

    @staticmethod
    def wire(phase="ENTRY", **extra):
        value = dict(v=1, phase=phase, nonce="a" * 64, ordinal=1, pid=123,
                     ppid=122, monotonic_ns=1)
        value.update(extra)
        return (json.dumps(value, separators=(",", ":")) + "\n").encode()

    def test_wire_positive_and_exact_limits(self):
        self.assertEqual(F1.validate_wire(self.wire())["phase"], "ENTRY")
        self.reject("F1R1_WIRE_BYTES_LIMIT", F1.validate_wire, b"x" * 256 + b"\n")
        self.reject("F1R1_WIRE_ASCII_LF_FRAME", F1.validate_wire, self.wire()[:-1] + b"\r\n")

    def test_wire_duplicate_and_extra_fields(self):
        raw = self.wire().replace(b'{', b'{"nonce":"' + b'a' * 64 + b'",', 1)
        self.assertLessEqual(len(raw), 256)
        self.reject("F1R1_WIRE_DUPLICATE_JSON_KEY", F1.validate_wire, raw)
        self.reject("F1R1_WIRE_FIELD_SET", F1.validate_wire, self.wire(override=1))
        self.reject("F1R1_STRICT_INTEGER_PID", F1.validate_wire, self.wire(pid=True))

    def test_original_status_singleton_units_and_boundaries(self):
        raw = b"Name:\tfixture\nPid:\t123\nPPid:\t122\nNSpid:\t123\nVmHWM:\t9 kB\nVmRSS:\t8 kB\nThreads:\t1\n"
        parsed = F1.parse_proc_status(raw)
        self.assertEqual(parsed["VmHWM_bytes"], 9216)
        self.assertEqual(parsed["namespace_mapping_sha256"], F1.sha(b"[123]"))
        self.reject("F1R1_REQUIRED_PROC_FIELDS", F1.parse_proc_status, raw.replace(b"VmHWM:\t9 kB\n", b""))
        self.reject("F1R1_DUPLICATE_PROC_FIELD", F1.parse_proc_status, raw + b"VmRSS:\t8 kB\n")
        self.reject("F1R1_PROC_UNIT", F1.parse_proc_status, raw.replace(b"9 kB", b"9 MB"))
        self.reject("F1R1_PROC_STATUS_BYTES_LIMIT", F1.parse_proc_status, b"x" * 8193)

    def test_original_stat_comm_with_spaces_and_parentheses(self):
        fields = ["S", "122"] + ["0"] * 17 + ["456"] + ["0"] * 5
        raw = ("123 (a name ) and ( more) " + " ".join(fields) + "\n").encode()
        value = F1.parse_proc_stat(raw)
        self.assertEqual((value["pid"], value["ppid"], value["start_ticks"]), (123, 122, 456))
        self.assertEqual(value["comm"], "a name ) and ( more")
        self.reject("F1R1_RAW_STAT_BYTES_LIMIT", F1.parse_proc_stat, b"x" * 1537)

    def test_wire_sequence_and_observation_before_ack(self):
        messages, observed = [], {}
        for i, phase in enumerate(("PREEXEC", "ENTRY", "RETURN")):
            extra = {"rss_kib": 0} if phase == "PREEXEC" else {"return_code": 0} if phase == "RETURN" else {}
            messages.append(self.wire(phase, monotonic_ns=i * 10 + 1, **extra))
            ack = dict(v=1, phase="ACK", for_phase=phase, nonce="a" * 64,
                       ordinal=1, child_pid=123, launcher_pid=122, monotonic_ns=i * 10 + 4)
            messages.append((json.dumps(ack, separators=(",", ":")) + "\n").encode())
            observed[phase] = (i * 10 + 2, i * 10 + 3)
        F1.validate_wire_sequence(messages, observed, nonce="a" * 64, ordinal=1, child_pid=123, launcher_pid=122)
        bad = dict(observed, ENTRY=(12, 15))
        self.reject("F1R1_OBSERVATION_BEFORE_ACK", F1.validate_wire_sequence,
                    messages, bad, nonce="a" * 64, ordinal=1, child_pid=123, launcher_pid=122)

    @staticmethod
    def freeze_template():
        # Explicit synthetic provider template; it is never live authority.
        root = MODULE.resolve().parents[3]
        contract = json.loads((root / F1.REG / "test-contract.json").read_text())
        schema = contract["external_freeze"]["body_schema"]
        def expand(rule):
            if "const" in rule:
                return copy.deepcopy(rule["const"])
            if rule.get("type") == "object":
                return {key: expand(value) for key, value in rule["properties"].items()}
            return "a" * 64
        body = expand(schema)
        body["source"].update(protected_base_B=B, protected_base_tree_B="4" * 40,
                              reviewed_head_C=C, reviewed_tree_C="5" * 40)
        body["reviewed_at_utc"] = "2026-10-24T17:00:00Z"
        user = {"login": "jiying2007", "id": 33591504, "type": "User"}
        url = "https://api.github.com/repos/" + F1.REPOSITORY + "/issues/845"
        comment = dict(id=101, node_id="SYNTHETIC_COMMENT_101", user=user,
                       issue_url=url, created_at="2026-10-24T17:00:01Z",
                       updated_at="2026-10-24T17:00:01Z", body=json.dumps(body))
        other_body = copy.deepcopy(body)
        other_body["source"]["reviewed_head_C"] = "6" * 40
        other = dict(comment, id=102, node_id="SYNTHETIC_COMMENT_102", body=json.dumps(other_body))
        issue = dict(id=6015285792, number=845, node_id="I_kwDOUE9X8c8AAAABZon6IA",
                     created_at="2026-10-24T16:50:18Z", user=user, url=url,
                     repository_url="https://api.github.com/repos/" + F1.REPOSITORY, comments=2)
        sweep = dict(repository=dict(id=F1.REPOSITORY_ID, full_name=F1.REPOSITORY),
                     issue_before=copy.deepcopy(issue), issue_after=copy.deepcopy(issue),
                     comments=[comment, other], selected_comment=copy.deepcopy(comment),
                     comments_has_next_page=False)
        args = dict(schema=schema, source=dict(C=C, B=B, C_tree="5" * 40, B_tree="4" * 40,
                                               actual_C_derived_before_freeze=True),
                    expected_digests=body["digests"], original_run_created_at="2026-10-24T17:00:02Z")
        return sweep, args

    def test_freeze_complete_counted_sweep_template(self):
        sweep, args = self.freeze_template()
        record = F1.validate_freeze_sweep(sweep, **args)
        self.assertEqual(record["id"], 101)
        self.assertEqual(record["body_sha256"], F1.sha(sweep["selected_comment"]["body"].encode()))
        F1.validate_freeze_pair(record, copy.deepcopy(record))

    def test_freeze_complete_list_and_POST_duplicate(self):
        sweep, args = self.freeze_template()
        F1.validate_freeze_sweep(sweep, **args)
        for kind in ("wrong_count", "next_page", "duplicate_C"):
            bad = copy.deepcopy(sweep)
            if kind == "wrong_count":
                bad["issue_after"]["comments"] += 1
                reason = "F1R1_COMPLETE_COMMENT_LIST"
            elif kind == "next_page":
                bad["comments_has_next_page"] = True
                reason = "F1R1_COMPLETE_COMMENT_LIST"
            else:
                body = json.loads(bad["comments"][1]["body"])
                body["source"]["reviewed_head_C"] = C
                bad["comments"][1]["body"] = json.dumps(body)
                reason = "F1R1_DUPLICATE_C_FREEZE"
            with self.subTest(mutation=kind):
                self.reject(reason, F1.validate_freeze_sweep, bad, **args)

    def test_freeze_same_tree_other_C_not_selected(self):
        sweep, args = self.freeze_template()
        body = json.loads(sweep["comments"][0]["body"])
        body["source"]["reviewed_head_C"] = "0" * 40
        sweep["comments"][0]["body"] = json.dumps(body)
        self.reject("F1R1_UNIQUE_MATCHING_C_FREEZE", F1.validate_freeze_sweep, sweep, **args)

    def test_freeze_creation_edit_and_equal_second(self):
        sweep, args = self.freeze_template()
        F1.validate_freeze_sweep(sweep, **args)
        changed = copy.deepcopy(sweep)
        changed["selected_comment"]["updated_at"] = "2026-10-24T17:00:02Z"
        self.reject("F1R1_FREEZE_COMMENT_EDITED", F1.validate_freeze_sweep, changed, **args)
        equal = dict(args, original_run_created_at="2026-10-24T17:00:01Z")
        self.reject("F1R1_FREEZE_NOT_BEFORE_ORIGINAL_RUN", F1.validate_freeze_sweep, sweep, **equal)

    def test_freeze_direct_record_mutation_predicates(self):
        sweep, args = self.freeze_template()
        F1.validate_freeze_sweep(sweep, **args)
        cases = [
            ("reviewed_at_utc", "2026-02-30T00:00:00Z", "F1R1_STRICT_UTC_TIMESTAMP"),
            ("reviewed_at_utc", "2026-10-24T17:00:02Z", "F1R1_REVIEW_TIMESTAMP"),
            ("reviewed_at_utc", "2026-10-24T16:59:59Z", "F1R1_PRE_POST_FREEZE_STABILITY"),
            ("decision", "GENERAL_REVIEW_LOOKS_GOOD", "F1R1_EXACT_EXECUTION_DECISION"),
            ("experiment_id", "OLD_F1", "F1R1_EXACT_EXPERIMENT_IDENTITY"),
        ]
        for field, value, reason in cases:
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(sweep)
                body = json.loads(bad["selected_comment"]["body"])
                body[field] = value
                bad["selected_comment"]["body"] = json.dumps(body)
                self.reject(reason, F1.validate_freeze_sweep, bad, **args)

    def test_freeze_direct_author_and_source_digest(self):
        sweep, args = self.freeze_template()
        bad = copy.deepcopy(sweep)
        bad["selected_comment"]["user"]["id"] += 1
        self.reject("F1R1_FREEZE_AUTHOR_IDENTITY", F1.validate_freeze_sweep, bad, **args)
        bad = copy.deepcopy(sweep)
        body = json.loads(bad["selected_comment"]["body"])
        body["digests"]["source_lock_sha256"] = "b" * 64
        bad["selected_comment"]["body"] = json.dumps(body)
        self.reject("F1R1_EXTERNAL_SOURCE_DIGEST", F1.validate_freeze_sweep, bad, **args)

    def test_main_actual_PR_before_freeze_and_immutable_B(self):
        S = "7" * 40
        detail = dict(id=9001, number=9001, head=pr_event()["pull_request"]["head"],
                      base=dict(pr_event()["pull_request"]["base"], sha="8" * 40),
                      merged=True, merged_at="2026-10-24T18:00:00Z", merge_commit_sha=S)
        run = dict(event="push", head_sha=S)
        graph = dict(S=S, S_parents=[B], S_tree="5" * 40, C_tree="5" * 40, B_tree="4" * 40)
        actual = F1.actual_provider_C("push", run, [detail], detail, graph, association_has_next_page=False)
        self.assertEqual((actual["C"], actual["B"]), (C, B))
        self.assertNotEqual(actual["B"], detail["base"]["sha"])
        self.reject("F1R1_MAIN_PROVIDER_ASSOCIATION_REQUIRED", F1.actual_provider_C,
                    "push", run, None, detail, graph)
        self.reject("F1R1_COMPLETE_MAIN_PR_ASSOCIATION", F1.actual_provider_C,
                    "push", run, [detail], detail, graph)
        self.reject("F1R1_COMPLETE_MAIN_PR_ASSOCIATION", F1.actual_provider_C,
                    "push", run, [detail], detail, graph, association_has_next_page=True)
        second = dict(detail, id=9002, number=9002)
        self.reject("F1R1_UNIQUE_MAIN_PR_ASSOCIATION", F1.actual_provider_C,
                    "push", run, [detail, second], detail, graph, association_has_next_page=False)


class ProviderMetadataTests(unittest.TestCase):
    """F1-A01..A20 and T01..T02: preregistered pure source preparation.

    Synthetic records below never stand in for provider, DNS, process-group,
    wait4, fixture or science originals. Neither execution flag is enabled.
    """
    reject = MetadataTests.reject

    @staticmethod
    def response_record(ordinal=1, phase='FIRST_JOB', name='jobs', raw=b'{}', final=True):
        path = F1.api_route(name, run_id=2001, attempt=1, source_S='7' * 40,
                            pr_number=9001, comment_id=101)
        start = 1_000_000_000 + ordinal * 10_000_000
        pid, ticks = (200, 20) if name == 'jobs' else (201, 21)
        record = {'request_ordinal': ordinal, 'phase': phase, 'route_name': name,
                  'method': 'GET', 'origin': F1.API_ORIGIN, 'path': path,
                  'http_status': 200, 'response_final_origin': F1.API_ORIGIN,
                  'response_final_url': F1.API_ORIGIN + path,
                  'headers_without_credentials': [['content-type', 'application/json'],
                                                   ['content-length', str(len(raw))]],
                  'headers_complete': True, 'body_bytes': len(raw), 'body_sha256': F1.sha(raw),
                  'body_complete': True, 'overflow': False, 'worker_pid': pid,
                  'worker_start_ticks': ticks, 'started_monotonic_ns': start,
                  'finished_monotonic_ns': start + 1_000_000, 'admitted_duration_ns': 5_000_000_000,
                  'deadline_monotonic_ns': start + 5_000_000_000,
                  'started_epoch_ns': 2_000_000_000_000 + start,
                  'finished_epoch_ns': 2_000_000_000_000 + start + 1_000_000,
                  'worker_exit_or_final_reap': {'state': 'REUSED_PENDING_FINAL_REAP'}}
        if final:
            record['worker_exit_or_final_reap'] = {'state': 'OWNED_WORKER_REAPED',
                                                   'wait4_requested_pid': pid, 'wait4_returned_pid': pid,
                                                   'raw_wait_status': 0,
                                                   'finished_monotonic_ns': start + 900_000}
        return path, record

    @staticmethod
    def job_body():
        return {'total_count': 2, 'jobs': [
            {'id': 3001, 'name': 'quality / frontend-rss-f1', 'status': 'in_progress',
             'run_id': 2001, 'run_attempt': 1, 'head_sha': C, 'started_at': '2026-10-24T18:00:00Z'},
            {'id': 3002, 'name': 'unrelated-job', 'status': 'completed'}]}

    @staticmethod
    def run_body(event='pull_request'):
        return {'id': 2001, 'run_attempt': 1, 'event': event,
                'head_sha': C if event == 'pull_request' else '7' * 40,
                'path': '.github/workflows/verify.yml', 'created_at': '2026-10-24T18:00:01Z',
                'repository': {'id': F1.REPOSITORY_ID, 'full_name': F1.REPOSITORY},
                'pull_requests': [{'number': 9001, 'head': {'sha': C}}]}

    def test_f1_a01_raw_commit_identity_and_header(self):
        raw = f'tree {"5" * 40}\nparent {B}\nauthor Synthetic <unit@example.invalid> 1 +0000\ncommitter Synthetic <unit@example.invalid> 1 +0000\n\npure template\n'.encode()
        digest = F1.git_object_digest('commit', raw)
        parsed = F1.parse_commit_object(raw, digest)
        self.assertEqual((parsed['tree'], parsed['parents']), ('5' * 40, [B]))
        self.reject('F1R1_IMMUTABLE_GIT_OBJECT', F1.parse_commit_object, raw + b'x', digest)
        duplicate = raw.replace(b'tree ' + b'5' * 40 + b'\n', b'tree ' + b'5' * 40 + b'\ntree ' + b'6' * 40 + b'\n')
        self.reject('F1R1_IMMUTABLE_GIT_OBJECT', F1.parse_commit_object,
                    duplicate, F1.git_object_digest('commit', duplicate))

    def test_f1_a02_raw_blob_and_tree_identity(self):
        raw = b'synthetic exact blob\n'
        digest = F1.git_object_digest('blob', raw)
        tree = b'100644 guard.py\0' + bytes.fromhex(digest)
        entry = F1.parse_tree_object(tree, F1.git_object_digest('tree', tree))['guard.py']
        self.assertEqual(entry, {'mode': '100644', 'oid': digest})
        objects = F1.ImmutableGitObjects(Path('/synthetic'))
        with patch.object(objects, 'member', return_value=entry), patch.object(F1, 'git', return_value=raw):
            self.assertEqual(objects.blob(B, 'guard.py')[0], raw)
        with patch.object(objects, 'member', return_value=entry), patch.object(F1, 'git', return_value=raw + b'x'):
            self.reject('F1R1_IMMUTABLE_GIT_OBJECT', objects.blob, B, 'guard.py')
        self.reject('F1R1_IMMUTABLE_GIT_OBJECT', F1.parse_tree_object,
                    tree + b'x', F1.git_object_digest('tree', tree))

    def test_f1_a03_canonical_fixed_route_only(self):
        for name in F1.API_ROUTE_CATEGORIES:
            path = F1.api_route(name, run_id=2001, attempt=1, source_S='7' * 40, pr_number=9001, comment_id=101)
            F1.validate_api_path(path)
        for path in ('https://elsewhere.invalid', F1.API_PREFIX + '/issues/846',
                     F1.API_PREFIX + '/issues/845/comments?per_page=100&page=2',
                     F1.API_PREFIX + '/issues/845/comments?per_page=100&page=1&since=now',
                     F1.API_PREFIX + '/../secrets'):
            self.reject('F1R1_CANONICAL_PROVIDER_ROUTE', F1.validate_api_path, path)
        self.reject('F1R1_CANONICAL_PROVIDER_ROUTE', F1.api_route, 'jobs', run_id=True, attempt=1)

    def test_f1_a04_exact_main17_PR15_and_no_extra_request(self):
        for event, count in (('push', 17), ('pull_request', 15)):
            ledger = F1.APIBudgetLedger(event)
            self.assertEqual(len(ledger.plan), count)
            for ordinal, (phase, name) in enumerate(ledger.plan, 1):
                path, record = self.response_record(ordinal, phase, name, final=name == 'jobs' or ordinal == count)
                ledger.accept(name, b'{}', record, expected_path=path)
            self.assertEqual(ledger.complete()['actual_GET_requests'], count)
            self.reject('F1R1_CONTROL_PLANE_REQUEST_LIMIT', ledger.next_request,
                        'POST', 'issue_after', 1_000_000_000)

    def test_f1_a05_independent_category_count_and_byte_caps(self):
        self.assertEqual(sum(count * cap for count, cap in F1.API_CATEGORY_RULES.values()), 7798784)
        ledger = F1.APIBudgetLedger('push')
        self.reject('F1R1_CONTROL_PLANE_METADATA_BYTES', ledger.retain,
                    'complete_comment_list_responses', b'x' * 1048577)
        self.assertEqual(ledger.retained_bytes, 0)
        ledger.retain('original_job_request_record', b'{}')
        self.reject('F1R1_CONTROL_PLANE_METADATA_BYTES', ledger.retain,
                    'original_job_request_record', b'{}')

    def test_f1_a06_integer_minimum_of_existing_windows(self):
        start = 9876543210123456
        full = F1.api_request_window(start, 0, start + 180_000_000_000, start + 840_000_000_000)
        self.assertEqual(full['admitted_duration_ns'], 5_000_000_000)
        self.assertEqual(full['work_deadline_monotonic_ns'], start + 4_500_000_000)
        self.assertEqual(F1.api_request_window(start, 59_000_000_000, None, None)['admitted_duration_ns'], 1_000_000_000)
        self.assertEqual(F1.api_request_window(start, 0, start + 2_000_000_000, start + 1_500_000_000)['admitted_duration_ns'], 1_500_000_000)
        self.reject('F1R1_CONTROL_PLANE_TIME_BUDGET', F1.api_request_window, start, 60_000_000_000, None, None)

    def test_f1_a07_request_cleanup_lifecycle_models_only(self):
        unused_path, row = self.response_record()
        self.assertEqual(F1.validate_api_lifecycle(row, final_reap=True), 1_000_000)
        late = dict(row, finished_monotonic_ns=row['deadline_monotonic_ns'] + 1)
        self.reject('F1R1_CONTROL_PLANE_TIME_BUDGET', F1.validate_api_lifecycle, late, final_reap=True)
        missing = dict(row, worker_exit_or_final_reap={'state': 'REUSED_PENDING_FINAL_REAP'})
        self.reject('F1R1_CONTROL_PLANE_LIFECYCLE', F1.validate_api_lifecycle, missing, final_reap=True)
        wrong = copy.deepcopy(row); wrong['worker_exit_or_final_reap']['wait4_returned_pid'] += 1
        self.reject('F1R1_CONTROL_PLANE_LIFECYCLE', F1.validate_api_lifecycle, wrong, final_reap=True)

    def test_f1_a08_response_origin_status_encoding_and_strict_JSON(self):
        path, record = self.response_record()
        F1.validate_api_response(b'{}', record, expected_path=path, cap=2097152)
        for fields, reason in (({'http_status': 302}, 'F1R1_CONTROL_PLANE_HTTP_STATUS'),
                               ({'response_final_url': 'https://elsewhere.invalid'}, 'F1R1_CANONICAL_PROVIDER_ROUTE'),
                               ({'headers_without_credentials': record['headers_without_credentials'] + [['content-encoding', 'gzip']]}, 'F1R1_CONTROL_PLANE_CONTENT_ENCODING')):
            self.reject(reason, F1.validate_api_response, b'{}', dict(record, **fields), expected_path=path, cap=2097152)
        for raw, reason in ((b'\xff', 'F1R1_INVALID_JSON'), (b'{"a":1,"a":2}', 'F1R1_DUPLICATE_JSON_KEY')):
            path, mutated = self.response_record(raw=raw)
            self.reject(reason, F1.validate_api_response, raw, mutated, expected_path=path, cap=2097152)

    def test_f1_a09_partial_overflow_is_retained_failure(self):
        path, row = self.response_record(raw=b'{}')
        F1.validate_api_response(b'{}', row, expected_path=path, cap=2097152)
        for change in ({'body_complete': False}, {'overflow': True}, {'body_bytes': 3}):
            self.reject('F1R1_CONTROL_PLANE_PARTIAL_RESPONSE', F1.validate_api_response,
                        b'{}', dict(row, **change), expected_path=path, cap=2097152)
        ledger = F1.APIBudgetLedger('push')
        row.update(body_complete=False, body_bytes=1, body_sha256=F1.sha(b'{'), request_qualification_complete=False,
                   reason='F1R1_CONTROL_PLANE_PARTIAL_RESPONSE')
        ledger.failed_request('jobs', b'{', row)
        self.assertTrue(ledger.failed)
        self.assertEqual(ledger.category_bytes['original_job_response'], 1)
        self.reject('F1R1_CONTROL_PLANE_REQUEST_LIMIT', ledger.complete)

    def test_f1_a10_original_Jobs_completeness(self):
        body = self.job_body()
        args = dict(headers=[], run_id=2001, attempt=1, expected_head=C)
        F1.validate_original_jobs(body, **args)
        for bad in (dict(body, total_count=3), dict(body, total_count=True),
                    dict(body, jobs=[body['jobs'][0], body['jobs'][0]])):
            self.reject('F1R1_COMPLETE_ORIGINAL_JOBS', F1.validate_original_jobs, bad, **args)
        next_args = dict(args, headers=[['link', '<https://api.github.com/next>; rel="next"']])
        self.reject('F1R1_COMPLETE_ORIGINAL_JOBS', F1.validate_original_jobs, body, **next_args)

    def test_f1_a11_original_Job_identity_and_fixed900_60(self):
        body = self.job_body(); args = dict(headers=[], run_id=2001, attempt=1, expected_head=C)
        deadline = F1.validate_original_jobs(body, **args)
        self.assertEqual(deadline['deadline_epoch_ns'] - deadline['started_epoch_ns'], 900_000_000_000)
        self.assertEqual(deadline['archive_reserve_seconds'], 60)
        bad = copy.deepcopy(body); bad['jobs'][1]['name'] = 'frontend-rss-f1'
        self.reject('F1R1_UNIQUE_ORIGINAL_JOB', F1.validate_original_jobs, bad, **args)
        bad = copy.deepcopy(body); bad['jobs'][0]['run_attempt'] = 2
        self.reject('F1R1_ORIGINAL_JOB_BINDING', F1.validate_original_jobs, bad, **args)
        self.assertEqual(F1.provider_timestamp_ns('2026-10-24T19:00:00.123456789+01:00'),
                         F1.provider_timestamp_ns('2026-10-24T18:00:00Z') + 123456789)

    def test_f1_a12_actual_run_and_environment_source(self):
        run = self.run_body()
        kwargs = dict(run_id=2001, attempt=1, event='pull_request', expected_head=C)
        F1.validate_actual_run(run, **kwargs)
        self.reject('F1R1_RUN_WORKFLOW_SOURCE', F1.validate_actual_run,
                    dict(run, path='.github/workflows/quality.yml'), **kwargs)
        self.reject('F1R1_RUN_EVENT_SOURCE', F1.validate_actual_run, dict(run, run_attempt=2), **kwargs)
        environment = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY=F1.REPOSITORY,
                           GITHUB_REPOSITORY_ID=str(F1.REPOSITORY_ID), GITHUB_JOB='frontend-rss-f1',
                           GITHUB_RUN_ID='2001', GITHUB_RUN_ATTEMPT='1', GITHUB_SHA=M,
                           GITHUB_REF='refs/pull/9001/merge', GITHUB_EVENT_NAME='pull_request')
        event = dict(pr_event(), number=9001)
        self.assertEqual(F1.hosted_provider_context(environment, event)['expected_provider_head'], C)
        self.reject('F1R1_ACTUAL_JOB_CONTEXT', F1.hosted_provider_context,
                    dict(environment, GITHUB_JOB='frontend-s3-t3s3f0'), event)

    def test_f1_a13_PR_number_comes_from_event_run_association(self):
        run = self.run_body(); event = dict(pr_event(), number=9001)
        self.assertEqual(F1.select_provider_PR('pull_request', event, run, None,
                                              association_has_next_page=None), 9001)
        bad = dict(run, pull_requests=run['pull_requests'] * 2)
        self.reject('F1R1_RUN_PR_ASSOCIATION', F1.select_provider_PR,
                    'pull_request', event, bad, None, association_has_next_page=None)
        self.reject('F1R1_RUN_PR_ASSOCIATION', F1.select_provider_PR,
                    'pull_request', dict(event, number=9002), run, None, association_has_next_page=None)

    def main_sweep_template(self):
        sweep, kwargs = MetadataTests.freeze_template()
        run = self.run_body('push'); S = '7' * 40
        detail = dict(id=9001, number=9001, node_id='SYNTHETIC_PR_9001',
                      head=pr_event()['pull_request']['head'],
                      base=dict(pr_event()['pull_request']['base'], sha='8' * 40),
                      merged=True, merged_at='2026-10-24T18:00:00Z', merge_commit_sha=S)
        records = {'repository': sweep['repository'], 'run': run, 'association': [detail], 'pr': detail,
                   'issue_before': sweep['issue_before'], 'comments': sweep['comments'],
                   'selected': sweep['selected_comment'], 'issue_after': sweep['issue_after']}
        context = dict(event='push', run_id=2001, run_attempt=1, checkout=S, expected_provider_head=S)
        graph = dict(S=S, S_parents=[B], S_tree='5' * 40, C_tree='5' * 40, B_tree='4' * 40)
        return records, context, graph, kwargs

    def test_f1_a14_main_graph_and_actual_PR_precede_freeze_selection(self):
        records, context, graph, kwargs = self.main_sweep_template()
        order = []
        def read(name, path):
            order.append(name); F1.validate_api_path(path)
            return copy.deepcopy(records[name]), []
        def graph_read(detail):
            order.append('immutable_graph'); return graph
        result = F1.provider_sweep_readback(context, {}, read, graph_read,
                                            schema=kwargs['schema'], expected_digests=kwargs['expected_digests'])
        self.assertEqual(order, ['repository', 'run', 'association', 'pr', 'immutable_graph',
                                 'issue_before', 'comments', 'selected', 'issue_after'])
        self.assertEqual(result['source']['B'], B)
        self.assertNotEqual(result['source']['B'], records['pr']['base']['sha'])
        self.assertFalse(result['scientific_execution_admitted'])

    def test_f1_a15_unique_actual_C_comment_before_direct_read(self):
        sweep, args = MetadataTests.freeze_template()
        kwargs = dict(source=args['source'], schema=args['schema'], has_next_page=False)
        self.assertEqual(F1.select_freeze_comment(sweep['comments'], sweep['issue_before'], **kwargs), 101)
        duplicated = copy.deepcopy(sweep['comments'])
        duplicated[1]['body'] = duplicated[0]['body']
        self.reject('F1R1_DUPLICATE_C_FREEZE', F1.select_freeze_comment,
                    duplicated, sweep['issue_before'], **kwargs)
        self.reject('F1R1_COMPLETE_COMMENT_LIST', F1.select_freeze_comment,
                    sweep['comments'], sweep['issue_before'], **dict(kwargs, has_next_page=None))

    def test_f1_a16_PRE_POST_source_freeze_tuple_stability(self):
        records, context, graph, args = self.main_sweep_template()
        result = F1.provider_sweep_readback(context, {}, lambda name, path: (copy.deepcopy(records[name]), []),
                                            lambda detail: graph, schema=args['schema'], expected_digests=args['expected_digests'])
        F1.validate_provider_sweep_pair(result, copy.deepcopy(result))
        for field in ('source', 'run_identity', 'PR_authority', 'freeze_identity'):
            changed = copy.deepcopy(result); changed[field]['synthetic_drift'] = True
            self.reject('F1R1_PRE_POST_FREEZE_STABILITY', F1.validate_provider_sweep_pair, result, changed)

    def test_f1_a17_reused_worker_process_key_and_final_reap(self):
        ledger = F1.APIBudgetLedger('push')
        for ordinal, name, phase in ((1, 'jobs', 'FIRST_JOB'), (2, 'repository', 'PRE')):
            path, row = self.response_record(ordinal, phase, name, final=name == 'jobs')
            ledger.accept(name, b'{}', row, expected_path=path)
        path, changed = self.response_record(3, 'PRE', 'run', final=False)
        changed['worker_start_ticks'] += 1
        self.reject('F1R1_CONTROL_PLANE_WORKER_LIMIT', ledger.accept,
                    'run', b'{}', changed, expected_path=path)
        self.assertEqual(len(ledger.requests), 2)

    def test_f1_a18_headers_and_child_env_do_not_copy_private_values(self):
        self.reject('F1R1_CONTROL_PLANE_CREDENTIALS', F1.api_headers_view,
                    [['authorization', 'synthetic-only-secret']])
        with patch.dict(F1.os.environ, {'GH_TOKEN': 'synthetic-only-secret', 'AWS_SECRET_ACCESS_KEY': 'another-unit-only',
                                       'CFLAGS': '-include injected.h', 'LD_PRELOAD': '/injected.so'}):
            build = F1.build_child_environment(Path('/synthetic/build-tmp'))
            launcher = F1.launcher_child_environment()
        self.assertEqual(set(build), {'PATH', 'LC_ALL', 'TZ', 'TMPDIR'})
        self.assertEqual(set(launcher), {'ASAN_OPTIONS', 'UBSAN_OPTIONS', 'LC_ALL', 'TZ'})
        self.assertNotIn(b'synthetic-only-secret', F1.compact_json([build, launcher]))
        self.assertNotIn('LD_PRELOAD', launcher)

    def test_f1_a19_original_record_replay_binds_body_deadline_and_context(self):
        context = dict(event='pull_request', run_id=2001, run_attempt=1, checkout=M, expected_provider_head=C)
        raw = F1.compact_json(self.job_body())
        unused_path, row = self.response_record(raw=raw)
        deadline = F1.validate_original_jobs(self.job_body(), headers=row['headers_without_credentials'],
                                             run_id=2001, attempt=1, expected_head=C)
        row.update(started_epoch_ns=deadline['started_epoch_ns'] + 100_000_000,
                   finished_epoch_ns=deadline['started_epoch_ns'] + 101_000_000,
                   selected_job_id=3001, original_job_deadline=deadline, actual_context=context)
        directory = Path('/synthetic/original-job')
        original = {'response.json': raw, 'request.json': F1.compact_json(row)}
        with patch.object(F1, 'bounded_file', side_effect=lambda path, cap: original[path.name]):
            ledger = F1.APIBudgetLedger('pull_request')
            self.assertEqual(F1.replay_original_job(directory, context, ledger), deadline)
            self.assertEqual(len(ledger.requests), 1)
        changed = copy.deepcopy(row); changed['original_job_deadline']['deadline_epoch_ns'] += 1
        with patch.object(F1, 'bounded_file', side_effect=lambda path, cap: raw if path.name == 'response.json' else F1.compact_json(changed)):
            self.reject('F1R1_ORIGINAL_JOB_BINDING', F1.replay_original_job,
                        directory, context, F1.APIBudgetLedger('pull_request'))

    def test_f1_a20_all_actual_worker_entries_reject_at_false_gates(self):
        self.assertIs(F1.PROVIDER_EXECUTION_ENABLED, False)
        self.assertIs(F1.SCIENCE_EXECUTION_ENABLED, False)
        unstarted = object.__new__(F1.HTTPMetadataWorker)
        with patch.object(F1.os, 'fork') as fork, patch.object(F1.subprocess, 'Popen') as popen, \
             patch.object(F1.urllib.request.OpenerDirector, 'open') as request:
            self.reject('F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP', F1.HTTPMetadataWorker,
                        'synthetic-token', F1.APIBudgetLedger('push'), Path('/unused'))
            self.reject('F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP', F1._http_worker_main, 1, 2, 'synthetic-token')
            self.reject('F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP', unstarted._start)
            self.reject('F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP', unstarted.get,
                        'PRE', 'repository', F1.API_PREFIX, stage_deadline_ns=1, job_deadline_ns=1)
            self.reject('F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP', F1.capture_original_job,
                        {}, token='synthetic-token', output=Path('/unused'))
            self.reject('F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP', unstarted.abort_between_requests,
                        stage_deadline_ns=1, job_deadline_ns=1)
            fork.assert_not_called(); popen.assert_not_called(); request.assert_not_called()

    def test_f1_t01_science29_29half_30_inside_original_cap(self):
        origin = 9876543210123456
        row = F1.science_deadlines(origin, origin + 180_000_000_000, origin + 840_000_000_000)
        self.assertEqual(row['admitted_duration_ns'], 30_000_000_000)
        self.assertEqual(row['work_deadline_monotonic_ns'], origin + 29_000_000_000)
        self.assertEqual(row['native_final_deadline_monotonic_ns'], origin + 29_500_000_000)
        self.assertEqual(row['invocation_deadline_monotonic_ns'], origin + 30_000_000_000)
        self.assertEqual(F1.science_deadlines(origin, origin + 3_000_000_000, origin + 4_000_000_000)['admitted_duration_ns'], 3_000_000_000)
        self.reject('F1R1_SCIENCE_INVOCATION_WINDOW_REQUIRED', F1.science_deadlines,
                    origin, origin + 1_000_000_000, origin + 30_000_000_000)
        engineering = F1.engineering_deadlines(origin, origin + 1_000_000_000)
        self.assertEqual(engineering['work_deadline_monotonic_ns'], origin + 800_000_000)
        self.assertEqual(engineering['final_deadline_monotonic_ns'], origin + 1_000_000_000)

    def test_f1_t02_owned_group_cleanup_order_model_only(self):
        row = dict(launcher_pid=100, owned_process_group=100,
                   invocation_started_monotonic_ns=1, leader_observed_waitable_monotonic_ns=2,
                   group_SIGKILL_monotonic_ns=3, launcher_wait4_finished_monotonic_ns=4,
                   group_absent_observed_monotonic_ns=5, encoding_finished_monotonic_ns=6,
                   invocation_deadline_monotonic_ns=30_000_000_001,
                   leader_wait_observation_consumed=False, leader_unreaped_at_group_SIGKILL=True,
                   group_absent=True, wait4_requested_pid=100, wait4_returned_pid=100,
                   signals_after_leader_reap=0, additional_descendant_proc_snapshots=0)
        F1.validate_owned_group_cleanup(row)
        F1.validate_owned_group_cleanup(dict(row, leader_observed_waitable_monotonic_ns=None))
        self.reject('F1R1_OWNED_GROUP_CLEANUP_REQUIRED', F1.validate_owned_group_cleanup,
                    dict(row, leader_unreaped_at_group_SIGKILL=False))
        self.reject('F1R1_OWNED_GROUP_CLEANUP_ORDER', F1.validate_owned_group_cleanup,
                    dict(row, launcher_wait4_finished_monotonic_ns=2))
        self.reject('F1R1_OWNED_GROUP_CLEANUP_ORDER', F1.validate_owned_group_cleanup,
                    dict(row, encoding_finished_monotonic_ns=30_000_000_002))


if __name__ == "__main__":
    unittest.main(verbosity=2)
