#!/usr/bin/env python3
"""Materialize the frozen I020 blind evidence archive without rerunning research."""
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
MANIFEST = ROOT / ".github/research/continuous-optimization/development-v4/i020-blind-baseline-invalid-durable-evidence-v1.json"
REVIEW = ROOT / ".github/research/continuous-optimization/development-v4/i020-vad-weak-start-requires-blend-v1-blind-review.json"
ARCHIVE_BRANCH = "automation/i020-durable-evidence-36304120808-36324803945"
PR_MARKER = "<!-- i020-durable-evidence-archive:v1 -->"
MAX_ZIP_BYTES = 64 * 1024 * 1024
EXPECTED_ROOT = "validation/research/evidence/i020-blind-baseline-invalid-36304120808-36324803945"
EXPECTED_SOURCE_RUN = 36304120808
EXPECTED_SOURCE_ARTIFACT = 10927016997
EXPECTED_RESUME_RUN = 36324803945
EXPECTED_RESUME_ARTIFACT = 10934232488


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


def _safe_relative(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def artifact_groups(manifest: dict) -> tuple[tuple[str, dict], ...]:
    return (
        ("source_partition_artifact", manifest["source_partition_artifact"]),
        ("same_partition_resume_artifact", manifest["same_partition_resume_artifact"]),
    )


def validate_frozen(manifest: dict, review: dict) -> None:
    require(manifest["schema_version"] == 1, "manifest schema drift")
    require(manifest["status"] == "FROZEN_ARCHIVE_MANIFEST", "archive manifest is not frozen")
    require(manifest["review_path"] == str(REVIEW.relative_to(ROOT)), "review path drift")
    require(manifest["required_review_status"] == "BLIND_BASELINE_INVALID_REVIEW_REQUIRED",
            "required review status drift")
    require(review["status"] == manifest["required_review_status"], "review status drift")
    require(review["decision"] == "BLIND_BASELINE_INVALID_REVIEW_REQUIRED", "review decision drift")
    require(review["terminal_candidate"] is False, "candidate unexpectedly terminalized")
    require(manifest["archive_root"] == EXPECTED_ROOT, "archive root drift")
    require(review["durable_evidence_plan"]["root"] == EXPECTED_ROOT, "review archive root drift")

    source = manifest["source_partition_artifact"]
    resume = manifest["same_partition_resume_artifact"]
    require(source["run_id"] == EXPECTED_SOURCE_RUN and source["artifact_id"] == EXPECTED_SOURCE_ARTIFACT,
            "source artifact identity drift")
    require(resume["run_id"] == EXPECTED_RESUME_RUN and resume["artifact_id"] == EXPECTED_RESUME_ARTIFACT,
            "resume artifact identity drift")
    blind = review["blind_partition_authority"]
    resumed = review["same_partition_resume"]
    require(source["run_id"] == blind["source_run_id"], "source run review mismatch")
    require(source["artifact_id"] == blind["source_artifact_id"], "source artifact review mismatch")
    require(source["artifact_digest"] == blind["source_artifact_digest"], "source digest review mismatch")
    require(resume["run_id"] == resumed["run_id"], "resume run review mismatch")
    require(resume["artifact_id"] == resumed["artifact_id"], "resume artifact review mismatch")
    require(resume["artifact_digest"] == resumed["artifact_digest"], "resume digest review mismatch")

    inv = manifest["invariants"]
    require(inv["visible_case_count"] == 130 and inv["blind_case_count"] == 30, "partition count drift")
    require(inv["blind_key_fingerprint"] == "ebeec484da932ee7", "blind key fingerprint drift")
    require(inv["partition_changed"] is False and inv["new_holdout_key_generated"] is False,
            "partition identity drift")
    require(inv["candidate_or_policy_changed"] is False, "candidate/policy drift")
    require(inv["decision"] == review["decision"], "manifest/review decision mismatch")
    require(inv["terminal_candidate"] is False, "manifest terminal candidate drift")

    boundary = manifest["authority_boundary"]
    require(boundary["archive_copy_only"] is True, "archive must remain copy-only")
    for key, value in boundary.items():
        if key != "archive_copy_only":
            require(value is False, "archive authority escalation: " + key)
    for key in (
        "candidate_terminalized", "candidate_qualified", "candidate_rejected",
        "candidate_advancement_authorized", "requalification_authorized", "rerun_authorized",
        "repartition_authorized", "policy_relaxation_authorized", "source_merge_authorized",
        "shipping_authority", "hil_authority", "product_certification_authority",
        "release_authority", "automatic_main_mutation",
    ):
        require(review["authority_boundary"][key] is False, "review authority escalation: " + key)

    members = []
    for group_name, group in artifact_groups(manifest):
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", group["artifact_digest"]) is not None,
                "invalid artifact digest: " + group_name)
        require(isinstance(group["members"], list) and group["members"], "empty member list: " + group_name)
        for item in group["members"]:
            require(_safe_relative(item["source_path"]), "unsafe source path")
            require(_safe_relative(item["archive_name"]) and "/" not in item["archive_name"],
                    "archive member must be one flat safe name")
            require(type(item["bytes"]) is int and 0 < item["bytes"] <= 2_000_000, "invalid member size")
            require(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None, "invalid member sha256")
            members.append(item["archive_name"])
    require(len(members) == 11 and len(set(members)) == 11, "frozen archive membership drift")
    require(set(review["durable_evidence_plan"]["source_partition_members"]) ==
            {item["archive_name"] for item in source["members"]}, "source durable plan mismatch")
    require(set(review["durable_evidence_plan"]["resume_members"]) ==
            {item["archive_name"] for item in resume["members"]}, "resume durable plan mismatch")


def select_members(zip_bytes: bytes, group: dict) -> dict[str, bytes]:
    require(len(zip_bytes) <= MAX_ZIP_BYTES, "artifact ZIP exceeds bounded size")
    expected_zip = group["artifact_digest"].removeprefix("sha256:")
    require(digest(zip_bytes) == expected_zip, "artifact ZIP digest mismatch")
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        infos = archive.infolist()
        names = [entry.filename for entry in infos]
        require(len(names) == len(set(names)), "duplicate ZIP member")
        for entry in infos:
            require(_safe_relative(entry.filename), "unsafe ZIP path")
        info_by_name = {entry.filename: entry for entry in infos}
        for item in group["members"]:
            name = item["source_path"]
            require(name in info_by_name, "missing frozen member: " + name)
            info = info_by_name[name]
            require(not info.is_dir(), "frozen member became directory: " + name)
            require(info.file_size == item["bytes"], "frozen member size mismatch: " + name)
            data = archive.read(info)
            require(len(data) == item["bytes"], "frozen member read size mismatch: " + name)
            require(digest(data) == item["sha256"], "frozen member digest mismatch: " + name)
            if item["archive_name"].endswith(".json"):
                parsed = parse(data)
                require(isinstance(parsed, (dict, list)), "JSON member has unexpected scalar root")
            result[item["archive_name"]] = data
    require(set(result) == {item["archive_name"] for item in group["members"]},
            "selected archive membership mismatch")
    return result


def render_archive(manifest: dict, source_zip: bytes, resume_zip: bytes) -> dict[str, bytes]:
    root = manifest["archive_root"]
    selected = {}
    selected.update(select_members(source_zip, manifest["source_partition_artifact"]))
    resume = select_members(resume_zip, manifest["same_partition_resume_artifact"])
    require(not (set(selected) & set(resume)), "duplicate archive filename across artifacts")
    selected.update(resume)
    return {root + "/" + name: data for name, data in sorted(selected.items())}


def validate_committed_archive(root: Path, manifest: dict, files: dict[str, bytes]) -> bool:
    archive_root = root / manifest["archive_root"]
    if not archive_root.exists():
        return False
    require(archive_root.is_dir(), "archive root is not a directory")
    expected = {Path(path).relative_to(manifest["archive_root"]).as_posix() for path in files}
    actual = {
        path.relative_to(archive_root).as_posix()
        for path in archive_root.rglob("*") if path.is_file()
    }
    require(actual == expected, "committed archive membership drift")
    for path, data in files.items():
        require((root / path).read_bytes() == data, "committed archive content drift: " + path)
    return True


class GitHub:
    def __init__(self, repo: str):
        self.repo = repo

    def api(self, path: str, *, writer: bool = False, method: str | None = None,
            payload=None, binary: bool = False):
        env = os.environ.copy()
        if writer:
            require(bool(env.get("GH_WRITE_TOKEN")), "BLOCKED_AUTOMATION_CREDENTIAL: no publishing token")
            env["GH_TOKEN"] = env["GH_WRITE_TOKEN"]
        else:
            require(bool(env.get("GH_TOKEN")), "missing read token")
        args = ["gh", "api", "--hostname", "github.com"]
        if method is not None:
            args += ["--method", method]
        args += ["repos/" + self.repo + "/" + path]
        input_bytes = None
        if payload is not None:
            if method is None:
                args[3:3] = ["--method", "POST"]
            args += ["--input", "-"]
            input_bytes = encoded(payload)
        process = subprocess.run(
            args, input=input_bytes, env=env, capture_output=True, timeout=120, check=False
        )
        if process.returncode != 0:
            stderr = process.stderr.decode("utf-8", errors="replace")
            match = re.search(r"\(HTTP ([1-5][0-9]{2})\)", stderr)
            code = match.group(1) if match else "unknown"
            raise ValueError("GitHub API request failed: HTTP " + code)
        if binary:
            return process.stdout
        return parse(process.stdout)

    def main(self) -> str:
        return self.api("git/ref/heads/main")["object"]["sha"]

    def artifact_zip(self, artifact_id: int, run_id: int, head_sha: str, expected_digest: str) -> bytes:
        artifact = self.api("actions/artifacts/" + str(artifact_id))
        require(artifact["id"] == artifact_id, "artifact id mismatch")
        require(artifact.get("expired") is False, "artifact expired")
        workflow_run = artifact.get("workflow_run") or {}
        require(workflow_run.get("id") == run_id, "artifact run id mismatch")
        require(workflow_run.get("head_sha") == head_sha, "artifact head SHA mismatch")
        if artifact.get("digest"):
            require(artifact["digest"] == expected_digest, "artifact API digest mismatch")
        data = self.api("actions/artifacts/" + str(artifact_id) + "/zip", binary=True)
        require(len(data) <= MAX_ZIP_BYTES, "artifact ZIP exceeds bounded size")
        require("sha256:" + digest(data) == expected_digest, "downloaded artifact digest mismatch")
        return data


def _git_blob(api: GitHub, data: bytes) -> str:
    response = api.api(
        "git/blobs", writer=True, method="POST",
        payload={"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"},
    )
    return response["sha"]


def publish_archive_pr(api: GitHub, manifest: dict, files: dict[str, bytes], main: str) -> dict:
    require(api.main() == main, "main moved before archive publication")
    base_commit = api.api("git/commits/" + main)
    tree_items = []
    for path, data in sorted(files.items()):
        tree_items.append({
            "path": path, "mode": "100644", "type": "blob", "sha": _git_blob(api, data)
        })
    tree = api.api(
        "git/trees", writer=True, method="POST",
        payload={"base_tree": base_commit["tree"]["sha"], "tree": tree_items},
    )
    require(api.main() == main, "main moved while preparing archive tree")

    refs = api.api("git/matching-refs/heads/" + ARCHIVE_BRANCH)
    exact = [ref for ref in refs if ref["ref"] == "refs/heads/" + ARCHIVE_BRANCH]
    require(len(exact) <= 1, "ambiguous archive branch")
    if exact:
        commit = api.api("git/commits/" + exact[0]["object"]["sha"])
        require(commit["tree"]["sha"] == tree["sha"], "existing archive branch tree drift")
        require([parent["sha"] for parent in commit["parents"]] == [main],
                "existing archive branch base drift")
        commit_sha = exact[0]["object"]["sha"]
    else:
        commit = api.api(
            "git/commits", writer=True, method="POST",
            payload={
                "message": "research(i020): archive frozen blind baseline-invalid evidence",
                "tree": tree["sha"], "parents": [main],
            },
        )
        commit_sha = commit["sha"]
        api.api(
            "git/refs", writer=True, method="POST",
            payload={"ref": "refs/heads/" + ARCHIVE_BRANCH, "sha": commit_sha},
        )

    owner = api.repo.split("/", 1)[0]
    prs = api.api("pulls?state=all&head=" + owner + ":" + ARCHIVE_BRANCH + "&base=main&per_page=100")
    require(len(prs) <= 1, "ambiguous archive PR history")
    if prs:
        pr = prs[0]
        require(pr["state"] == "open" or pr.get("merged_at"), "archive PR closed without merge")
        return {"status": "ARCHIVE_PR_EXISTS", "pr": pr["number"], "head": commit_sha}

    body = (
        PR_MARKER + "\n\n"
        "Copy-only durable archive of the already-consumed I020 blind partition and same-partition resume evidence.\n\n"
        "Source artifact " + str(EXPECTED_SOURCE_ARTIFACT) + " / run " + str(EXPECTED_SOURCE_RUN) +
        " and resume artifact " + str(EXPECTED_RESUME_ARTIFACT) + " / run " + str(EXPECTED_RESUME_RUN) +
        " were re-downloaded from trusted main and verified against the frozen manifest. "
        "Only the 11 manifest-listed text members are committed; PCM/public-corpus payloads are excluded.\n\n"
        "This PR does not rerun, repartition, requalify or reclassify I020. "
        "The candidate remains BLIND_BASELINE_INVALID_REVIEW_REQUIRED and gains no shipping, source-merge, HIL, "
        "Product Certification or release authority."
    )
    pr = api.api(
        "pulls", writer=True, method="POST",
        payload={
            "title": "research(i020): archive frozen blind evidence bytes",
            "head": ARCHIVE_BRANCH, "base": "main", "body": body,
        },
    )
    return {"status": "ARCHIVE_PR_CREATED", "pr": pr["number"], "head": commit_sha}


def collect(api: GitHub, manifest: dict, review: dict) -> dict[str, bytes]:
    blind = review["blind_partition_authority"]
    resumed = review["same_partition_resume"]
    source = manifest["source_partition_artifact"]
    resume = manifest["same_partition_resume_artifact"]
    source_zip = api.artifact_zip(
        source["artifact_id"], source["run_id"], blind["source_run_head_sha"], source["artifact_digest"]
    )
    resume_zip = api.artifact_zip(
        resume["artifact_id"], resume["run_id"], resumed["run_head_sha"], resume["artifact_digest"]
    )
    return render_archive(manifest, source_zip, resume_zip)


def check_repository() -> dict:
    manifest = parse(MANIFEST.read_bytes())
    review = parse(REVIEW.read_bytes())
    validate_frozen(manifest, review)
    archive_root = ROOT / manifest["archive_root"]
    if not archive_root.exists():
        return {"status": "FROZEN_MANIFEST_READY_FOR_COPY", "archive_root": manifest["archive_root"]}
    expected = {}
    for _, group in artifact_groups(manifest):
        for item in group["members"]:
            path = manifest["archive_root"] + "/" + item["archive_name"]
            data = (ROOT / path).read_bytes()
            require(len(data) == item["bytes"], "committed archive size drift: " + path)
            require(digest(data) == item["sha256"], "committed archive digest drift: " + path)
            expected[path] = data
    validate_committed_archive(ROOT, manifest, expected)
    return {"status": "DURABLE_ARCHIVE_PRESENT_AND_VERIFIED", "members": len(expected)}


def reconcile(output: Path) -> dict:
    manifest = parse(MANIFEST.read_bytes())
    review = parse(REVIEW.read_bytes())
    validate_frozen(manifest, review)
    require(os.environ.get("GITHUB_REPOSITORY") == "jiying2007/audio-pipeline", "foreign repository")
    require(os.environ.get("GITHUB_REF") == "refs/heads/main", "publisher requires trusted main")
    require(os.environ.get("GITHUB_EVENT_NAME") in {"push", "workflow_dispatch"}, "untrusted publish event")
    api = GitHub(os.environ["GITHUB_REPOSITORY"])
    main = api.main()
    checkout = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(checkout == main, "checkout is not live main")

    if (ROOT / manifest["archive_root"]).exists():
        result = check_repository()
        result["main"] = main
        return result

    files = collect(api, manifest, review)
    output.mkdir(parents=True, exist_ok=True)
    receipt = {
        path: {"bytes": len(data), "sha256": digest(data)}
        for path, data in sorted(files.items())
    }
    (output / "verified-members.json").write_bytes(encoded(receipt))
    result = publish_archive_pr(api, manifest, files, main)
    result["verified_members"] = len(files)
    result["verified_bytes"] = sum(len(data) for data in files.values())
    result["source_main"] = main
    return result


def self_test() -> None:
    payload = b'{"ok": true}\n'
    ignored = b"do-not-archive"
    group = {
        "artifact_digest": "",
        "members": [{
            "source_path": "public/wanted.json",
            "archive_name": "wanted.json",
            "bytes": len(payload),
            "sha256": digest(payload),
        }],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("public/wanted.json", payload)
        archive.writestr("public/audio.pcm", ignored)
    data = buffer.getvalue()
    group["artifact_digest"] = "sha256:" + digest(data)
    selected = select_members(data, group)
    require(selected == {"wanted.json": payload}, "allowlist copy failed")
    bad = dict(group)
    bad["members"] = [dict(group["members"][0], sha256="0" * 64)]
    try:
        select_members(data, bad)
    except ValueError as exc:
        require("digest mismatch" in str(exc), "wrong self-test failure")
    else:
        raise AssertionError("member digest corruption was accepted")
    print("i020 durable archive self-test: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("i020-durable-archive-out"))
    args = parser.parse_args()
    require(sum((args.self_test, args.check, args.publish)) == 1, "choose exactly one mode")
    if args.self_test:
        self_test()
        return
    if args.check:
        print(json.dumps(check_repository(), sort_keys=True))
        return
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        result = reconcile(args.output)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        result = {"status": "BLOCKED", "error": str(exc)}
        (args.output / "status.json").write_bytes(encoded(result))
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(1) from None
    (args.output / "status.json").write_bytes(encoded(result))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
