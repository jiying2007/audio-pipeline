#!/usr/bin/env python3
"""D4 statistic controls and actual saved-evidence corruption tests."""
import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

import dualmic_window_d4 as d4

class Controls(unittest.TestCase):
    def row(self,index,before,after,zero=False,reset=0):
        return {"frame":index,"state_before":before,"state_after":after,"zero":zero,"reset":reset,
                "allow":1,"target_gate_cap_active":0,"output_gate_cap_active":0,"peak_cap_active":0,
                "applied_gain":after,"input_peak":0.0 if zero else 0.25,"input_rms":1e-7 if zero else .1}
    def test_signed_zero(self):
        self.assertTrue(d4.finite_zero([0.0,-0.0]))
    def test_tiny_nonzero(self):
        self.assertFalse(d4.finite_zero([0.0,1e-30]))
    def test_nonfinite_refused(self):
        for x in (math.nan,math.inf,-math.inf):
            with self.assertRaises(ValueError):
                d4.finite_zero([0.0,x])
    def test_no_rms_zero_proxy(self):
        r=self.row(0,1,2,True)
        s=d4.span_summary([r],0,1)
        self.assertEqual(s["zero_frames"],1)
        self.assertEqual(s["state_update_directions"]["zero"]["up"],1)
    def test_reset_not_cross_row_fall(self):
        rows=[self.row(0,7,8),self.row(1,1,1,reset=1)]
        s=d4.span_summary(rows,1,2)
        self.assertEqual(s["state_update_directions"]["nonzero"],{"up":0,"down":0,"unchanged":1})
        self.assertEqual(s["event_frame_ids"]["reset"],[1])
    def test_directions_and_frame_zero(self):
        rows=[self.row(0,1,2,True),self.row(1,2,1),self.row(2,1,1)]
        s=d4.span_summary(rows,1,3)
        self.assertEqual(s["original_frame_range"],[1,3])
        self.assertEqual(s["zero_frames"],0)
        self.assertEqual(s["state_update_directions"]["nonzero"],{"up":0,"down":1,"unchanged":1})
        self.assertEqual(s["ranges"]["state_before"],{"first":2,"last":1,"min":1,"max":2})
    def test_row_id_shift_refused(self):
        rows=[self.row(1,1,1)]
        with self.assertRaises(ValueError):
            d4.span_summary(rows,0,1)
    def test_short_last_window(self):
        spans=[[a,min(a+16000,96000-160)] for a in range(0,96000-160,16000)]
        frames=[[(a+160)//160,(b+160)//160] for a,b in spans]
        self.assertEqual(frames,[[1,101],[101,201],[201,301],[301,401],[401,501],[501,600]])
        self.assertEqual(sum(b-a for a,b in frames),599)

    def test_existing_analysis_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"result";output.mkdir()
            marker=output/"analysis-phase.json";marker.write_bytes(b"original")
            with patch("sys.argv",["d4","analysis","--input",tmp,"--output",str(output)]):
                with self.assertRaisesRegex(ValueError,"D4_FRESH_OUTPUT_REQUIRED"):
                    d4.main()
            self.assertEqual(marker.read_bytes(),b"original")
            self.assertEqual({p.name for p in output.iterdir()},{"analysis-phase.json"})
    def test_existing_readback_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"result";output.mkdir()
            marker=output/"readback.json";marker.write_bytes(b"original")
            with patch("sys.argv",["d4","verify","--input",tmp,"--output",str(output)]):
                with self.assertRaisesRegex(ValueError,"D4_NEW_VERIFY_RECEIPT_REQUIRED"):
                    d4.main()
            self.assertEqual(marker.read_bytes(),b"original")
            self.assertEqual({p.name for p in output.iterdir()},{"readback.json"})
    def test_output_symlink_is_not_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"original";target.mkdir()
            marker=target/"keep";marker.write_bytes(b"original")
            output=Path(tmp)/"link";output.symlink_to(target,target_is_directory=True)
            with patch("sys.argv",["d4","analysis","--input",tmp,"--output",str(output)]):
                with self.assertRaisesRegex(ValueError,"D4_FRESH_OUTPUT_REQUIRED"):
                    d4.main()
            self.assertEqual({p.name for p in target.iterdir()},{"keep"})
            self.assertEqual(marker.read_bytes(),b"original")

    def test_existing_negative_receipt_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/"integrity.json";receipt.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError,"D4_FRESH_NEGATIVE_RECEIPT_REQUIRED"):
                negatives(Path(tmp),Path(tmp)/"missing",receipt)
            self.assertEqual(receipt.read_bytes(),b"original")

def mutate(report,kind):
    windows=report["cases"][0]["windows"]
    if kind=="window_offset": windows[0]["gain"]["original_frame_range"][0]-=1
    elif kind=="missing_window": windows.pop()
    elif kind=="duplicate_window": windows.append(copy.deepcopy(windows[-1]))
    elif kind=="swapped_windows": windows[0],windows[1]=windows[1],windows[0]
    elif kind=="gain_count": windows[0]["gain"]["zero_frames"]+=1
    elif kind=="cross_reset":
        c=next(c for c in report["cases"] if c["reset_coordinates"])
        c["native_gain"]["state_update_directions"]["nonzero"]["down"]+=1
    elif kind=="score":
        for c in report["cases"]:
            for w in c["windows"]:
                score=w["original_d2_stages"]["pre_agc"]["near_si_sdr_db"]
                if score is not None:
                    w["original_d2_stages"]["pre_agc"]["near_si_sdr_db"]=score+1
                    return
        raise ValueError("no scored window")
    elif kind=="null":
        c=next(c for c in report["cases"] if c["group"]=="C")
        c["windows"][0]["original_d2_stages"]["pre_agc"]["near_si_sdr_db"]=0.0
        c["windows"][0]["original_d2_stages"]["pre_agc"]["near_si_sdr_null_reason"]=None
    elif kind=="revision": report["source"]["revision"]="0"*40
    elif kind=="tree": report["source"]["tree"]="0"*40

def negatives(input_root,original,receipt_path):
    start=time.monotonic()
    d4.need(not receipt_path.exists() and not receipt_path.is_symlink(),"D4_FRESH_NEGATIVE_RECEIPT_REQUIRED")
    kinds=("window_offset","missing_window","duplicate_window","swapped_windows","gain_count",
           "cross_reset","score","null","revision","tree","root_member","source_member",
           "saved_admission","saved_report","saved_contract","root_type")
    expected={kind:"D4_READBACK_DIFFERS" for kind in kinds}
    expected.update(root_member="D4_OUTPUT_MEMBERS",root_type="D4_OUTPUT_MEMBERS",source_member="D4_SOURCE_MEMBERS",
                    saved_admission="D4_SAVED_INPUT_CHANGED",saved_report="D4_SAVED_INPUT_CHANGED",
                    saved_contract="D4_SAVED_SOURCE_CHANGED")
    records=[];receipt={"experiment":d4.EXPERIMENT,"status":"FAIL","budget_seconds":300,"tests":records}
    try:
        d4.phase_pass(original,"verify")
        readback=d4.d2.read_json(original/"readback.json")
        d4.need(readback["status"]=="PASS" and
                readback["report"]==d4.descriptor(original/"report.json") and
                readback["DSP_executed"] is False and readback["models_executed"] is False,
                "D4_QUALIFIED_ORIGINAL_REQUIRED")
        d4.verify(input_root,original,start)
        receipt["unmodified_baseline_verified"]=True
        for kind in kinds:
            d4.remaining(start,300)
            with tempfile.TemporaryDirectory(prefix="d4-negative-") as tmp:
                output=Path(tmp)/"result";shutil.copytree(original,output)
                if kind=="root_type":
                    p=output/"verify-phase.json";p.unlink();p.mkdir();(p/"extra.bin").write_bytes(b"unlisted")
                elif kind=="root_member": (output/"extra.bin").write_bytes(b"unlisted")
                elif kind=="source_member": (output/"source/extra.py").write_bytes(b"unlisted")
                elif kind=="saved_admission":
                    r=d4.d2.read_json(output/"admission.json");r["source_revision"]="0"*40
                    d4.dump(output/"admission.json",r)
                elif kind=="saved_report":
                    r=d4.d2.read_json(output/"original-d2-report.json");r["promotion_allowed"]=True
                    d4.dump(output/"original-d2-report.json",r)
                elif kind=="saved_contract":
                    p=output/"source"/d4.PLAN;p.write_bytes(p.read_bytes()+b"\n")
                else:
                    r=d4.d2.read_json(output/"report.json");mutate(r,kind);d4.dump(output/"report.json",r)
                try:
                    d4.verify(input_root,output,start)
                except ValueError as error:
                    d4.need(str(error) == expected[kind], "D4_UNEXPECTED_REJECTION:"+kind+":"+str(error))
                    records.append({"name":kind,"rejected":True,"reason":str(error),
                                    "expected_reason":expected[kind],"error_type":type(error).__name__})
                else:
                    raise ValueError("D4_MUTATION_NOT_REJECTED:"+kind)
        d4.need(len(records)==16,"D4_NEGATIVE_COUNT")
        receipt["status"]="PASS"
    except Exception as error:
        receipt.update(reason=str(error),error_type=type(error).__name__)
        raise
    finally:
        receipt["elapsed_seconds"]=time.monotonic()-start;d4.dump(receipt_path,receipt)
        if time.monotonic()-start>300:
            receipt.update(status="FAIL",reason="D4_NEGATIVE_FINAL_WRITE_BUDGET_EXCEEDED")
            d4.dump(receipt_path,receipt);raise ValueError(receipt["reason"])
    print(json.dumps(receipt,sort_keys=True))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--input",type=Path);p.add_argument("--output",type=Path);p.add_argument("--receipt",type=Path)
    args=p.parse_args()
    if args.self_test:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    d4.need(args.input is not None and args.output is not None and args.receipt is not None,"D4_REQUIRED_PATHS")
    negatives(args.input.resolve(),args.output.resolve(),args.receipt.resolve())
