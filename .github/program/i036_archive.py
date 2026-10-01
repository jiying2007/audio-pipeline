#!/usr/bin/env python3
"""Publish exact consumed invalid I036 evidence bytes without rerunning research."""

from __future__ import annotations

import argparse,base64,hashlib,io,json,os,re,subprocess,zipfile
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[2]
CLOSURE=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i036-ns-noise-estimate-aggregation-domain-decomposition-v1-result.json"
)
ARCHIVE_ROOT="validation/research/evidence/i036-36803529573"
ARCHIVE_BRANCH="automation/i036-evidence-36803529573"
EXPECTED_RUN=36803529573
EXPECTED_ARTIFACT=11137255580
EXPECTED_HEAD="9768801f9dd6d8c674a158e3a78d863e00cfedb5"
EXPECTED_ZIP_SHA256="423056a3e463fcdc415598517c4536f738976e7f30abe622ac1d979729a9e7b5"
EXPECTED_ZIP_BYTES=109960
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
        bool(name) and not path.is_absolute() and ".." not in path.parts
        and len(path.parts)==2 and path.parts[0]=="evidence"
    )


def validate_closure(closure: dict) -> dict[str,str]:
    require(closure["schema_version"]==1,"closure schema drift")
    require(
        closure["investigation_id"]
        =="i036-ns-noise-estimate-aggregation-domain-decomposition-v1",
        "closure investigation drift",
    )
    require(closure["status"]=="CLOSED_INVALID_DIAGNOSTIC_ONLY",
            "I036 closure is not terminal invalid")
    require(closure["authority"]=="CANDIDATE_ZERO_DIAGNOSTIC_ONLY",
            "closure authority drift")
    require(closure["decision"]=="I036_INPUT_INVALID_REVIEW_REQUIRED",
            "raw invalid decision drift")
    require(
        closure["reviewed_decision"]
        =="NUMERIC_RECONSTRUCTION_GATE_FAILED_FLOAT_REDUCTION_ORDER_NO_AGGREGATION_MECHANISM_VERDICT",
        "reviewed invalid decision drift",
    )
    invalid=closure["invalidity_review"]
    require(invalid["invalid_reasons"]==["noise_rms_reconstruction"],
            "invalid reason drift")
    require(invalid["all_other_preregistered_validity_gates_passed"] is True,
            "other validity gate drift")
    require(invalid["post_hoc_gate_relaxation_authorized"] is False,
            "post-hoc gate relaxation detected")
    require(invalid["descriptive_result_promotion_authorized"] is False,
            "invalid result promotion detected")
    require(
        closure["fresh_authority"]=={
            "target_seeds":[1881307,1891307,1901307,1911307,1921307,1931307],
            "diagnostic_execution_consumed":1,
            "candidate_budget_consumed":0,
            "confirmation_budget_consumed":0,
            "rerun_allowed":False,
        },
        "fresh authority drift",
    )
    mirror=closure["shipping_mirror"]
    require(mirror["max_ns_upstream_gap_delta"]==0,"NS mirror drift")
    require(mirror["max_vad_probability_delta"]==0,"VAD mirror drift")
    require(mirror["vad_active_mismatch_frames"]==0,"VAD active mirror drift")
    require(
        mirror["max_noise_rms_reconstruction_gap_db"]
        ==invalid["observed_max_noise_rms_reconstruction_gap_db"],
        "reconstruction review drift",
    )
    require(
        all(value is False for value in closure["authority_boundary"].values()),
        "closure authority escalation",
    )

    execution=closure["authoritative_execution"]
    require(execution["run_id"]==EXPECTED_RUN,"run drift")
    require(execution["run_attempt"]==1,"attempt drift")
    require(execution["head_sha"]==EXPECTED_HEAD,"head drift")
    require(execution["run_conclusion"]=="failure","run conclusion drift")
    require(execution["evaluator_result_structured"] is True,
            "structured evaluator result missing")
    require(execution["evaluator_input_valid"] is False,
            "invalid evaluator unexpectedly marked valid")
    require(execution["evaluator_return_code"]==2,"evaluator rc drift")
    require(execution["artifact_id"]==EXPECTED_ARTIFACT,"artifact id drift")
    require(
        execution["artifact_name"]
        =="i036-ns-noise-estimate-aggregation-domain-36803529573",
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
            "member map drift")
    for name,sha in expected.items():
        require(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*",name) is not None,
            "unsafe archive filename",
        )
        require(re.fullmatch(r"[0-9a-f]{64}",sha) is not None,
                "invalid member digest")
    require(
        closure["original_result_path"]==ARCHIVE_ROOT+"/result.json",
        "archive root binding drift",
    )
    return expected


def select_members(zip_bytes: bytes,expected: dict[str,str]) -> dict[str,bytes]:
    require(len(zip_bytes)==EXPECTED_ZIP_BYTES,"ZIP size mismatch")
    require(len(zip_bytes)<=MAX_ZIP_BYTES,"ZIP unexpectedly large")
    require(digest(zip_bytes)==EXPECTED_ZIP_SHA256,"ZIP digest mismatch")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        infos=archive.infolist()
        names=[entry.filename for entry in infos]
        require(len(names)==len(set(names)),"duplicate ZIP member")
        require(all(safe_member(name) for name in names),"unsafe ZIP member")
        require(set(names)=={"evidence/"+name for name in expected},
                "ZIP membership drift")
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
                "internal digest mismatch: "+name)

    require(members["evaluate.exit-code"]==b"2\n","evaluator rc bytes drift")
    require(members["evaluate.stderr"]==b"","evaluator stderr drift")
    require(
        members["build-info.txt"]==b"main_sha="+EXPECTED_HEAD.encode()+b"\n",
        "build-info drift",
    )
    raw=parse(members["result.json"])
    require(raw["decision"]=="I036_INPUT_INVALID_REVIEW_REQUIRED",
            "artifact decision drift")
    require(raw["invalid_reasons"]==["noise_rms_reconstruction"],
            "artifact invalid reason drift")
    require(raw["diagnostic_execution_consumed"]==1,
            "artifact consumption drift")
    require(raw["candidate_budget_consumed"]==0,
            "artifact candidate authority drift")
    require(raw["confirmation_budget_consumed"]==0,
            "artifact confirmation authority drift")
    require(raw["shipping_mirror"]["max_ns_upstream_gap_delta"]==0.0,
            "artifact NS mirror drift")
    require(raw["shipping_mirror"]["max_vad_probability_delta"]==0.0,
            "artifact VAD mirror drift")
    require(raw["shipping_mirror"]["vad_active_mismatch_frames"]==0,
            "artifact VAD active mirror drift")
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
        return {"status":"TRUSTED_INVALID_CLOSURE_READY_FOR_ARCHIVE",
                "archive_root":ARCHIVE_ROOT}
    require(root.is_dir(),"archive root is not directory")
    actual=sorted(path.name for path in root.iterdir() if path.is_file())
    require(actual==sorted(expected),"committed archive membership drift")
    for name,sha in expected.items():
        require(digest((root/name).read_bytes())==sha,
                "committed archive digest drift: "+name)
    return {"status":"DURABLE_INVALID_ARCHIVE_PRESENT_AND_VERIFIED",
            "members":len(expected)}


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
        require(digest(data)==EXPECTED_ZIP_SHA256,"downloaded ZIP digest mismatch")
        return data


def git_blob(api: GitHub,data: bytes) -> str:
    return api.api(
        "git/blobs",writer=True,method="POST",
        payload={"content":base64.b64encode(data).decode("ascii"),"encoding":"base64"},
    )["sha"]


def publish_branch(api: GitHub,files: dict[str,bytes],main: str) -> dict:
    require(api.main()==main,"main moved before archive publication")
    base=api.api("git/commits/"+main)
    tree_items=[
        {"path":path,"mode":"100644","type":"blob","sha":git_blob(api,data)}
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
        require(commit["tree"]["sha"]==tree["sha"],"existing archive tree drift")
        return {"status":"ARCHIVE_BRANCH_READY","head":exact[0]["object"]["sha"],
                "existing":True}

    commit=api.api(
        "git/commits",writer=True,method="POST",
        payload={
            "message":"research(i036): archive verified invalid aggregation evidence",
            "tree":tree["sha"],"parents":[main],
        },
    )
    api.api(
        "git/refs",writer=True,method="POST",
        payload={"ref":"refs/heads/"+ARCHIVE_BRANCH,"sha":commit["sha"]},
    )
    return {"status":"ARCHIVE_BRANCH_READY","head":commit["sha"],
            "existing":False}


def reconcile(output: Path) -> dict:
    expected=validate_closure(parse(CLOSURE.read_bytes()))
    require(os.environ.get("GITHUB_REPOSITORY")=="jiying2007/audio-pipeline",
            "foreign repository")
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
    assert digest(b"x")=="2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"
    print("i036 invalid exact evidence archive self-test: PASS")


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--publish",action="store_true")
    parser.add_argument("--output",type=Path,default=Path("i036-archive-out"))
    args=parser.parse_args()
    require(sum((args.self_test,args.check,args.publish))==1,
            "choose exactly one mode")
    if args.self_test:
        self_test(); return 0
    expected=validate_closure(parse(CLOSURE.read_bytes()))
    if args.check:
        print(json.dumps(check_repository(expected),sort_keys=True)); return 0
    args.output.mkdir(parents=True,exist_ok=True)
    try:
        result=reconcile(args.output); rc=0
    except (
        ValueError,KeyError,TypeError,OSError,
        subprocess.SubprocessError,zipfile.BadZipFile
    ) as exc:
        result={"status":"BLOCKED","error":str(exc)}; rc=1
    (args.output/"status.json").write_bytes(encoded(result))
    print(json.dumps(result,sort_keys=True))
    return rc


if __name__=="__main__":
    raise SystemExit(main())
