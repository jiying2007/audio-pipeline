#!/usr/bin/env python3
"""Publish exact consumed I033 evidence bytes without rerunning research."""

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

ROOT=Path(__file__).resolve().parents[2]
CLOSURE=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i033-ns-vad-causal-noise-delta-alignment-v1-result.json"
)
ARCHIVE_ROOT="validation/research/evidence/i033-36719045384"
ARCHIVE_BRANCH="automation/i033-evidence-36719045384"
EXPECTED_RUN=36719045384
EXPECTED_ARTIFACT=11099050975
EXPECTED_HEAD="60267394933898f517ff6dd5cec49d8345bf07d0"
EXPECTED_ZIP_SHA256="9a2a66cfff362e201a4c598c96c322b7b5497958dfb15d51a5ebc911032ba734"
EXPECTED_ZIP_BYTES=26775
MAX_ZIP_BYTES=2_000_000


def require(condition,message):
    if not condition:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n").encode()


def parse(data: bytes | str):
    if isinstance(data,bytes):
        data=data.decode("utf-8")
    return json.loads(data)


def safe_member(name: str) -> bool:
    path=PurePosixPath(name)
    return (
        bool(name)
        and not path.is_absolute()
        and ".." not in path.parts
        and len(path.parts)==2
        and path.parts[0]=="evidence"
    )


def validate_closure(closure: dict) -> dict[str,str]:
    require(closure["schema_version"]==1,"closure schema drift")
    require(
        closure["investigation_id"]=="i033-ns-vad-causal-noise-delta-alignment-v1",
        "closure investigation drift",
    )
    require(closure["status"]=="CLOSED_DIAGNOSTIC_ONLY",
            "I033 closure is not terminal")
    require(closure["authority"]=="CANDIDATE_ZERO_DIAGNOSTIC_ONLY",
            "closure authority drift")
    require(
        closure["decision"]
        =="NS_VAD_CAUSAL_NOISE_DELTA_ALIGNMENT_DECOMPOSED_REVIEW_REQUIRED",
        "raw decision drift",
    )
    require(
        closure["reviewed_decision"]
        =="RELATIVE_NS_TO_POST_NS_NOISE_DELTA_ALIGNMENT_NOT_SUPPORTED_NO_REFRESH_MAPPING_OR_SOURCE_CANDIDATE",
        "reviewed decision drift",
    )
    require(
        closure["fresh_authority"]=={
            "target_seeds":[1701307,1711307,1721307,1731307,1741307,1751307],
            "diagnostic_execution_consumed":1,
            "candidate_budget_consumed":0,
            "confirmation_budget_consumed":0,
            "rerun_allowed":False,
        },
        "fresh authority drift",
    )
    require(
        closure["shipping_mirror"]=={
            "max_ns_upstream_gap_delta":0,
            "max_vad_probability_delta":0,
            "vad_active_mismatch_frames":0,
        },
        "shipping mirror drift",
    )
    coverage=closure["coverage_review"]
    require(
        coverage["target_cases"]==252
        and coverage["causal_target_cases"]==143
        and coverage["causal_anchor_cases"]==39
        and coverage["benchmarkable_anchor_cases"]==39,
        "coverage count drift",
    )
    require(coverage["causal_anchor_coverage"]>=0.25,
            "causal anchor coverage drift")
    require(coverage["post_target_benchmark_coverage"]>=0.8,
            "post-target benchmark coverage drift")
    delta=closure["delta_alignment_review"]
    require(delta["cases"]==39,"delta population drift")
    require(delta["supported"] is False,"relative delta unexpectedly promoted")
    require(
        delta["median_absolute_delta_error_db"]
        >delta["preregistered_maximum_median_absolute_delta_error_db"],
        "median rejection drift",
    )
    require(
        delta["p90_absolute_delta_error_db"]
        >delta["preregistered_maximum_p90_absolute_delta_error_db"],
        "p90 rejection drift",
    )
    packaging=closure["artifact_packaging_review"]
    require(packaging["research_result_valid"] is True,
            "research result validity drift")
    require(packaging["packaging_step_failed_after_evaluator_success"] is True,
            "packaging failure review drift")
    require(packaging["sha256sums_member_empty"] is True,
            "SHA256SUMS packaging review drift")
    require(packaging["rerun_required"] is False,
            "closure unexpectedly requests rerun")
    require(
        all(value is False for value in closure["authority_boundary"].values()),
        "closure authority escalation",
    )

    execution=closure["authoritative_execution"]
    require(execution["run_id"]==EXPECTED_RUN,"diagnostic run drift")
    require(execution["run_attempt"]==1,"diagnostic attempt drift")
    require(execution["head_sha"]==EXPECTED_HEAD,"diagnostic head drift")
    require(execution["artifact_id"]==EXPECTED_ARTIFACT,"artifact id drift")
    require(
        execution["artifact_name"]
        =="i033-ns-vad-causal-noise-delta-36719045384",
        "artifact name drift",
    )
    require(execution["artifact_size_bytes"]==EXPECTED_ZIP_BYTES,
            "artifact size drift")
    require(execution["artifact_sha256"]==EXPECTED_ZIP_SHA256,
            "artifact digest drift")
    expected=execution["member_sha256"]
    require(isinstance(expected,dict) and len(expected)==11,
            "archive member map drift")
    required={"SHA256SUMS","contract.json","result.json","summary.json"}
    require(required.issubset(expected),"required archive members missing")
    for name,sha in expected.items():
        require(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*",name) is not None,
            "unsafe archive filename",
        )
        require(re.fullmatch(r"[0-9a-f]{64}",sha) is not None,
                "invalid archive member digest")
    require(
        closure["original_result_path"]==ARCHIVE_ROOT+"/result.json",
        "archive root/result binding drift",
    )
    return expected


def select_members(zip_bytes: bytes,expected: dict[str,str]) -> dict[str,bytes]:
    require(
        len(zip_bytes)==EXPECTED_ZIP_BYTES and len(zip_bytes)<=MAX_ZIP_BYTES,
        "artifact ZIP size mismatch",
    )
    require(digest(zip_bytes)==EXPECTED_ZIP_SHA256,
            "artifact ZIP digest mismatch")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        infos=archive.infolist()
        names=[entry.filename for entry in infos]
        require(len(names)==len(set(names)),"duplicate ZIP member")
        require(all(safe_member(name) for name in names),"unsafe ZIP member")
        require(set(names)=={"evidence/"+name for name in expected},
                "artifact ZIP membership drift")
        members={}
        for info in infos:
            require(not info.is_dir() and not info.flag_bits & 1,
                    "non-regular/encrypted ZIP member")
            name=PurePosixPath(info.filename).name
            data=archive.read(info)
            require(digest(data)==expected[name],
                    "member digest mismatch: "+name)
            members[name]=data

    # The malformed auxiliary files are preserved as evidence, not repaired.
    require(members["SHA256SUMS"]==b"",
            "I033 empty SHA256SUMS defect drift")
    require(members["evaluate.exit-code"]==b"0\\n",
            "I033 literal exit-code newline defect drift")
    require(members["evaluate.stderr"]==b"",
            "I033 evaluator stderr drift")
    require(members["build-info.txt"]==(
        b"main_sha="+EXPECTED_HEAD.encode()+b"\\n"
    ),"I033 build-info newline defect drift")
    summary=members["summary.json"]
    require(summary.endswith(b"\\n"),
            "I033 summary newline defect drift")
    require(isinstance(parse(summary[:-2]),dict),
            "I033 summary JSON prefix invalid")

    raw=parse(members["result.json"])
    require(
        raw["decision"]
        =="NS_VAD_CAUSAL_NOISE_DELTA_ALIGNMENT_DECOMPOSED_REVIEW_REQUIRED",
        "artifact raw decision drift",
    )
    require(raw["invalid_reasons"]==[],"artifact invalid reasons drift")
    require(raw["diagnostic_execution_consumed"]==1,
            "artifact execution consumption drift")
    require(raw["candidate_budget_consumed"]==0,
            "artifact candidate authority drift")
    require(raw["confirmation_budget_consumed"]==0,
            "artifact confirmation authority drift")
    coverage=raw["coverage"]
    require(
        coverage["target_cases"]==252
        and coverage["causal_target_cases"]==143
        and coverage["causal_anchor_cases"]==39
        and coverage["benchmarkable_anchor_cases"]==39,
        "artifact coverage count drift",
    )
    require(coverage["causal_anchor_coverage"]>=0.25,
            "artifact causal-anchor coverage drift")
    require(coverage["post_target_benchmark_coverage"]>=0.8,
            "artifact post-target coverage drift")
    hypothesis=raw["delta_alignment_hypothesis"]
    require(hypothesis["supported"] is False,
            "artifact relative delta unexpectedly supported")
    global_delta=raw["delta_alignment"]["global"]
    require(global_delta["median_absolute_delta_error_db"]>3.0,
            "artifact median rejection drift")
    require(global_delta["p90_absolute_delta_error_db"]>6.0,
            "artifact p90 rejection drift")
    require(
        raw["shipping_mirror"]=={
            "max_ns_upstream_gap_delta":0.0,
            "max_vad_probability_delta":0.0,
            "vad_active_mismatch_frames":0,
        },
        "artifact shipping mirror drift",
    )
    require(all(value is False for value in raw["authority_boundary"].values()),
            "artifact authority escalation")
    return members


def rendered_files(members: dict[str,bytes]) -> dict[str,bytes]:
    return {
        ARCHIVE_ROOT+"/"+name:data
        for name,data in sorted(members.items())
    }


def check_repository(expected: dict[str,str]) -> dict:
    root=ROOT/ARCHIVE_ROOT
    if not root.exists():
        return {
            "status":"TRUSTED_CLOSURE_READY_FOR_ARCHIVE",
            "archive_root":ARCHIVE_ROOT,
        }
    require(root.is_dir(),"archive root is not directory")
    actual=sorted(path.name for path in root.iterdir() if path.is_file())
    require(actual==sorted(expected),"committed archive membership drift")
    for name,sha in expected.items():
        require(digest((root/name).read_bytes())==sha,
                "committed archive digest drift: "+name)
    return {
        "status":"DURABLE_ARCHIVE_PRESENT_AND_VERIFIED",
        "members":len(expected),
    }


class GitHub:
    def __init__(self,repo: str):
        self.repo=repo

    def api(self,path: str,*,writer=False,method=None,payload=None,binary=False):
        env=os.environ.copy()
        if writer:
            require(bool(env.get("GH_WRITE_TOKEN")),
                    "BLOCKED_AUTOMATION_CREDENTIAL: no publishing token")
            env["GH_TOKEN"]=env["GH_WRITE_TOKEN"]
        else:
            require(bool(env.get("GH_TOKEN")),"missing read token")
        args=["gh","api","--hostname","github.com"]
        if method:
            args+=["--method",method]
        args+=["repos/"+self.repo+"/"+path]
        input_bytes=None
        if payload is not None:
            if not method:
                args[3:3]=["--method","POST"]
            args+=["--input","-"]
            input_bytes=encoded(payload)
        process=subprocess.run(
            args,input=input_bytes,env=env,capture_output=True,
            timeout=120,check=False,
        )
        if process.returncode:
            stderr=process.stderr.decode("utf-8",errors="replace")
            match=re.search(r"\(HTTP ([1-5][0-9]{2})\)",stderr)
            raise ValueError(
                "GitHub API request failed: HTTP "
                +(match.group(1) if match else "unknown")
            )
        if binary:
            return process.stdout
        return parse(process.stdout)

    def main(self) -> str:
        return self.api("git/ref/heads/main")["object"]["sha"]

    def artifact_zip(self) -> bytes:
        artifact=self.api("actions/artifacts/"+str(EXPECTED_ARTIFACT))
        require(artifact["id"]==EXPECTED_ARTIFACT,"artifact identity mismatch")
        require(artifact.get("expired") is False,"artifact expired")
        run=artifact.get("workflow_run") or {}
        require(
            run.get("id")==EXPECTED_RUN and run.get("head_sha")==EXPECTED_HEAD,
            "artifact run binding mismatch",
        )
        if artifact.get("digest"):
            require(
                artifact["digest"]=="sha256:"+EXPECTED_ZIP_SHA256,
                "artifact API digest mismatch",
            )
        data=self.api(
            "actions/artifacts/"+str(EXPECTED_ARTIFACT)+"/zip",
            binary=True,
        )
        require(len(data)==EXPECTED_ZIP_BYTES,"downloaded ZIP size mismatch")
        require(digest(data)==EXPECTED_ZIP_SHA256,
                "downloaded ZIP digest mismatch")
        return data


def git_blob(api: GitHub,data: bytes) -> str:
    return api.api(
        "git/blobs",writer=True,method="POST",
        payload={
            "content":base64.b64encode(data).decode("ascii"),
            "encoding":"base64",
        },
    )["sha"]


def publish_branch(api: GitHub,files: dict[str,bytes],main: str) -> dict:
    require(api.main()==main,"main moved before archive publication")
    base=api.api("git/commits/"+main)
    tree_items=[
        {
            "path":path,"mode":"100644","type":"blob",
            "sha":git_blob(api,data),
        }
        for path,data in sorted(files.items())
    ]
    tree=api.api(
        "git/trees",writer=True,method="POST",
        payload={"base_tree":base["tree"]["sha"],"tree":tree_items},
    )
    require(api.main()==main,"main moved while preparing archive tree")
    refs=api.api("git/matching-refs/heads/"+ARCHIVE_BRANCH)
    exact=[ref for ref in refs if ref["ref"]=="refs/heads/"+ARCHIVE_BRANCH]
    require(len(exact)<=1,"ambiguous archive branch")
    if exact:
        commit=api.api("git/commits/"+exact[0]["object"]["sha"])
        require(commit["tree"]["sha"]==tree["sha"],
                "existing archive tree drift")
        return {
            "status":"ARCHIVE_BRANCH_READY",
            "head":exact[0]["object"]["sha"],
            "existing":True,
        }

    commit=api.api(
        "git/commits",writer=True,method="POST",
        payload={
            "message":"research(i033): archive verified causal noise-delta evidence",
            "tree":tree["sha"],"parents":[main],
        },
    )
    api.api(
        "git/refs",writer=True,method="POST",
        payload={"ref":"refs/heads/"+ARCHIVE_BRANCH,"sha":commit["sha"]},
    )
    return {
        "status":"ARCHIVE_BRANCH_READY",
        "head":commit["sha"],
        "existing":False,
    }


def reconcile(output: Path) -> dict:
    closure=parse(CLOSURE.read_bytes())
    expected=validate_closure(closure)
    require(
        os.environ.get("GITHUB_REPOSITORY")=="jiying2007/audio-pipeline",
        "foreign repository",
    )
    require(os.environ.get("GITHUB_REF")=="refs/heads/main",
            "publisher requires trusted main")
    require(os.environ.get("GITHUB_EVENT_NAME")=="push",
            "publisher requires trusted main push")
    api=GitHub(os.environ["GITHUB_REPOSITORY"])
    main=api.main()
    checkout=subprocess.check_output(
        ["git","rev-parse","HEAD"],cwd=ROOT,text=True
    ).strip()
    require(checkout==main,"checkout is not live main")
    if (ROOT/ARCHIVE_ROOT).exists():
        result=check_repository(expected)
        result["main"]=main
        return result

    members=select_members(api.artifact_zip(),expected)
    files=rendered_files(members)
    output.mkdir(parents=True,exist_ok=True)
    (output/"verified-members.json").write_bytes(encoded({
        path:{"bytes":len(data),"sha256":digest(data)}
        for path,data in sorted(files.items())
    }))
    result=publish_branch(api,files,main)
    result.update({
        "verified_members":len(files),
        "verified_bytes":sum(len(data) for data in files.values()),
        "source_main":main,
    })
    return result


def self_test() -> None:
    assert safe_member("evidence/result.json")
    assert not safe_member("../result.json")
    assert not safe_member("evidence/sub/result.json")
    assert digest(b"x")=="2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
    print("i033 exact evidence archive self-test: PASS")


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--publish",action="store_true")
    parser.add_argument("--output",type=Path,default=Path("i033-archive-out"))
    args=parser.parse_args()
    require(sum((args.self_test,args.check,args.publish))==1,
            "choose exactly one mode")
    if args.self_test:
        self_test()
        return 0
    closure=parse(CLOSURE.read_bytes())
    expected=validate_closure(closure)
    if args.check:
        print(json.dumps(check_repository(expected),sort_keys=True))
        return 0
    args.output.mkdir(parents=True,exist_ok=True)
    try:
        result=reconcile(args.output)
        rc=0
    except (
        ValueError,KeyError,TypeError,OSError,
        subprocess.SubprocessError,zipfile.BadZipFile
    ) as exc:
        result={"status":"BLOCKED","error":str(exc)}
        rc=1
    (args.output/"status.json").write_bytes(encoded(result))
    print(json.dumps(result,sort_keys=True))
    return rc


if __name__=="__main__":
    raise SystemExit(main())
