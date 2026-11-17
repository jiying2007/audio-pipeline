#!/usr/bin/env python3
"""Corrupt disposable copies of actual D3 evidence; never reseal originals."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import time

import dualmic_zero_d3 as d3
from dualmic_stages_source import dump, need, remaining

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--receipt",required=True,type=Path)
    a=p.parse_args(); start=time.monotonic()
    original=a.output.resolve()
    need(d3.d2.read_json(original/"readback.json")["status"]=="PASS","qualified original readback required")
    key=d3.d2.read_json(original/"run-index.json")["completed"][0]
    mutations=[
        ("candidate_sample", "cases/"+key+"/candidate.f32le", "flip"),
        ("baseline_sample", "cases/"+key+"/baseline.f32le", "flip"),
        ("complete_state", "cases/"+key+"/trace.bin", "flip"),
        ("control", "cases/"+key+"/control.bin", "flip"),
        ("missing_trace", "cases/"+key+"/trace.bin", "delete"),
        ("source", "source/candidate.c", "append"),
        ("report", "report.json", "report"),
        ("added_member", "cases/"+key+"/unlisted.bin", "add"),
        ("output_root_member", "unlisted.bin", "add"),
        ("case_root_member", "cases/unlisted.bin", "add"),
        ("self_consistent_build_argv", "build.json", "argv"),
        ("source_tree", "build.json", "tree"),
        ("source_revision", "build.json", "revision"),
        ("failed_run_phase", "run-phase.json", "phase"),
        ("resealed_extra_source", "source/extra.h", "source_extra"),
    ]
    records=[]; receipt={"experiment":d3.EXPERIMENT,"status":"FAIL","tests":records,"budget_seconds":300}
    try:
        for name,relative,kind in mutations:
            remaining(start,300)
            with tempfile.TemporaryDirectory(prefix="d3-negative-") as tmp:
                copy=Path(tmp)/"result"; shutil.copytree(original,copy)
                path=copy/relative
                if kind=="flip":
                    raw=bytearray(path.read_bytes()); raw[0]^=1; path.write_bytes(raw)
                elif kind=="delete": path.unlink()
                elif kind=="append": path.write_bytes(path.read_bytes()+b"\n")
                elif kind=="add": path.write_bytes(b"unlisted")
                elif kind=="argv":
                    b=d3.d2.read_json(path); b["command"][2]="-O3"; dump(path,b)
                    r=d3.d2.read_json(copy/"build-command.json"); r["argv"]=b["command"]; dump(copy/"build-command.json",r)
                elif kind in ("tree","revision"):
                    b=d3.d2.read_json(path); b["source_tree" if kind=="tree" else "source_revision"]="0"*40; dump(path,b)
                elif kind=="phase":
                    r=d3.d2.read_json(path); r["status"]="FAIL"; dump(path,r)
                elif kind=="source_extra":
                    path.write_bytes(b"unlisted")
                    b=d3.d2.read_json(copy/"build.json"); b["source_files"]["source/extra.h"]=d3.descriptor(path)
                    dump(copy/"build.json",b)
                else:
                    report=d3.d2.read_json(path); report["promotion_allowed"]=True; dump(path,report)
                try:
                    d3.verify_report(a.input.resolve(),copy,start)
                except (ValueError,AssertionError,OSError) as error:
                    records.append({"name":name,"rejected":True,"error_type":type(error).__name__,
                                    "reason":str(error)})
                else:
                    raise ValueError("D3_TAMPER_NOT_REJECTED:"+name)
        need(len(records)==15,"D3_NEGATIVE_MATRIX_INCOMPLETE")
        receipt["status"]="PASS"
    finally:
        receipt["elapsed_seconds"]=time.monotonic()-start
        dump(a.receipt,receipt)
        if time.monotonic()-start>300:
            receipt.update(status="FAIL",reason="D3_NEGATIVE_FINAL_WRITE_BUDGET_EXCEEDED")
            dump(a.receipt,receipt)
            raise ValueError(receipt["reason"])
    print(json.dumps(receipt,sort_keys=True))
if __name__=="__main__":
    main()
