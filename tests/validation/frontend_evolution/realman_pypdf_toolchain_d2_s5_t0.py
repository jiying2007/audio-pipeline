#!/usr/bin/env python3
"""D2-S5-T0: qualify pinned BSD pypdf only on synthetic PDF, never RealMAN paper.

Original preinstalled pdftotext experiment #716/#717 remains FAILED.
Preregistration https://github.com/jiying2007/audio-pipeline/issues/718
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
FROZEN = Path(__file__).with_name("realman_pypdf_toolchain_d2_s5_t0.json")
UPSTREAM = "https://github.com/py-pdf/pypdf.git"
TAG = "5.4.0"
COMMIT = "f20954f2241640feb484800e191373f8fbdfa44b"
TREE = "291be0904e532421cbc6e209e5a7875fdd610fb6"
PASS = "REALMAN_D2_S5_T0_PINNED_PYPDF_SYNTHETIC_QUALIFIED_ONLY"
BLOCKED = "REALMAN_D2_S5_T0_PDF_REFERENCE_NOT_QUALIFIED"
SENTENCE = "SYNTHETIC CLOCK SOURCE TEST 257 UNMODIFIED"
MAX_SOURCE = 128 * 1024 * 1024


class Reject(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(x, code="S5T0_SYNTHETIC_PROTOCOL_INVALID"):
    if not x:
        raise Reject(code)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def file_hash(p, cap=MAX_SOURCE):
    p=Path(p)
    require(p.is_file() and 0<p.stat().st_size<=cap,"S5T0_SOURCE_FILE_MISSING_OR_TOO_BIG")
    h=hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b=f.read(65536)
            if not b: break
            h.update(b)
    return p.stat().st_size,h.hexdigest()


def strict_json(p, cap=32768):
    require(p.is_file() and 0<p.stat().st_size<cap,"S5T0_RECEIPT_MISSING")
    def no_duplicate(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,"S5T0_DUPLICATE_JSON_KEY")
            d[k]=v
        return d
    try:
        return json.loads(p.read_text(encoding="utf-8"),
                          object_pairs_hook=no_duplicate,
                          parse_constant=lambda _:(_ for _ in ()).throw(
                              Reject("S5T0_JSON_NONFINITE")))
    except (ValueError, UnicodeError, OSError):
        raise Reject("S5T0_INVALID_RECEIPT_JSON") from None


def anchor():
    c=strict_json(FROZEN)
    s=c.get("source",{})
    require(c.get("schema_version")==1 and
            c.get("experiment_id")=="FE03-A2-D2-S5-T0-PINNED-PYPDF-5_4_0-SYNTHETIC"
            and c.get("preregistration") ==
            "https://github.com/jiying2007/audio-pipeline/issues/718"
            and c.get("predecessor_failure_issue")==716
            and c.get("predecessor_failed_pr")==717
            and c.get("predecessor_original_run")==38106174694
            and c.get("predecessor_original_artifact")==11690216460
            and c.get("predecessor_original_artifact_zip_sha256")==
            "96644eb6cb4c9211f328a159fd7950138e91718c7e4e1a0ba08b36707b5d7c2b"
            and c.get("original_preinstalled_pdf_extractor_result")==
            "S5_PREINSTALLED_PDF_TEXT_TOOL_MISSING"
            and s.get("official_repository")=="py-pdf/pypdf"
            and s.get("git_url")==UPSTREAM and s.get("tag")==TAG
            and s.get("annotated_tag_object_sha")==
            "6e3ae92515aefb7add4dae40fc840ad77274ba57"
            and s.get("immutable_commit")==COMMIT
            and s.get("immutable_tree")==TREE
            and s.get("python_package")=="pypdf"
            and s.get("python_package_version")==TAG
            and s.get("max_source_git_workspace_bytes")==MAX_SOURCE
            and s.get("git_source_fetch_timeout_seconds")==120
            and c.get("expected_synthetic_text")==SENTENCE
            and c.get("positive_decision")==PASS
            and c.get("failed_decision")==BLOCKED
            and s.get("source_binary_install_authorized") is False
            and s.get("source_bundle_redistribution_authorized") is False,
            "S5T0_FROZEN_SOURCE_ANCHOR_DRIFT")
    for k in ("publisher_paper_pdf_download_authorized","original_audio_download_authorized",
              "original_csv_download_authorized","acoustic_quality_score_authorized",
              "four_mic_hardware_sample_zero_verified","shipping_authority",
              "commercial_authority"):
        require(c.get(k) is False,"S5T0_SOURCE_SCOPE_PROMOTED")
    return c


def checkout_sha():
    try:
        sha40=subprocess.check_output(["git","rev-parse","HEAD"],
                                      cwd=ROOT,text=True,timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        raise Reject("S5T0_ACTION_GIT_SHA_MISSING") from None
    require(bool(re.fullmatch(r"[0-9a-f]{40}",sha40))
            and os.environ.get("GITHUB_SHA")==sha40,
            "S5T0_ACTION_CHECKOUT_SHA_DRIFT")
    return sha40


def command(argv, *, cwd=None, timeout=30, code="S5T0_SUBPROCESS_FAILED"):
    try:
        x=subprocess.run(argv,cwd=cwd,stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         timeout=timeout,check=False)
        require(x.returncode==0 and len(x.stdout)<32768,code)
        return x.stdout.decode("utf-8",errors="strict").strip()
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise Reject(code) from None


def program(name):
    path=shutil.which(name)
    require(path is not None,"S5T0_BUILD_TOOL_MISSING")
    p=Path(path).resolve()
    require(p.is_file(),"S5T0_BUILD_TOOL_MISSING")
    n,d=file_hash(p,cap=128*1024*1024)
    return str(p),{"sha256":d,"bytes":n}


def filetree_bytes(path):
    root=Path(path)
    total=0
    for p in root.rglob("*"):
        if p.is_file():
            total+=p.stat().st_size
            require(total<=MAX_SOURCE,"S5T0_UPSTREAM_SOURCE_TOO_LARGE")
    return total


def native_source(work, git):
    src=work/"pypdf-official"
    require(not src.exists(),"S5T0_SOURCE_WORKDIR_NOT_CLEAN")
    command([git,"clone","--depth","1","--single-branch",
             "--branch",TAG,"--filter=blob:none","--no-checkout",
             UPSTREAM,str(src)],cwd=work,timeout=120,
             code="S5T0_PINNED_GIT_CLONE_FAILED")
    command([git,"-C",str(src),"sparse-checkout","init","--cone"],
            timeout=20,code="S5T0_SPARSE_CHECKOUT_FAILED")
    command([git,"-C",str(src),"sparse-checkout","set","pypdf"],
            timeout=60,code="S5T0_SPARSE_CHECKOUT_FAILED")
    command([git,"-C",str(src),"checkout","--detach",COMMIT],
            timeout=40,code="S5T0_UPSTREAM_CHECKOUT_FAILED")
    return src


def source_identity(src,git):
    require(command([git,"-C",str(src),"rev-parse","HEAD"],timeout=10)==COMMIT,
            "S5T0_PINNED_SOURCE_COMMIT_DRIFT")
    require(command([git,"-C",str(src),"rev-parse","HEAD^{tree}"],timeout=10)==TREE,
            "S5T0_PINNED_SOURCE_TREE_DRIFT")
    require(command([git,"-C",str(src),"status","--porcelain"],timeout=10)=="",
            "S5T0_PINNED_SOURCE_DIRTY")
    require(command([git,"-C",str(src),"remote","get-url","origin"],timeout=10)==UPSTREAM,
            "S5T0_PINNED_UPSTREAM_CHANGED")
    license=src/"LICENSE"
    size,h=file_hash(license,cap=65536)
    content=license.read_bytes()
    require(b"Redistribution and use in source and binary forms" in content and
            b"All rights reserved" in content,
            "S5T0_BSD_LICENSE_NOT_PROVEN")
    pkg=src/"pypdf"/"__init__.py"
    require(pkg.is_file() and (src/"pyproject.toml").is_file(),
            "S5T0_PURE_PYTHON_PACKAGE_INCOMPLETE")
    n=filetree_bytes(src)
    return {
        "upstream_git_commit":COMMIT,"upstream_git_tree":TREE,
        "license_bytes":size,"license_sha256":h,"git_and_source_bytes":n,
        "package_entry_sha256":file_hash(pkg,cap=4*1024*1024)[1],
        "pure_python_direct_source_import":True,
        "upstream_source_distributed_in_artifact":False
    }


def synthetic_pdf():
    """Build a fixed valid one-page Helvetica PDF using only the Python stdlib."""
    body=(b"BT /F1 12 Tf 36 120 Td ("+SENTENCE.encode("ascii")+
          b") Tj ET\n")
    objects=[
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length "+str(len(body)).encode()+b" >>\nstream\n"+body+b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf=bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(pdf))
        pdf+=(str(i)+" 0 obj\n").encode()+obj+b"\nendobj\n"
    begin=len(pdf)
    pdf+=b"xref\n0 6\n0000000000 65535 f \n"
    for o in offsets[1:]:
        pdf+=("%010d 00000 n \n"%o).encode()
    pdf+=b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
    pdf+=str(begin).encode()+b"\n%%EOF\n"
    require(0<len(pdf)<=65536,"S5T0_SYNTHETIC_PDF_SIZE")
    return bytes(pdf)


def child_proof(src):
    # No sys-site installed parser is trusted; import only from pinned source.
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(src))
    import pypdf
    from pypdf import PdfReader
    require(str(pypdf.__version__)==TAG and
            Path(pypdf.__file__).resolve().is_relative_to(
                (src/"pypdf").resolve()),
            "S5T0_SOURCE_PYTHON_IMPORT_NOT_PINNED")
    raw=synthetic_pdf()
    vals=[]
    for _ in range(2):
        rd=PdfReader(BytesIO(raw),strict=True)
        require(len(rd.pages)==1,"S5T0_SYNTHETIC_PAGE_COUNT_WRONG")
        got=rd.pages[0].extract_text()
        require(got.strip()==SENTENCE,"S5T0_SYNTHETIC_TEXT_MISMATCH")
        vals.append(got.strip())
    truncated=False
    try:
        PdfReader(BytesIO(raw[:-19]),strict=True).pages[0].extract_text()
    except Exception:
        truncated=True
    require(truncated,"S5T0_TRUNCATED_PDF_NOT_REJECTED")
    altered=raw.replace(b"CLOCK",b"FRAUD")
    require(altered!=raw and len(altered)==len(raw),
            "S5T0_ALTERED_FIXTURE_NOT_GENERATED")
    got=PdfReader(BytesIO(altered),strict=True).pages[0].extract_text()
    require(got.strip()!=SENTENCE,"S5T0_MODIFIED_TEXT_FALSE_ACCEPT")
    proof={
        "pypdf_version":pypdf.__version__,
        "synthetic_pdf_bytes":len(raw),
        "synthetic_pdf_sha256":sha(raw),
        "synthetic_text_sha256":sha(SENTENCE.encode()),
        "two_exact_text_readbacks":True,
        "independent_subprocess_proof":True,
        "truncated_pdf_rejected":True,
        "altered_text_not_accepted":True,
        "publisher_paper_used":False,
        "original_realman_audio_used":False,
        "shipping_authority":False,
    }
    print(json.dumps(proof,sort_keys=True,separators=(",",":")))
    return 0


def synthetic_child_process(src, timeout=30):
    p=Path(__file__).resolve()
    result=subprocess.run([sys.executable,str(p),"child-proof","--source",str(src)],
                          stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,cwd=ROOT,
                          env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1"),
                          timeout=timeout)
    require(result.returncode==0 and len(result.stdout)<8192,
            "S5T0_SYNTHETIC_PARSER_FAILED")
    try:
        data=json.loads(result.stdout.decode("utf-8",errors="strict"))
    except (ValueError,UnicodeError):
        raise Reject("S5T0_SYNTHETIC_PROOF_NOT_CANONICAL") from None
    require(data.get("two_exact_text_readbacks") is True
            and data.get("truncated_pdf_rejected") is True
            and data.get("altered_text_not_accepted") is True
            and data.get("publisher_paper_used") is False
            and data.get("original_realman_audio_used") is False
            and data.get("shipping_authority") is False,
            "S5T0_INVALID_SYNTHETIC_PROOF")
    return data


def identity():
    return {
        "schema_version":1,
        "experiment_id":"FE03-A2-D2-S5-T0-PINNED-PYPDF-5_4_0-SYNTHETIC",
        "preregistration":"https://github.com/jiying2007/audio-pipeline/issues/718",
        "source_commit":checkout_sha(),
        "frozen_contract_sha256":sha(FROZEN.read_bytes()),
        "script_sha256":sha(Path(__file__).read_bytes()),
        "original_s5_preinstalled_extractor_passed":False,
        "original_neurips_pdf_downloaded":False,
        "original_realman_audio_used":False,
        "four_mic_timebase_verified":False,
        "shipping_authority":False,
        "commercial_authority":False
    }


def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj,sort_keys=True,separators=(",",":"),
                              ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    tmp.replace(path)


def collect(work,receipt):
    out=identity()
    out["captured_at_utc"]=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        anchor()
        require(not work.exists(),"S5T0_WORKSPACE_ALREADY_EXISTS")
        work.mkdir(parents=True)
        git,githash=program("git")
        require(sys.version_info>=(3,11),"S5T0_UNSUPPORTED_PYTHON")
        python_bytes,python_sha=file_hash(Path(sys.executable).resolve(),
                                          cap=128*1024*1024)
        out["preflight"]={
            "git_version":command([git,"--version"],timeout=5),
            "git_binary":githash,
            "python_version":sys.version.split()[0],
            "python_binary_sha256":python_sha,
            "python_binary_bytes":python_bytes,
        }
        src=native_source(work,git)
        out["source"]=source_identity(src,git)
        out["synthetic_proof"]=synthetic_child_process(src)
        require(out["source"]==source_identity(src,git),
                "S5T0_ORIGINAL_TREE_CHANGED_AFTER_SYNTHETIC")
        out["decision"]=PASS
        status=0
    except (Reject,OSError,subprocess.SubprocessError) as e:
        for k in ("preflight","source","synthetic_proof"):
            out.pop(k,None)
        out["decision"]=BLOCKED
        out["failure_code"]=getattr(e,"code","S5T0_TOOL_OR_STORAGE_ERROR")
        status=1
    save(receipt,out)
    print("decision="+out["decision"]+" failure="+out.get("failure_code","NONE"),flush=True)
    return status


def verify(work,receipt):
    r=strict_json(receipt)
    expected=identity()
    for k,v in expected.items():
        require(r.get(k)==v,"S5T0_RECEIPT_IDENTITY_CHANGED")
    require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                              r.get("captured_at_utc",""))),
            "S5T0_RECEIPT_TIME_INVALID")
    if r.get("decision")==PASS:
        require(set(r)==set(expected)|{
            "captured_at_utc","preflight","source","synthetic_proof","decision"},
            "S5T0_RECEIPT_FIELD_DRIFT")
        anchor()
        git,_=program("git")
        src=work/"pypdf-official"
        require(r.get("source")==source_identity(src,git),
                "S5T0_INDEPENDENT_PINNED_SOURCE_DRIFT")
        require(synthetic_child_process(src)==r.get("synthetic_proof"),
                "S5T0_INDEPENDENT_SYNTHETIC_READBACK_FAILED")
        require(r.get("source")==source_identity(src,git),
                "S5T0_SOURCE_CHANGED_DURING_VERIFICATION")
    else:
        require(r.get("decision")==BLOCKED and
                bool(re.fullmatch(r"S5T0_[A-Z0-9_]+",r.get("failure_code","")))
                and set(r)==set(expected)|{"captured_at_utc","decision","failure_code"},
                "S5T0_FAILED_RECEIPT_INVALID")
    print("S5T0_PINNED_SOURCE_SYNTHETIC_READBACK="+r["decision"])


def self_test():
    a=anchor()
    require(a["source"]["immutable_commit"]==COMMIT and
            a["source"]["immutable_tree"]==TREE)
    raw=synthetic_pdf()
    require(raw.startswith(b"%PDF-1.4") and raw.endswith(b"%%EOF\n")
            and b"(" + SENTENCE.encode() + b")" in raw
            and 500<len(raw)<4096 and raw.count(b"endobj")==5,
            "S5T0_SYNTHETIC_FIXTURE_INVALID")
    require(raw.replace(b"CLOCK",b"FRAUD")!=raw)
    require(raw[:-19]!=raw)
    with tempfile.TemporaryDirectory(prefix="s5t0-receipt-test-") as dir:
        p=Path(dir)/"r.json"
        p.write_text('{"decision":1,"decision":2}')
        try:
            strict_json(p)
        except Reject:
            pass
        else:
            raise AssertionError("duplicate JSON object keys admitted")
    require(not a["original_audio_download_authorized"]
            and not a["publisher_paper_pdf_download_authorized"]
            and not a["commercial_authority"])
    print("REALMAN_D2_S5_T0_OFFLINE_SYNTHETIC_CONTRACT_PASS; no real PDF or audio")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("self-test","collect","verify","child-proof"))
    p.add_argument("--workspace")
    p.add_argument("--receipt")
    p.add_argument("--source")
    a=p.parse_args()
    if a.action=="self-test":
        self_test()
        return 0
    if a.action=="child-proof":
        require(bool(a.source),"S5T0_CHILD_SOURCE_MISSING")
        return child_proof(Path(a.source).resolve())
    require(bool(a.workspace and a.receipt),"S5T0_ARGUMENTS_MISSING")
    work=Path(a.workspace).resolve()
    receipt=Path(a.receipt).resolve()
    if a.action=="collect":
        return collect(work,receipt)
    verify(work,receipt)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
