#!/usr/bin/env python3
"""Publish exact consumed I037 evidence bytes without rerunning research."""

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
    "i037-ns-noise-estimate-aggregation-exact-order-recovery-v1-result.json"
)
ARCHIVE_ROOT="validation/research/evidence/i037-36824635292"
ARCHIVE_BRANCH="automation/i037-evidence-36824635292"
EXPECTED_RUN=36824635292
EXPECTED_ARTIFACT=11144499769
EXPECTED_HEAD="4204ae2fa9bff472ec2f70e42b6710b6e088bc74"
EXPECTED_ZIP_SHA256="fdb2e7b488dd9e541e886a8da8fd27dcf6c28f4badcb62a263ab238a0708be6f"
EXPECTED_ZIP_BYTES=115706
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
        =="i037-ns-noise-estimate-aggregation-exact-order-recovery-v1",
        "closure investigation drift",
    )
    require(closure["status"]=="CLOSED_DIAGNOSTIC_ONLY",
            "I037 closure is not terminal")
    require(closure["authority"]=="CANDIDATE_ZERO_DIAGNOSTIC_ONLY",
            "closure authority drift")
    require(
        closure["decision"]
        =="NS_NOISE_ESTIMATE_AGGREGATION_EXACT_ORDER_RECOVERED_REVIEW_REQUIRED",
        "raw decision drift",
    )
    require(
        closure["reviewed_decision"]
        =="EXACT_ORDER_RECOVERED_FIXED_SPEECH_BAND_DOES_NOT_CONSISTENTLY_CLOSE_ALIGNMENT_OR_RESPONSE_GAP_NO_BAND_ESTIMATOR_OR_NORMALIZATION_CANDIDATE",
        "reviewed decision drift",
    )
    require(
        closure["fresh_authority"]=={
            "target_seeds":[1941307,1951307,1961307,1971307,1981307,1991307],
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
            "max_noise_rms_reconstruction_gap_db":0,
            "noise_rms_bitwise_mismatch_frames":0,
        },
        "shipping mirror drift",
    )
    coverage=closure["coverage_review"]
    require(
        coverage["target_cases"]==252
        and coverage["causal_target_cases"]==150
        and coverage["causal_anchor_cases"]==54,
        "coverage count drift",
    )
    require(coverage["causal_anchor_coverage"]>=0.25,
            "causal anchor coverage drift")
    require(
        coverage["fixed_horizon_coverage"]=={"1":1,"2":1,"4":1,"8":1},
        "fixed horizon coverage drift",
    )
    review=closure["root_cause_review"]
    require(review["exact_order_reconstruction_recovered"] is True,
            "exact-order recovery drift")
    require(review["i036_float_reduction_order_defect_confirmed"] is True,
            "I036 reduction-order conclusion drift")
    require(
        review["simple_all_bin_aggregation_dilution_explanation_supported"]
        is False,
        "all-bin dilution explanation was promoted",
    )
    require(
        review["fixed_speech_band_consistently_improves_alignment"] is False,
        "fixed speech band was promoted",
    )
    require(review["speech_band_response_deficit_persists"] is True,
            "speech response-deficit review drift")
    horizons=closure["aggregation_review"]["fixed_horizons"]
    require(list(horizons)==["1","2","4","8"],"horizon order drift")
    for horizon,row in horizons.items():
        require(row["cases"]==54,"horizon population drift")
        require(row["median_speech_response_deficit_db"]>0.0,
                "speech response deficit unexpectedly disappeared")
        require(row["median_speech_vs_all_alignment_improvement_db"]<0.0,
                "speech alignment review drift")
        require(row["speech_alignment_better_fraction"]<0.5,
                "speech alignment majority drift")
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
        =="i037-ns-aggregation-exact-order-recovery-36824635292",
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
    require(
        members["build-info.txt"]==b"main_sha="+EXPECTED_HEAD.encode()+b"\n",
        "build-info drift",
    )
    for name in ("contract.json","materialization.json","result.json","summary.json"):
        require(isinstance(parse(members[name]),dict),
                "JSON member invalid: "+name)

    raw=parse(members["result.json"])
    require(
        raw["decision"]
        =="NS_NOISE_ESTIMATE_AGGREGATION_EXACT_ORDER_RECOVERED_REVIEW_REQUIRED",
        "artifact raw decision drift",
    )
    require(raw["invalid_reasons"]==[],"artifact invalid reasons drift")
    require(raw["diagnostic_execution_consumed"]==1,
            "artifact execution consumption drift")
    require(raw["candidate_budget_consumed"]==0,
            "artifact candidate authority drift")
    require(raw["confirmation_budget_consumed"]==0,
            "artifact confirmation authority drift")
    mirror=raw["shipping_mirror"]
    require(mirror["max_ns_upstream_gap_delta"]==0.0,
            "artifact NS mirror drift")
    require(mirror["max_vad_probability_delta"]==0.0,
            "artifact VAD mirror drift")
    require(mirror["vad_active_mismatch_frames"]==0,
            "artifact VAD active mirror drift")
    require(mirror["max_noise_rms_reconstruction_gap_db"]==0.0,
            "artifact reconstruction gap drift")
    require(mirror["noise_rms_bitwise_mismatch_frames"]==0,
            "artifact bitwise reconstruction drift")
    coverage=raw["coverage"]
    require(
        coverage["target_cases"]==252
        and coverage["causal_target_cases"]==150
        and coverage["causal_anchor_cases"]==54,
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
    global_review=raw["aggregation_domain"]["global_fixed_horizons"]
    require(list(global_review)==["1","2","4","8"],
            "artifact horizon order drift")
    for horizon in ("1","2","4","8"):
        row=global_review[horizon]
        require(row["median_speech_response_deficit_db"]>0.0,
                "artifact speech response deficit drift")
        require(row["median_speech_vs_all_alignment_improvement_db"]<0.0,
                "artifact speech alignment review drift")
        require(row["speech_alignment_better_fraction"]<0.5,
                "artifact speech alignment majority drift")
    boundary=raw["interpretation_boundary"]
    require(boundary["exact_shipping_order_all_bin_accumulation"] is True,
            "artifact exact-order boundary drift")
    require(boundary["bitwise_noise_rms_reconstruction_required"] is True,
            "artifact bitwise boundary drift")
    require(boundary["fixed_low_speech_high_partitions_only"] is True,
            "artifact fixed-partition boundary drift")
    require(boundary["no_spectral_band_search"] is True,
            "artifact band-search boundary drift")
    require(boundary["no_estimator_selection"] is True,
            "artifact estimator boundary drift")
    require(boundary["no_source_candidate"] is True,
            "artifact source-candidate boundary drift")
    require(
        all(value is False for value in raw["authority_boundary"].values()),
        "artifact authority escalation",
    )
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
            "message":"research(i037): archive verified exact-order evidence",
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
    print("i037 exact evidence archive self-test: PASS")


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--publish",action="store_true")
    parser.add_argument("--output",type=Path,default=Path("i037-archive-out"))
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
