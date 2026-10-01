#!/usr/bin/env python3
"""Publish exact consumed I035 evidence bytes without rerunning research."""

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
    "i035-ns-vad-noise-state-temporal-response-decomposition-v1-result.json"
)
ARCHIVE_ROOT="validation/research/evidence/i035-36795467909"
ARCHIVE_BRANCH="automation/i035-evidence-36795467909"
EXPECTED_RUN=36795467909
EXPECTED_ARTIFACT=11133847821
EXPECTED_HEAD="d4bac5e8ac3f847c78143b64634d16a16780df3f"
EXPECTED_ZIP_SHA256="2e6595d6d51acfc0eb5c27b439ac6aee2c617696e76ecef809191a807f650ad7"
EXPECTED_ZIP_BYTES=80389
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
        closure["investigation_id"]
        =="i035-ns-noise-tracker-update-regime-decomposition-v1",
        "closure investigation drift",
    )
    require(closure["status"]=="CLOSED_DIAGNOSTIC_ONLY",
            "I035 closure is not terminal")
    require(closure["authority"]=="CANDIDATE_ZERO_DIAGNOSTIC_ONLY",
            "closure authority drift")
    require(
        closure["decision"]
        =="NS_NOISE_TRACKER_UPDATE_REGIME_DECOMPOSED_REVIEW_REQUIRED",
        "raw decision drift",
    )
    require(
        closure["reviewed_decision"]
        =="FAST_UPDATE_DOMINATES_NOISE_ESTIMATE_MOVEMENT_RESPONSE_DEFICIT_PERSISTS_NO_ALPHA_THRESHOLD_OR_LAG_CANDIDATE",
        "reviewed decision drift",
    )
    require(
        closure["fresh_authority"]=={
            "target_seeds":[1821307,1831307,1841307,1851307,1861307,1871307],
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
        and coverage["causal_target_cases"]==144
        and coverage["causal_anchor_cases"]==39,
        "coverage count drift",
    )
    require(coverage["causal_anchor_coverage"]>=0.25,
            "causal anchor coverage drift")
    require(
        coverage["fixed_horizon_coverage"]=={"1":1,"2":1,"4":1,"8":1},
        "fixed horizon coverage drift",
    )
    review=closure["fixed_horizon_regime_review"]
    for horizon in ("1","2","4","8"):
        row=review[horizon]
        require(row["cases"]==39,"horizon population drift")
        require(row["median_fast_update_bin_fraction"]>0.90,
                "fast update opportunity drift")
        require(row["median_fast_update_abs_contribution_fraction"]>0.99,
                "fast update contribution drift")
        require(row["median_response_deficit_db"]>2.0,
                "response deficit unexpectedly disappeared")
        require(
            row["spearman_slow_update_bin_fraction_vs_response_deficit"]<0.0,
            "slow exposure association drift",
        )
    root=closure["root_cause_review"]
    require(root["simple_slow_update_gating_explanation_supported"] is False,
            "slow-gating explanation was promoted")
    require(root["fast_update_opportunity_dominant"] is True,
            "fast opportunity review drift")
    require(root["fast_update_absolute_contribution_dominant"] is True,
            "fast contribution review drift")
    require(root["response_deficit_persists_with_fast_update_opportunity"] is True,
            "persistent deficit review drift")
    require(root["tracker_alpha_change_authorized"] is False,
            "tracker alpha was promoted")
    require(root["tracker_branch_threshold_change_authorized"] is False,
            "tracker threshold was promoted")
    require(root["mapping_authorized"] is False,
            "mapping was promoted")
    require(root["source_patch_authorized"] is False,
            "source patch was promoted")
    require(
        all(value is False for value in closure["authority_boundary"].values()),
        "closure authority escalation",
    )

    execution=closure["authoritative_execution"]
    require(execution["run_id"]==EXPECTED_RUN,"diagnostic run drift")
    require(execution["run_attempt"]==1,"diagnostic attempt drift")
    require(execution["head_sha"]==EXPECTED_HEAD,"diagnostic head drift")
    require(execution["run_conclusion"]=="success","run conclusion drift")
    require(execution["evaluator_result_valid"] is True,
            "evaluator validity drift")
    require(execution["evaluator_return_code"]==0,
            "evaluator return-code drift")
    require(execution["artifact_id"]==EXPECTED_ARTIFACT,"artifact id drift")
    require(
        execution["artifact_name"]
        =="i035-ns-noise-tracker-update-regime-36795467909",
        "artifact name drift",
    )
    require(execution["artifact_size_bytes"]==EXPECTED_ZIP_BYTES,
            "artifact size drift")
    require(execution["artifact_sha256"]==EXPECTED_ZIP_SHA256,
            "artifact digest drift")
    require(execution["internal_sha256sums_verified"] is True,
            "internal SHA256SUMS review drift")
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

    sums={}
    for line in members["SHA256SUMS"].decode("ascii").splitlines():
        match=re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)",line)
        require(match is not None,"invalid SHA256SUMS line")
        sha,name=match.groups()
        require(name not in sums,"duplicate SHA256SUMS entry")
        sums[name]=sha
    require(set(sums)==set(expected)-{"SHA256SUMS"},
            "SHA256SUMS membership drift")
    for name,sha in sums.items():
        require(sha==expected[name] and digest(members[name])==sha,
                "internal member digest mismatch: "+name)

    require(members["evaluate.exit-code"]==b"0\n",
            "evaluator exit code drift")
    require(members["evaluate.stderr"]==b"",
            "evaluator stderr drift")
    require(members["build-info.txt"]==(
        b"main_sha="+EXPECTED_HEAD.encode()+b"\n"
    ),"build-info drift")
    for name in ("contract.json","materialization.json","result.json","summary.json"):
        require(isinstance(parse(members[name]),dict),
                "JSON member invalid: "+name)

    raw=parse(members["result.json"])
    require(
        raw["decision"]
        =="NS_NOISE_TRACKER_UPDATE_REGIME_DECOMPOSED_REVIEW_REQUIRED",
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
        and coverage["causal_target_cases"]==144
        and coverage["causal_anchor_cases"]==39,
        "artifact coverage count drift",
    )
    require(coverage["causal_anchor_coverage"]>=0.25,
            "artifact causal-anchor coverage drift")
    require(
        coverage["fixed_horizon_coverage"]=={
            "1":1.0,"2":1.0,"4":1.0,"8":1.0
        },
        "artifact horizon coverage drift",
    )
    global_review=raw["update_regime"]["global_fixed_horizons"]
    require(list(global_review)==["1","2","4","8"],
            "artifact horizon order drift")
    for horizon in ("1","2","4","8"):
        row=global_review[horizon]
        require(row["median_fast_update_bin_fraction"]>0.90,
                "artifact fast opportunity drift")
        require(row["median_fast_update_abs_contribution_fraction"]>0.99,
                "artifact fast contribution drift")
        require(row["median_response_deficit_db"]>2.0,
                "artifact response deficit drift")
    boundary=raw["interpretation_boundary"]
    require(boundary["shipping_tracker_function_reused_in_mirror"] is True,
            "artifact tracker mirror boundary drift")
    require(boundary["no_tracker_alpha_search"] is True,
            "artifact alpha-search boundary drift")
    require(boundary["no_tracker_threshold_search"] is True,
            "artifact tracker-threshold boundary drift")
    require(boundary["no_source_candidate"] is True,
            "artifact source-candidate boundary drift")
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
            "message":"research(i035): archive verified update-regime evidence",
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
    print("i035 exact evidence archive self-test: PASS")


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--publish",action="store_true")
    parser.add_argument("--output",type=Path,default=Path("i035-archive-out"))
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
