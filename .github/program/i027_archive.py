#!/usr/bin/env python3
"""Publish the frozen invalid I027 evidence bytes without rerunning research."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CLOSURE = ROOT / (
    ".github/research/continuous-optimization/development-v4/"
    "i027-ns-upstream-reference-ready-component-counterfactual-v1-result.json"
)
ARCHIVE_ROOT = "validation/research/evidence/i027-36570600341"
ARCHIVE_BRANCH = "automation/i027-evidence-36570600341"
PR_MARKER = "<!-- i027-evidence-archive:v1 -->"
EXPECTED_RUN = 36570600341
EXPECTED_ARTIFACT = 11034169094
EXPECTED_HEAD = "a62610fa3005f369e7c30dcb1db7bdfbb82b4a55"
EXPECTED_ZIP_SHA256 = "8b76658586686485414305022b6a6f25cf8d4e77c61d3af188f386e83f35cc1f"
EXPECTED_ZIP_BYTES = 47994
MAX_ZIP_BYTES = 2_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def parse(data: bytes | str):
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return json.loads(data)


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        bool(name)
        and not path.is_absolute()
        and ".." not in path.parts
        and len(path.parts) == 2
        and path.parts[0] == "evidence"
    )


def validate_closure(closure: dict) -> dict[str, str]:
    require(closure["schema_version"] == 1, "closure schema drift")
    require(
        closure["investigation_id"]
        == "i027-ns-upstream-reference-ready-component-counterfactual-v1",
        "closure investigation drift",
    )
    require(
        closure["status"] == "CLOSED_INVALID_DIAGNOSTIC_ONLY",
        "I027 invalid closure is not terminal",
    )
    require(
        closure["authority"] == "CANDIDATE_ZERO_CAUSAL_DIAGNOSTIC_ONLY",
        "closure authority drift",
    )
    require(
        closure["decision"] == "I027_INPUT_INVALID_REVIEW_REQUIRED",
        "raw decision drift",
    )
    require(
        closure["reviewed_decision"]
        == "REFERENCE_READY_SPEECH_COVERAGE_GATE_FAILED_NO_COMPONENT_CONCLUSION_NO_CANDIDATE",
        "reviewed decision drift",
    )
    require(
        closure["fresh_authority"]
        == {
            "seeds": [1101307, 1111307, 1121307],
            "diagnostic_execution_consumed": 1,
            "candidate_budget_consumed": 0,
            "confirmation_budget_consumed": 0,
            "rerun_allowed": False,
        },
        "fresh authority drift",
    )
    require(
        closure["shipping_mirror"]
        == {
            "max_ns_upstream_gap_delta": 0,
            "max_vad_probability_delta": 0,
            "vad_active_mismatch_frames": 0,
        },
        "shipping mirror drift",
    )
    invalid = closure["invalidity_review"]
    require(
        invalid["invalid_reasons"]
        == [
            "domain_eligible_fraction:cafeteria:speech",
            "global_eligible_fraction:speech",
        ],
        "invalid reason drift",
    )
    require(invalid["target_cases"] == 168, "target case count drift")
    require(
        invalid["target_cases_with_any_eligible_target"] == 168,
        "eligible target-case coverage drift",
    )
    require(
        invalid["global"]["speech"]["eligible_fraction"]
        == 0.7449760145209386,
        "global speech eligibility drift",
    )
    require(
        invalid["global"]["speech"]["required_fraction"] == 0.75,
        "global speech gate drift",
    )
    require(
        invalid["cafeteria_speech"]["eligible_fraction"]
        == 0.5537084398976982,
        "cafeteria speech eligibility drift",
    )
    require(
        invalid["cafeteria_speech"]["required_fraction"] == 0.60,
        "cafeteria speech gate drift",
    )
    require(
        invalid["denominator_correction_worked"] is True,
        "eligible-only denominator closure drift",
    )
    require(
        invalid["secondary_scenario_snr_reverb_coverage_gates_passed"] is True,
        "secondary coverage review drift",
    )
    require(
        closure["invalid_observations"]["interpretation_allowed"] is False,
        "invalid fractions became interpretable",
    )
    require(
        all(value is False for value in closure["authority_boundary"].values()),
        "closure authority escalation",
    )
    follow = closure["proposed_followup_hypothesis"]
    require(
        follow["id"]
        == "i028-ns-upstream-reference-readiness-temporal-decomposition-v1",
        "follow-up identity drift",
    )
    require(
        follow["authority"] == "CANDIDATE_ZERO_DIAGNOSTIC_ONLY",
        "follow-up authority drift",
    )

    execution = closure["authoritative_execution"]
    require(execution["run_id"] == EXPECTED_RUN, "diagnostic run drift")
    require(execution["run_attempt"] == 1, "diagnostic attempt drift")
    require(execution["head_sha"] == EXPECTED_HEAD, "diagnostic head drift")
    require(execution["artifact_id"] == EXPECTED_ARTIFACT, "artifact id drift")
    require(
        execution["artifact_name"]
        == "i027-ns-upstream-reference-ready-component-36570600341",
        "artifact name drift",
    )
    require(
        execution["artifact_size_bytes"] == EXPECTED_ZIP_BYTES,
        "artifact size drift",
    )
    require(
        execution["artifact_sha256"] == EXPECTED_ZIP_SHA256,
        "artifact digest drift",
    )
    expected = execution["member_sha256"]
    require(
        isinstance(expected, dict) and len(expected) == 11,
        "archive member map drift",
    )
    required = {"SHA256SUMS", "contract.json", "result.json", "summary.json"}
    require(required.issubset(expected), "required archive members missing")
    for name, sha in expected.items():
        require(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) is not None,
            "unsafe archive filename",
        )
        require(
            re.fullmatch(r"[0-9a-f]{64}", sha) is not None,
            "invalid archive member digest",
        )
    require(
        closure["original_result_path"] == ARCHIVE_ROOT + "/result.json",
        "archive root/result binding drift",
    )
    return expected


def select_members(zip_bytes: bytes, expected: dict[str, str]) -> dict[str, bytes]:
    require(
        len(zip_bytes) == EXPECTED_ZIP_BYTES and len(zip_bytes) <= MAX_ZIP_BYTES,
        "artifact ZIP size mismatch",
    )
    require(digest(zip_bytes) == EXPECTED_ZIP_SHA256, "artifact ZIP digest mismatch")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        infos = archive.infolist()
        names = [entry.filename for entry in infos]
        require(len(names) == len(set(names)), "duplicate ZIP member")
        require(all(safe_member(name) for name in names), "unsafe ZIP member")
        expected_paths = {"evidence/" + name for name in expected}
        require(set(names) == expected_paths, "artifact ZIP membership drift")
        members = {}
        for info in infos:
            require(
                not info.is_dir() and not info.flag_bits & 1,
                "non-regular/encrypted ZIP member",
            )
            name = PurePosixPath(info.filename).name
            data = archive.read(info)
            require(
                digest(data) == expected[name],
                "member digest mismatch: " + name,
            )
            members[name] = data

    sums = {}
    for line in members["SHA256SUMS"].decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        require(match is not None, "invalid SHA256SUMS line")
        sha, name = match.groups()
        require(name not in sums, "duplicate SHA256SUMS entry")
        sums[name] = sha
    require(
        set(sums) == set(expected) - {"SHA256SUMS"},
        "SHA256SUMS membership drift",
    )
    for name, sha in sums.items():
        require(
            sha == expected[name] and digest(members[name]) == sha,
            "internal member digest mismatch: " + name,
        )
    for name in ("contract.json", "materialization.json", "result.json", "summary.json"):
        require(isinstance(parse(members[name]), dict), "JSON member invalid: " + name)
    require(
        members["evaluate.exit-code"] == b"2\n",
        "invalid evaluator exit code drift",
    )
    require(
        members["evaluate.stderr"] == b"",
        "invalid evaluator stderr is not empty",
    )
    raw = parse(members["result.json"])
    require(
        raw["decision"] == "I027_INPUT_INVALID_REVIEW_REQUIRED",
        "artifact raw decision drift",
    )
    require(
        raw["invalid_reasons"]
        == [
            "domain_eligible_fraction:cafeteria:speech",
            "global_eligible_fraction:speech",
        ],
        "artifact invalid reason drift",
    )
    require(
        raw["global"]["eligible_target_fraction"]["speech"]
        == 0.7449760145209386,
        "artifact global speech eligibility drift",
    )
    require(
        raw["slices"]["noise_domain:cafeteria"]["eligible_target_fraction"]["speech"]
        == 0.5537084398976982,
        "artifact cafeteria speech eligibility drift",
    )
    require(
        raw["interpretation_boundary"][
            "excluded_targets_enter_counterfactual_denominator"
        ] is False,
        "artifact denominator boundary drift",
    )
    return members


def rendered_files(members: dict[str, bytes]) -> dict[str, bytes]:
    return {
        ARCHIVE_ROOT + "/" + name: data
        for name, data in sorted(members.items())
    }


def check_repository(expected: dict[str, str]) -> dict:
    root = ROOT / ARCHIVE_ROOT
    if not root.exists():
        return {
            "status": "TRUSTED_INVALID_CLOSURE_READY_FOR_ARCHIVE",
            "archive_root": ARCHIVE_ROOT,
        }
    require(root.is_dir(), "archive root is not directory")
    actual = sorted(path.name for path in root.iterdir() if path.is_file())
    require(actual == sorted(expected), "committed archive membership drift")
    for name, sha in expected.items():
        require(
            digest((root / name).read_bytes()) == sha,
            "committed archive digest drift: " + name,
        )
    return {
        "status": "DURABLE_INVALID_ARCHIVE_PRESENT_AND_VERIFIED",
        "members": len(expected),
    }


class GitHub:
    def __init__(self, repo: str):
        self.repo = repo

    def api(self, path: str, *, writer=False, method=None, payload=None, binary=False):
        env = os.environ.copy()
        if writer:
            require(
                bool(env.get("GH_WRITE_TOKEN")),
                "BLOCKED_AUTOMATION_CREDENTIAL: no publishing token",
            )
            env["GH_TOKEN"] = env["GH_WRITE_TOKEN"]
        else:
            require(bool(env.get("GH_TOKEN")), "missing read token")
        args = ["gh", "api", "--hostname", "github.com"]
        if method:
            args += ["--method", method]
        args += ["repos/" + self.repo + "/" + path]
        input_bytes = None
        if payload is not None:
            if not method:
                args[3:3] = ["--method", "POST"]
            args += ["--input", "-"]
            input_bytes = encoded(payload)
        process = subprocess.run(
            args,
            input=input_bytes,
            env=env,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if process.returncode:
            stderr = process.stderr.decode("utf-8", errors="replace")
            match = re.search(r"\(HTTP ([1-5][0-9]{2})\)", stderr)
            raise ValueError(
                "GitHub API request failed: HTTP "
                + (match.group(1) if match else "unknown")
            )
        if binary:
            return process.stdout
        return parse(process.stdout)

    def main(self) -> str:
        return self.api("git/ref/heads/main")["object"]["sha"]

    def artifact_zip(self) -> bytes:
        artifact = self.api("actions/artifacts/" + str(EXPECTED_ARTIFACT))
        require(artifact["id"] == EXPECTED_ARTIFACT, "artifact identity mismatch")
        require(artifact.get("expired") is False, "artifact expired")
        run = artifact.get("workflow_run") or {}
        require(
            run.get("id") == EXPECTED_RUN and run.get("head_sha") == EXPECTED_HEAD,
            "artifact run binding mismatch",
        )
        if artifact.get("digest"):
            require(
                artifact["digest"] == "sha256:" + EXPECTED_ZIP_SHA256,
                "artifact API digest mismatch",
            )
        data = self.api(
            "actions/artifacts/" + str(EXPECTED_ARTIFACT) + "/zip",
            binary=True,
        )
        require(
            len(data) == EXPECTED_ZIP_BYTES,
            "downloaded ZIP size mismatch",
        )
        require(
            digest(data) == EXPECTED_ZIP_SHA256,
            "downloaded ZIP digest mismatch",
        )
        return data


def git_blob(api: GitHub, data: bytes) -> str:
    return api.api(
        "git/blobs",
        writer=True,
        method="POST",
        payload={
            "content": base64.b64encode(data).decode("ascii"),
            "encoding": "base64",
        },
    )["sha"]


def publish(api: GitHub, files: dict[str, bytes], main: str) -> dict:
    require(api.main() == main, "main moved before archive publication")
    base = api.api("git/commits/" + main)
    tree_items = [
        {
            "path": path,
            "mode": "100644",
            "type": "blob",
            "sha": git_blob(api, data),
        }
        for path, data in sorted(files.items())
    ]
    tree = api.api(
        "git/trees",
        writer=True,
        method="POST",
        payload={"base_tree": base["tree"]["sha"], "tree": tree_items},
    )
    require(api.main() == main, "main moved while preparing archive tree")
    refs = api.api("git/matching-refs/heads/" + ARCHIVE_BRANCH)
    exact = [
        ref for ref in refs
        if ref["ref"] == "refs/heads/" + ARCHIVE_BRANCH
    ]
    require(len(exact) <= 1, "ambiguous archive branch")
    if exact:
        commit = api.api("git/commits/" + exact[0]["object"]["sha"])
        require(
            commit["tree"]["sha"] == tree["sha"],
            "existing archive tree drift",
        )
        require(
            [parent["sha"] for parent in commit["parents"]] == [main],
            "existing archive branch base drift",
        )
        commit_sha = exact[0]["object"]["sha"]
    else:
        commit = api.api(
            "git/commits",
            writer=True,
            method="POST",
            payload={
                "message": "research(i027): archive verified invalid diagnostic evidence",
                "tree": tree["sha"],
                "parents": [main],
            },
        )
        commit_sha = commit["sha"]
        api.api(
            "git/refs",
            writer=True,
            method="POST",
            payload={
                "ref": "refs/heads/" + ARCHIVE_BRANCH,
                "sha": commit_sha,
            },
        )

    owner = api.repo.split("/", 1)[0]
    prs = api.api(
        "pulls?state=all&head=" + owner + ":" + ARCHIVE_BRANCH
        + "&base=main&per_page=100"
    )
    require(len(prs) <= 1, "ambiguous archive PR history")
    if prs:
        pr = prs[0]
        require(
            pr["state"] == "open" or pr.get("merged_at"),
            "archive PR closed without merge",
        )
        return {
            "status": "ARCHIVE_PR_EXISTS",
            "pr": pr["number"],
            "head": commit_sha,
        }

    body = (
        PR_MARKER + "\n\n"
        "Copy-only durable archive of the already-consumed invalid I027 "
        "reference-ready component diagnostic evidence.\n\n"
        "Trusted closure on main binds run 36570600341, artifact 11034169094, "
        "ZIP SHA256 " + EXPECTED_ZIP_SHA256 + ", and all 11 member SHA256 values. "
        "This PR contains only those original artifact bytes under "
        + ARCHIVE_ROOT + ".\n\n"
        "The authoritative evaluator decision is I027_INPUT_INVALID_REVIEW_REQUIRED "
        "because preregistered speech eligibility coverage failed. No invalid fraction is "
        "promoted into a component conclusion. No research execution is rerun. "
        "No seed, dataset, component, mapping, candidate, threshold, tracker alpha, "
        "shipping source, HIL, Product Certification or release authority changes."
    )
    pr = api.api(
        "pulls",
        writer=True,
        method="POST",
        payload={
            "title": "research(i027): archive invalid readiness diagnostic evidence",
            "head": ARCHIVE_BRANCH,
            "base": "main",
            "body": body,
        },
    )
    return {
        "status": "ARCHIVE_PR_CREATED",
        "pr": pr["number"],
        "head": commit_sha,
    }


def reconcile(output: Path) -> dict:
    closure = parse(CLOSURE.read_bytes())
    expected = validate_closure(closure)
    require(
        os.environ.get("GITHUB_REPOSITORY") == "jiying2007/audio-pipeline",
        "foreign repository",
    )
    require(
        os.environ.get("GITHUB_REF") == "refs/heads/main",
        "publisher requires trusted main",
    )
    require(
        os.environ.get("GITHUB_EVENT_NAME") == "push",
        "publisher requires trusted main push",
    )
    api = GitHub(os.environ["GITHUB_REPOSITORY"])
    main = api.main()
    checkout = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    require(checkout == main, "checkout is not live main")
    if (ROOT / ARCHIVE_ROOT).exists():
        result = check_repository(expected)
        result["main"] = main
        return result

    members = select_members(api.artifact_zip(), expected)
    files = rendered_files(members)
    output.mkdir(parents=True, exist_ok=True)
    (output / "verified-members.json").write_bytes(encoded({
        path: {"bytes": len(data), "sha256": digest(data)}
        for path, data in sorted(files.items())
    }))
    result = publish(api, files, main)
    result.update({
        "verified_members": len(files),
        "verified_bytes": sum(len(data) for data in files.values()),
        "source_main": main,
    })
    return result


def self_test() -> None:
    payload = (
        b'{"decision":"I027_INPUT_INVALID_REVIEW_REQUIRED",'
        b'"invalid_reasons":["domain_eligible_fraction:cafeteria:speech",'
        b'"global_eligible_fraction:speech"],'
        b'"global":{"eligible_target_fraction":{"speech":0.7449760145209386}},'
        b'"slices":{"noise_domain:cafeteria":{"eligible_target_fraction":'
        b'{"speech":0.5537084398976982}}},'
        b'"interpretation_boundary":'
        b'{"excluded_targets_enter_counterfactual_denominator":false}}\n'
    )
    sums = digest(payload).encode() + b"  result.json\n"
    expected = {
        "SHA256SUMS": digest(sums),
        "result.json": digest(payload),
        "contract.json": digest(b"{}\n"),
        "summary.json": digest(b"{}\n"),
        "materialization.json": digest(b"{}\n"),
        "build-info.txt": digest(b"x\n"),
        "corpora.sha256": digest(b"x\n"),
        "evaluate.exit-code": digest(b"2\n"),
        "evaluate.stderr": digest(b""),
        "evaluate.stdout": digest(b"x\n"),
        "probe.sha256": digest(b"x\n"),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in {
            "SHA256SUMS": sums,
            "result.json": payload,
            "contract.json": b"{}\n",
            "summary.json": b"{}\n",
            "materialization.json": b"{}\n",
            "build-info.txt": b"x\n",
            "corpora.sha256": b"x\n",
            "evaluate.exit-code": b"2\n",
            "evaluate.stderr": b"",
            "evaluate.stdout": b"x\n",
            "probe.sha256": b"x\n",
        }.items():
            archive.writestr("evidence/" + name, data)
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
        assert set(archive.namelist()) == {
            "evidence/" + name for name in expected
        }
    assert expected["result.json"] == digest(payload)
    print("i027 invalid evidence archive self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("i027-archive-out"),
    )
    args = parser.parse_args()
    require(
        sum((args.self_test, args.check, args.publish)) == 1,
        "choose exactly one mode",
    )
    if args.self_test:
        self_test()
        return 0
    closure = parse(CLOSURE.read_bytes())
    expected = validate_closure(closure)
    if args.check:
        print(json.dumps(check_repository(expected), sort_keys=True))
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        result = reconcile(args.output)
        rc = 0
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
    ) as exc:
        result = {"status": "BLOCKED", "error": str(exc)}
        rc = 1
    (args.output / "status.json").write_bytes(encoded(result))
    print(json.dumps(result, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
