#!/usr/bin/env python3
"""Offline tiny ZIP / HTTP contract tests; no GitHub, DSP or scientific replay."""
from __future__ import annotations

import copy
import argparse
import hashlib
import io
import json
from pathlib import Path
import signal
import stat
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

import fe09_same_run_artifact_download as download
import fe09_same_run_artifact_visibility as old

REPO = "jiying2007/audio-pipeline"
RUN, ATTEMPT, ARTIFACT = 12345, 2, 98765
HEAD, SOURCE = "b" * 40, "c" * 40
TOKEN = "synthetic-only-secret-token"
BLOB = "https://productionresultssa3.blob.core.windows.net/signed-path?sig=synthetic-secret"
DATA = {"SHA256SUMS": b"tiny synthetic manifest\n", "receipt.json": b'{"tiny":true}\n',
        "collect.log": b"tiny payload only\n", "verify.log": b"tiny\n"}


def tiny_zip(*, data=None, entries=None, compression=zipfile.ZIP_DEFLATED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as handle:
        for name, body in (entries if entries is not None else (data or DATA).items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            info.compress_type = compression
            handle.writestr(info, body)
    return stream.getvalue()


class Response(io.BytesIO):
    def __init__(self, body=b"", *, status=200, headers=None, url=None):
        super().__init__(body)
        self.status, self.headers, self.url = status, headers or {}, url


class Fixture:
    def __init__(self, root, stage="b2s2", archive=None):
        self.root, self.stage = root, stage
        self.archive = tiny_zip() if archive is None else archive
        self.name = download.STAGES[stage]["prefix"] + str(RUN)
        if download.STAGES[stage]["attempt_name"]:
            self.name += "-attempt-" + str(ATTEMPT)
        self.run = {"id": RUN, "run_attempt": ATTEMPT, "head_sha": HEAD,
                    "status": "in_progress", "conclusion": None,
                    "repository": {"full_name": REPO, "id": 123},
                    "head_repository": {"id": 456},
                    "run_started_at": "2026-11-27T18:00:00Z",
                    "referenced_workflows": [{"path": REPO +
                        "/.github/workflows/quality.yml@" + SOURCE, "sha": SOURCE}]}
        self.artifact = {"id": ARTIFACT, "name": self.name, "expired": False,
                         "size_in_bytes": len(self.archive),
                         "digest": "sha256:" + hashlib.sha256(self.archive).hexdigest(),
                         "created_at": "2026-11-27T18:01:00Z",
                         "workflow_run": {"id": RUN, "head_sha": HEAD,
                                          "repository_id": 123, "head_repository_id": 456}}
        self.opened, self.paused = [], []
        self.args = dict(stage=stage, repo=REPO, run_id=RUN, artifact_id=ARTIFACT,
                         artifact_name=self.name, token=TOKEN, run_attempt=ATTEMPT,
                         run_head_sha=HEAD, execution_source=SOURCE,
                         output=root / "readback", evidence=root / "transport",
                         alarms=False, pause=self.paused.append)

    def listing(self, rows=None, total=None):
        rows = [self.artifact] if rows is None else rows
        return {"total_count": len(rows) if total is None else total, "artifacts": rows}

    def responses(self):
        return [self.run, self.listing(), Response(status=302, headers={"Location": BLOB}),
                Response(self.archive, headers={"Content-Length": str(len(self.archive))})]

    def execute(self, values=None, **changes):
        queue = iter(self.responses() if values is None else values)
        def opener(request, timeout):
            self.opened.append((request, timeout))
            value = next(queue)
            if callable(value):
                value = value(request)
            if isinstance(value, BaseException):
                raise value
            if type(value) is dict:
                value = Response(json.dumps(value).encode("utf-8"))
            if value.url is None:
                value.url = request.full_url
            return value
        return download.download_artifact(opener=opener, **dict(self.args, **changes))

    def report(self):
        return json.loads((self.args["evidence"] / "transport.json").read_text("utf-8"))


class OriginalZipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fresh(self, stage="b2s2", archive=None):
        root = self.root / str(len(list(self.root.iterdir())))
        root.mkdir()
        return Fixture(root, stage, archive)

    def assert_refused(self, f, values=None, message=None, **changes):
        with self.assertRaises(download.NotAdmitted) as caught:
            f.execute(values, **changes)
        if message is not None:
            self.assertIn(message, str(caught.exception))
        if (f.args["evidence"] / "transport.json").is_file():
            self.assertEqual(f.report()["status"], "FAILED")
            serialized = json.dumps(f.report())
            self.assertNotIn(TOKEN, serialized)
            self.assertNotIn("synthetic-secret", serialized)
            self.assertNotIn("signed-path", serialized)
        return str(caught.exception)

    def test_both_exact_stages_fetch_one_original_zip_then_same_four_bytes(self):
        for stage in download.STAGES:
            f = self.fresh(stage)
            result = f.execute()
            self.assertEqual(result["status"], "PASS_TRANSPORT_ONLY")
            self.assertEqual([e["kind"] for e in result["requests"]], ["run", "list", "archive", "blob"])
            self.assertEqual(result["budget"], {"http_requests": 8, "request_seconds": 10,
                                               "total_seconds": 94, "retry_pause_seconds": 2})
            self.assertEqual(len(f.opened), 4)
            self.assertEqual(f.paused, [])
            self.assertEqual((f.args["evidence"] / "original.zip").read_bytes(), f.archive)
            self.assertFalse((f.args["evidence"] / "original.zip.partial").exists())
            self.assertEqual({p.name for p in f.args["output"].iterdir()}, set(DATA))
            for name, body in DATA.items():
                self.assertEqual((f.args["output"] / name).read_bytes(), body)
                self.assertEqual(result["members"][name]["sha256"], hashlib.sha256(body).hexdigest())

    def test_token_never_crosses_api_host_and_signed_url_never_retained(self):
        f = self.fresh()
        report = f.execute()
        for request, timeout in f.opened:
            self.assertEqual(timeout, 10)
            if request.full_url.startswith(download.API_URL + "/"):
                self.assertEqual(request.get_header("Authorization"), "Bearer " + TOKEN)
            else:
                self.assertEqual(request.full_url, BLOB)
                self.assertIsNone(request.get_header("Authorization"))
        serialized = json.dumps(report)
        for secret in (TOKEN, BLOB, "signed-path", "synthetic-secret"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(report["blob_host"], "productionresultssa3.blob.core.windows.net")

    def test_archive_endpoint_404_after_metadata_success_is_one_shared_retry(self):
        f = self.fresh()
        values = f.responses()
        result = f.execute(values[:2] + [Response(status=404)] + values[2:])
        self.assertEqual(len(result["requests"]), 5)
        self.assertEqual(f.paused, [2])
        self.assertEqual([e["status"] for e in result["requests"]], [200, 200, 404, 302, 200])

    def test_blob_transient_fetches_fresh_redirect_with_same_budget(self):
        for status in (404, 502, 503):
            f = self.fresh()
            values = f.responses()
            result = f.execute(values[:3] + [Response(status=status)] +
                               [Response(status=302, headers={"Location": BLOB}), values[3]])
            self.assertEqual(len(result["requests"]), 6)
            self.assertEqual(f.paused, [2])

    def test_status_302_as_urllib_http_error_is_expected(self):
        f = self.fresh()
        values = f.responses()
        values[2] = lambda req: urllib.error.HTTPError(req.full_url, 302, "not retained",
                                                       {"Location": BLOB}, None)
        self.assertEqual(f.execute(values)["status"], "PASS_TRANSPORT_ONLY")

    def test_auth_rate_limit_other_http_never_retry_at_any_phase(self):
        for stage in download.STAGES:
            for index in range(4):
                for status in (401, 403, 429, 400, 500):
                    f = self.fresh(stage)
                    values = f.responses()
                    values[index] = Response(status=status)
                    self.assert_refused(f, values, "HTTP_HARD_FAILURE")
                    self.assertEqual(len(f.opened), index + 1)
                    self.assertEqual(f.paused, [])

    def test_tls_timeout_network_errors_never_retry_or_log_exception_payload(self):
        for error in (urllib.error.URLError(BLOB), TimeoutError(BLOB), OSError(BLOB)):
            f = self.fresh()
            values = f.responses()
            values[3] = error
            self.assert_refused(f, values)
            self.assertEqual(len(f.opened), 4)
            self.assertEqual(f.paused, [])

    def test_only_two_exact_names_and_strict_identity_args_before_network(self):
        for stage in download.STAGES:
            for change in ({"stage": "other"}, {"artifact_name": "arbitrary"},
                           {"artifact_id": True}, {"artifact_id": 0}, {"artifact_id": 2**63},
                           {"run_attempt": False}, {"run_id": 0}, {"run_head_sha": "c"*39},
                           {"execution_source": "D"*40}, {"repo": "../repo"},
                           {"token": "bad\nheader"}):
                f = self.fresh(stage)
                self.assert_refused(f, **change)
                self.assertEqual(f.opened, [])
            f = self.fresh(stage)
            wrong = (f.name.replace("-attempt-2", "-attempt-1") if stage == "b2s2"
                     else f.name + "-attempt-2")
            self.assert_refused(f, artifact_name=wrong)
            self.assertEqual(f.opened, [])

    def test_cli_preserves_original_ba2_canonical_positive_upload_id_boundary(self):
        self.assertEqual(download.positive_id("98765"), ARTIFACT)
        for value in ("0", "01", "+1", "-1", " 1", "1 ", "1.0", str(2**63), "1"*20):
            with self.assertRaises(argparse.ArgumentTypeError):
                download.positive_id(value)
        with self.assertRaises(download.NotAdmitted):
            download.api_request("http://api.github.com/synthetic-only", TOKEN)

    def test_exact_attempt_head_repo_execution_and_running_run_required(self):
        mutations = (
            lambda r: r.update(run_attempt=1), lambda r: r.update(id=RUN+1),
            lambda r: r.update(head_sha="d"*40), lambda r: r.update(status="completed"),
            lambda r: r.update(conclusion="success"),
            lambda r: r["repository"].update(id=True),
            lambda r: r["repository"].update(full_name="other/repo"),
            lambda r: r["head_repository"].update(id=False),
            lambda r: r["referenced_workflows"][0].update(sha="d"*40),
            lambda r: r["referenced_workflows"].append(copy.deepcopy(r["referenced_workflows"][0])),
        )
        for mutate in mutations:
            f = self.fresh()
            mutate(f.run)
            self.assert_refused(f)
            self.assertEqual(len(f.opened), 1)
            self.assertEqual(f.paused, [])

    def test_conflicting_artifact_fails_before_even_partial_snapshot_retry(self):
        mutations = (
            lambda a: a.update(id=ARTIFACT+1), lambda a: a.update(name="other"),
            lambda a: a.update(expired=True), lambda a: a.update(size_in_bytes=True),
            lambda a: a.update(digest="bad"),
            lambda a: a.update(created_at="2026-11-27T17:59:59Z"),
            lambda a: a["workflow_run"].update(id=RUN+1),
            lambda a: a["workflow_run"].update(head_sha="d"*40),
            lambda a: a["workflow_run"].update(repository_id=999),
            lambda a: a["workflow_run"].update(head_repository_id=999),
        )
        for stage in download.STAGES:
            for mutate in mutations:
                f = self.fresh(stage)
                mutate(f.artifact)
                self.assert_refused(f, [f.run, f.listing(total=2)])
                self.assertEqual(len(f.opened), 2)
                self.assertEqual(f.paused, [])

    def test_complete_pagination_detects_duplicate_name_on_later_page(self):
        f = self.fresh("ba2")
        rows = [f.artifact] + [{"id": i, "name": "unrelated-"+str(i)} for i in range(1, 100)]
        duplicate = dict(f.artifact, id=ARTIFACT+1)
        self.assert_refused(f, [f.run, f.listing(rows, 101), f.listing([duplicate], 101)],
                            "NOT_UNIQUE")
        self.assertEqual(len(f.opened), 3)
        self.assertEqual(f.paused, [])

    def test_complete_pagination_before_archive_is_mandatory(self):
        f = self.fresh()
        rows = [f.artifact] + [{"id": i, "name": "unrelated-"+str(i)} for i in range(1, 100)]
        result = f.execute([f.run, f.listing(rows, 101),
                            f.listing([{"id": 100, "name": "unrelated-100"}], 101)] + f.responses()[2:])
        self.assertEqual(len(result["requests"]), 5)
        self.assertIn("page=2", f.opened[2][0].full_url)

    def test_invalid_or_duplicate_rows_and_duplicate_json_keys_fail(self):
        for rows in ([None], [{"id": True, "name": "x"}],
                     [{"id": 1, "name": "a"}, {"id": 1, "name": "b"}]):
            f = self.fresh()
            self.assert_refused(f, [f.run, f.listing(rows)])
            self.assertEqual(len(f.opened), 2)
            self.assertEqual(f.paused, [])
        f = self.fresh()
        self.assert_refused(f, [f.run, Response(b'{"total_count":0,"total_count":1,"artifacts":[]}')],
                            "DUPLICATE_JSON_KEY")

    def test_changing_snapshot_and_absence_restart_but_all_requests_are_shared(self):
        f = self.fresh()
        result = f.execute([f.run, f.listing(total=2), f.listing([]), f.listing()] + f.responses()[2:])
        self.assertEqual(len(result["requests"]), 6)
        self.assertEqual(f.paused, [2, 2])

    def test_no_ninth_request_after_metadata_retries_or_redirect(self):
        f = self.fresh()
        values = [f.run] + [f.listing([])] * 5 + [f.listing(),
                    Response(status=302, headers={"Location": BLOB})]
        self.assert_refused(f, values, "SHARED_HTTP_BUDGET_EXHAUSTED")
        self.assertEqual(len(f.opened), 8)
        self.assertEqual(f.paused, [2] * 5)
        self.assertEqual(f.report()["requests"][-1]["kind"], "archive")

    def test_archive_absence_stops_at_eight_total_not_eight_extra(self):
        f = self.fresh()
        self.assert_refused(f, [f.run, f.listing()] + [Response(status=404) for _ in range(6)],
                            "SHARED_HTTP_BUDGET_EXHAUSTED")
        self.assertEqual(len(f.opened), 8)
        self.assertEqual(f.paused, [2] * 5)

    def test_run_lookup_transient_consumes_same_budget(self):
        f = self.fresh()
        result = f.execute([Response(status=503)] + f.responses())
        self.assertEqual(len(result["requests"]), 5)
        self.assertEqual(f.paused, [2])

    def test_stage_caps_are_independent_and_old_one_mib_predicate_stays_strict(self):
        archive = tiny_zip(data=dict(DATA, **{"collect.log": b"x" * (1024*1024+1)}),
                           compression=zipfile.ZIP_STORED)
        f = self.fresh("ba2", archive)
        self.assertEqual(f.execute()["status"], "PASS_TRANSPORT_ONLY")
        with self.assertRaises(old.NotAdmitted):
            old.verify_metadata(f.artifact, name=f.name, run_id=RUN, artifact_id=ARTIFACT)
        for stage, cap in (("b2s2", 64*1024), ("ba2", 8*1024*1024)):
            f = self.fresh(stage)
            f.artifact["size_in_bytes"] = cap + 1
            self.assert_refused(f, message="WRONG_ID_NAME_SIZE")
            self.assertEqual(len(f.opened), 2)

    def test_redirect_rejects_unobserved_host_or_unsafe_url_before_blob_request(self):
        locations = ("http://productionresultssa3.blob.core.windows.net/a",
                     "https://productionresultssa3.blob.core.windows.net.evil/a",
                     "https://evil.blob.core.windows.net/a", "https://api.github.com/a",
                     "https://user@productionresultssa3.blob.core.windows.net/a",
                     BLOB + "#fragment", BLOB + "\n", "https://productionresultssa3.blob.core.windows.net:444/a")
        for location in locations:
            f = self.fresh()
            values = f.responses()
            values[2] = Response(status=302, headers={"Location": location})
            self.assert_refused(f, values, "REDIRECT_NOT_ADMITTED")
            self.assertEqual(len(f.opened), 3)
            self.assertEqual(f.paused, [])

    def test_automatic_or_second_redirect_is_refused(self):
        for index in (0, 1, 2, 3):
            f = self.fresh()
            values = f.responses()
            values[index] = Response(status=200, url="https://unexpected.example/")
            self.assert_refused(f, values, "UNEXPECTED_REDIRECT_FOLLOWED")
            self.assertEqual(f.paused, [])
        f = self.fresh()
        values = f.responses()
        values[3] = Response(status=302, headers={"Location": BLOB})
        self.assert_refused(f, values, "HTTP_HARD_FAILURE_302")

    def test_size_digest_and_content_length_fail_without_retry_and_keep_bounded_prefix(self):
        for change in ("short", "long", "digest", "length"):
            f = self.fresh()
            values = f.responses()
            body = f.archive[:-1] if change == "short" else f.archive + (b"x" if change == "long" else b"")
            headers = {"Content-Length": "1"} if change == "length" else {}
            values[3] = Response(body, headers=headers)
            if change == "digest":
                f.artifact["digest"] = "sha256:" + "0"*64
            self.assert_refused(f, values)
            self.assertEqual(len(f.opened), 4)
            self.assertEqual(f.paused, [])
            self.assertFalse(f.args["output"].exists())
            partial = f.args["evidence"] / "original.zip.partial"
            if change != "length":
                self.assertTrue(partial.is_file())
                self.assertLessEqual(partial.stat().st_size, len(f.archive))

    def test_partial_body_network_error_retains_prefix_without_retry(self):
        f = self.fresh()
        class Partial(Response):
            def read(self, size):
                if self.tell() == 0:
                    return super().read(7)
                raise urllib.error.URLError(BLOB)
        values = f.responses()
        values[3] = Partial(f.archive)
        self.assert_refused(f, values, "NETWORK_OR_TLS_FAILURE")
        self.assertEqual((f.args["evidence"] / "original.zip.partial").read_bytes(), f.archive[:7])
        self.assertEqual(len(f.opened), 4)
        self.assertEqual(f.paused, [])

    def test_bad_zip_crc_is_not_saved_reader_input(self):
        archive = tiny_zip(compression=zipfile.ZIP_STORED)
        archive = archive.replace(b"tiny payload only", b"tiny payload FAIL", 1)
        f = self.fresh(archive=archive)
        self.assert_refused(f, message="BadZipFile")
        self.assertFalse(f.args["output"].exists())
        self.assertEqual((f.args["evidence"] / "original.zip").read_bytes(), archive)

    def test_extra_duplicate_traversal_and_directory_members_are_refused(self):
        replacements = ("../receipt.json", "folder/receipt.json", "receipt.json/", "receipt.json\x00x")
        for replacement in replacements:
            entries = [(replacement if n == "receipt.json" else n, b) for n, b in DATA.items()]
            # zipfile itself normalizes NUL on creation; patch both name fields
            # at equal length so the admitted outer hash still covers the attack.
            if "\x00" in replacement:
                archive = tiny_zip().replace(b"receipt.json", b"receipt.jso\x00")
            else:
                archive = tiny_zip(entries=entries)
            f = self.fresh(archive=archive)
            self.assert_refused(f)
            self.assertFalse(f.args["output"].exists())
        f = self.fresh(archive=tiny_zip(entries=list(DATA.items()) + [("extra", b"x")]))
        self.assert_refused(f, message="MEMBER_SET")
        with patch("warnings.warn"):
            archive = tiny_zip(entries=[("receipt.json", b"x")] * 4)
        self.assert_refused(self.fresh(archive=archive), message="MEMBER_SET")

    def test_symlink_special_and_encrypted_member_are_refused(self):
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o600):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as zipped:
                for name, body in DATA.items():
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    info.external_attr = (mode if name == "receipt.json" else stat.S_IFREG | 0o600) << 16
                    zipped.writestr(info, body)
            self.assert_refused(self.fresh(archive=stream.getvalue()), message="MEMBER_TYPE")
        archive = bytearray(tiny_zip())
        # Local/central encryption bits; outer digest is recomputed by fixture.
        local = archive.index(b"PK\x03\x04")
        central = archive.index(b"PK\x01\x02")
        archive[local+6] |= 1
        archive[central+8] |= 1
        self.assert_refused(self.fresh(archive=bytes(archive)), message="MEMBER_TYPE")

    def test_unsupported_compression_and_expansion_bomb_are_refused(self):
        self.assert_refused(self.fresh(archive=tiny_zip(compression=zipfile.ZIP_BZIP2)), message="MEMBER_TYPE")
        for stage, cap in (("b2s2", 1024*1024), ("ba2", 16*1024*1024)):
            archive = tiny_zip(data=dict(DATA, **{"collect.log": b"z" * cap}))
            self.assert_refused(self.fresh(stage, archive), message="EXPANDED_SIZE_CAP")

    def test_existing_path_symlink_parent_and_overlap_are_refused_before_network(self):
        for what in ("output", "evidence"):
            f = self.fresh()
            f.args[what].mkdir()
            self.assert_refused(f, message="ALREADY_EXISTS")
            self.assertEqual(f.opened, [])
        f = self.fresh()
        link = f.root / "link"
        link.symlink_to(f.root, target_is_directory=True)
        self.assert_refused(f, output=link / "new", message="SYMLINK")
        self.assertEqual(f.opened, [])
        f = self.fresh()
        self.assert_refused(f, output=f.args["evidence"], message="PATHS_OVERLAP")
        f = self.fresh()
        self.assert_refused(f, output=f.root / ".." / "outside", message="PARENT_TRAVERSAL")

    def test_global_and_per_request_deadlines_include_body_and_output(self):
        f = self.fresh()
        now = [0.0]
        class Slow(Response):
            def read(self, size):
                now[0] += 10.01
                return super().read(size)
        values = f.responses()
        values[3] = Slow(f.archive)
        self.assert_refused(f, values, "REQUEST_WALL_BUDGET", clock=lambda: now[0])
        self.assertEqual(f.paused, [])
        f = self.fresh()
        now = [0.0]
        original = download.extract_checked
        def slow_extract(*args):
            result = original(*args)
            now[0] = 94.001
            return result
        with patch.object(download, "extract_checked", side_effect=slow_extract):
            self.assert_refused(f, message="TOTAL_WALL_BUDGET", clock=lambda: now[0])
        self.assertEqual(f.report()["status"], "FAILED")

    def test_late_success_receipt_is_replaced_by_failure(self):
        f = self.fresh()
        now = [0.0]
        original = download.write_report
        def late_write(evidence, report):
            original(evidence, report)
            if report["status"] == "PASS_TRANSPORT_ONLY":
                now[0] = 94.01
        with patch.object(download, "write_report", side_effect=late_write):
            self.assert_refused(f, message="TOTAL_WALL_BUDGET", clock=lambda: now[0])
        self.assertEqual(f.report()["status"], "FAILED")

    @unittest.skipUnless(hasattr(signal, "setitimer"), "POSIX hard-wall timer")
    def test_real_alarm_interrupts_blocked_response_body_without_network(self):
        f = self.fresh()
        class Blocked(Response):
            def read(self, size):
                time.sleep(0.1)
                return super().read(size)
        values = f.responses()
        values[3] = Blocked(f.archive)
        with patch.object(download, "REQUEST_SECONDS", 0.02):
            self.assert_refused(f, values, "REQUEST_WALL_BUDGET", alarms=True)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))


class WorkflowContractTests(unittest.TestCase):
    def test_only_two_explicit_stages_keep_original_upload_and_independent_reader(self):
        root = Path(__file__).resolve().parents[3]
        quality = (root / ".github/workflows/quality.yml").read_text("utf-8")
        self.assertEqual(quality.count("fe09_same_run_artifact_download.py"), 2)
        for stage, step, output, reader in (
            ("b2s2", "fe09_b2s2", "fe09-b2s2", "fe09_runtime_source_boundary.py s2"),
            ("ba2", "fe09_a2f0", "fe09-t3s2b1ba2", "fe09_b2s3_t3s2b1ba2_finite_retirement_qualification.py"),
        ):
            start = quality.index("        id: " + step + "_upload\n")
            end = quality.index("      - name: Independently", start)
            block = quality[start:end]
            for marker in ("id: " + step + "_readback", "GH_TOKEN: ${{ github.token }}",
                           "ARTIFACT_ID: ${{ steps." + step + "_upload.outputs.artifact-id }}",
                           "RUN_HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}",
                           "--stage " + stage, '--repository "$GITHUB_REPOSITORY"',
                           '--artifact-id "$ARTIFACT_ID" --run-id "$GITHUB_RUN_ID"',
                           '--run-attempt "$GITHUB_RUN_ATTEMPT" --run-head-sha "$RUN_HEAD_SHA"',
                           '--execution-source "$GITHUB_SHA"', "--output " + output + "-readback",
                           "--evidence " + output + "-transport", "retention-days: 30"):
                self.assertIn(marker, block)
            self.assertNotIn("actions/download-artifact", block)
            self.assertNotIn("continue-on-error", block)
            self.assertNotIn("overwrite:", block)
            self.assertIn(reader, quality[end:end+700])
        self.assertIn("python3 tests/validation/frontend_evolution/test_fe09_same_run_artifact_download.py",
                      (root / ".github/scripts/verify-docs-gate.sh").read_text("utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
