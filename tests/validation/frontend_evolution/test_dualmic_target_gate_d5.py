#!/usr/bin/env python3
"""D5 engineering contracts and qualified actual-evidence corruption tests."""
import argparse
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import time
import unittest
from unittest.mock import patch
import dualmic_target_gate_d5 as d5

class Controls(unittest.TestCase):
    def test_compiler_symlink_resolves_without_relaxing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            real=Path(tmp)/"compiler";real.write_bytes(b"compiler identity")
            link=Path(tmp)/"cc";link.symlink_to(real)
            with patch.object(d5.shutil,"which",return_value=str(link)):
                identity=d5.compiler_identity()
                self.assertEqual(identity["lookup_path"],str(link))
                self.assertEqual(identity["lookup_symlink_target"],str(real))
                self.assertEqual(identity["resolved_path"],str(real))
                self.assertEqual(d5.verify_compiler(identity),str(real))
                with self.assertRaisesRegex(ValueError,"D5_REGULAR_FILE_REQUIRED"):
                    d5.descriptor(link)
                other=Path(tmp)/"other";other.write_bytes(real.read_bytes())
                link.unlink();link.symlink_to(other)
                with self.assertRaisesRegex(ValueError,"D5_COMPILER_IDENTITY"):
                    d5.verify_compiler(identity)

    def test_compiler_bytes_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            real=Path(tmp)/"compiler";real.write_bytes(b"first")
            with patch.object(d5.shutil,"which",return_value=str(real)):
                identity=d5.compiler_identity()
                self.assertIsNone(identity["lookup_symlink_target"])
                real.write_bytes(b"second")
                with self.assertRaisesRegex(ValueError,"D5_COMPILER_IDENTITY"):
                    d5.verify_compiler(identity)

    def test_exact_one_statement_transform(self):
        raw="void ap_agc_process_controlled(void) {\n"+d5.BEFORE+"\n}\n"
        self.assertEqual(d5.derived(raw),"void d5_agc_process_controlled(void) {\n\n}\n")
        for invalid in ("",raw+raw):
            with self.assertRaisesRegex(ValueError,"D5_EXACT_INTERVENTION_SITE"):
                d5.derived(invalid)

    def test_signed_zero_tiny_and_profiles(self):
        for target in (.1,.12589254):
            for before in (.25,.75,1.,2.,8.):
                for allow in (0,1):
                    for level in (0.,-0.,1e-20,.01,.2,2.):
                        signal=[d5.d2.f32(level)]*160
                        b,_=d5.observation(signal,before,allow,d5.d2.f32(target),d5.d2.f32(.7943282),False)
                        c,pcm=d5.observation(signal,before,allow,d5.d2.f32(target),d5.d2.f32(.7943282),True)
                        formula,_=d5.d2.gain_observation(signal,before,1,d5.d2.f32(target),d5.d2.f32(.7943282))
                        self.assertEqual(c["expected_state_gain_after"],formula["expected_state_gain_after"])
                        self.assertEqual(c["target_gate_cap_active"],0)
                        if allow:self.assertEqual(b,c)
                        else:self.assertLessEqual(c["applied_gain"],1.)
                        self.assertTrue(all(abs(x)<=d5.d2.f32(.7943282) for x in struct.unpack("<160f",pcm)))

    def test_original_no_target_opportunity(self):
        before=1.
        for _ in range(10):
            b,bpcm=d5.observation([.5]*160,before,0,.1,.8,False)
            c,cpcm=d5.observation([.5]*160,before,0,.1,.8,True)
            self.assertEqual((b,bpcm),(c,cpcm))
            before=b["expected_state_gain_after"]

    def test_existing_outputs_untouched(self):
        for phase,name in (("build","build-phase.json"),("run","run-phase.json"),
                           ("analysis","report.json"),("verify","readback.json")):
            with tempfile.TemporaryDirectory() as tmp:
                output=Path(tmp)/"result";output.mkdir()
                marker=output/name;marker.write_bytes(b"original")
                with patch("sys.argv",["d5",phase,"--input",tmp,"--output",str(output)]):
                    with self.assertRaisesRegex(ValueError,"D5_(FRESH_OUTPUT|NEW_PHASE_RECEIPT|NEW_PHASE_OUTPUT)_REQUIRED"):
                        d5.main()
                self.assertEqual(marker.read_bytes(),b"original")
                self.assertEqual({p.name for p in output.iterdir()},{name})

    def test_output_and_parent_symlinks(self):
        for phase in ("build","run","analysis","verify"):
            with tempfile.TemporaryDirectory() as tmp:
                target=Path(tmp)/"original";target.mkdir()
                (target/"keep").write_bytes(b"original")
                link=Path(tmp)/"link";link.symlink_to(target,target_is_directory=True)
                with patch("sys.argv",["d5",phase,"--input",tmp,"--output",str(link)]):
                    with self.assertRaises(ValueError):d5.main()
                self.assertEqual({p.name for p in target.iterdir()},{"keep"})

    def test_negative_receipts_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/"receipt";receipt.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError,"D5_FRESH_NEGATIVE_RECEIPT_REQUIRED"):
                negatives(Path(tmp),Path(tmp),receipt)
            self.assertEqual(receipt.read_bytes(),b"original")
            receipt.unlink();target=Path(tmp)/"absent";receipt.symlink_to(target)
            with self.assertRaisesRegex(ValueError,"D5_FRESH_NEGATIVE_RECEIPT_REQUIRED"):
                negatives(Path(tmp),Path(tmp),receipt)
            self.assertFalse(target.exists())

    def test_source_closure_rejects_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"extra").mkdir()
            with self.assertRaisesRegex(ValueError,"CLOSURE"):
                d5.closure(root,set(),"CLOSURE")

def rewrite(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n")

def reseal_report(output):
    path=output/"readback.json"
    value=d5.d2.read_json(path);value["report"]=d5.descriptor(output/"report.json")
    rewrite(path,value)

def reseal_source(output):
    path=output/"build.json";value=d5.d2.read_json(path)
    value["source_files"]={p.relative_to(output/"source").as_posix():d5.descriptor(p)
                           for p in (output/"source").rglob("*") if p.is_file()}
    rewrite(path,value)

def negatives(input_root,original,receipt_path):
    start=time.monotonic()
    d5.need(not receipt_path.exists() and d5.no_symlink_path(receipt_path),
            "D5_FRESH_NEGATIVE_RECEIPT_REQUIRED")
    expected={
        "baseline_sample":"D5_BASELINE_NOT_ORIGINAL",
        "candidate_sample":"D5_CANDIDATE_OUTPUT_FORMULA",
        "baseline_state":"D5_BASELINE_FULL_STATE",
        "candidate_state":"D5_CANDIDATE_STATE_FORMULA",
        "applied_gain":"D5_APPLIED_GAIN_FORMULA",
        "trace_control":"D5_TRACE_CONTROLS",
        "zero_flag":"D5_ZERO_FLAG",
        "control_bytes":"D5_CONTROLS_CHANGED",
        "target":"D5_READBACK_CASE_DIFFERS",
        "alpha":"D5_READBACK_CASE_DIFFERS",
        "wrong_window":"D5_READBACK_CASE_DIFFERS",
        "missing_case":"D5_REPORT_CASE_SET",
        "null_to_zero":"D5_READBACK_CASE_DIFFERS",
        "source_tree":"D5_SOURCE_IDENTITY",
        "report_source":"D5_REPORT_SOURCE_CHANGED",
        "source_resealed":"D5_SAVED_SOURCE_CHANGED",
        "candidate_source_resealed":"D5_CANDIDATE_DERIVATION",
        "argv":"D5_BUILD_ARGV_CHANGED",
        "execution_argv":"D5_COMMAND_ARGV_CHANGED",
        "source_extra_file":"D5_SOURCE_CLOSURE",
        "source_extra_dir":"D5_SOURCE_CLOSURE",
        "extra_file":"D5_OUTPUT_CLOSURE",
        "extra_dir":"D5_OUTPUT_CLOSURE",
        "output_symlink":"D5_OUTPUT_CLOSURE",
        "failed_build_phase":"D5_PHASE_FAILED",
        "failed_run_phase":"D5_PHASE_FAILED",
        "failed_analysis_phase":"D5_PHASE_FAILED",
        "failed_verify_phase":"D5_PHASE_FAILED",
        "failed_command":"D5_COMMAND_RECEIPT_FAILED",
        "saved_admission":"D5_SAVED_INPUT_CHANGED",
        "input_binding":"D5_INPUT_NOT_ADMITTED",
        "readback_receipt":"D5_READBACK_RECEIPT_CHANGED"}
    records=[];receipt={"experiment":d5.EXPERIMENT,"status":"FAIL","budget_seconds":300,"tests":records}
    try:
        d5.phase_pass(original,"verify")
        d5.need((original/"readback.json").is_file(),"D5_QUALIFIED_BASELINE_REQUIRED")
        d5.verify_report(input_root,original,start)
        receipt["unmodified_baseline_verified"]=True
        first=d5.d2.read_json(original/"report.json")["cases"][0]["key"]
        for kind,reason in expected.items():
            d5.remaining(start,300)
            with tempfile.TemporaryDirectory(prefix="d5-negative-") as tmp:
                output=Path(tmp)/"result";shutil.copytree(original,output)
                folder=output/"cases"/first;trial_input=input_root
                if kind in ("baseline_sample","candidate_sample"):
                    path=folder/("baseline.f32le" if kind=="baseline_sample" else "candidate.f32le")
                    data=bytearray(path.read_bytes());data[:4]=struct.pack("<f",.123);path.write_bytes(data)
                elif kind in ("baseline_state","candidate_state","applied_gain","trace_control","zero_flag"):
                    path=folder/"trace.bin";data=bytearray(path.read_bytes())
                    offset={"baseline_state":4,"candidate_state":36,"applied_gain":52,"trace_control":56,"zero_flag":64}[kind]
                    data[offset:offset+4]=struct.pack("<I",3) if kind in ("trace_control","zero_flag") else struct.pack("<f",.123)
                    path.write_bytes(data)
                elif kind=="control_bytes":
                    path=folder/"control.bin";data=bytearray(path.read_bytes());data[0]^=1;path.write_bytes(data)
                elif kind in ("target","alpha","wrong_window","missing_case","null_to_zero","report_source"):
                    path=output/"report.json";value=d5.d2.read_json(path)
                    if kind in ("target","alpha"):
                        value["cases"][0]["frame_audit"][0]["candidate"]["target_gain" if kind=="target" else "alpha"]+=.1
                    elif kind=="wrong_window":value["cases"][0]["stages"]["candidate"]["one_second_windows"][0]["physical_sample_range"][0]+=160
                    elif kind=="missing_case":value["cases"].pop()
                    elif kind=="report_source":value["source"]["revision"]="0"*40
                    else:
                        case=next(c for c in value["cases"] if c["group"]=="C")
                        case["stages"]["candidate"]["common"]["near_si_sdr_db"]=0.0
                        case["stages"]["candidate"]["common"]["near_si_sdr_null_reason"]=None
                    rewrite(path,value);reseal_report(output)
                elif kind in ("source_tree","argv"):
                    path=output/"build.json";value=d5.d2.read_json(path)
                    if kind=="source_tree":value["source"]["tree"]="0"*40
                    else:value["command"].append("-ffast-math")
                    rewrite(path,value)
                elif kind in ("source_resealed","candidate_source_resealed"):
                    path=output/"source"/("repository/"+d5.PLAN if kind=="source_resealed" else "candidate.c")
                    path.write_bytes(path.read_bytes()+b"\n");reseal_source(output)
                elif kind in ("execution_argv","failed_command"):
                    path=folder/"execution-command.json";value=d5.d2.read_json(path)
                    if kind=="execution_argv":value["argv"][-1]="1"
                    else:value["status"]="FAIL"
                    rewrite(path,value)
                elif kind=="source_extra_file":(output/"source/extra").write_bytes(b"extra")
                elif kind=="source_extra_dir":(output/"source/extra").mkdir()
                elif kind=="extra_file":(output/"extra").write_bytes(b"extra")
                elif kind=="extra_dir":(output/"extra").mkdir()
                elif kind=="output_symlink":(output/"extra").symlink_to(output/"report.json")
                elif kind.startswith("failed_"):
                    phase=kind[len("failed_"):-len("_phase")]
                    path=output/(phase+"-phase.json");value=d5.d2.read_json(path);value["status"]="FAIL";rewrite(path,value)
                elif kind=="saved_admission":
                    path=output/"admission.json";value=d5.d2.read_json(path);value["source_revision"]="0"*40;rewrite(path,value)
                elif kind=="input_binding":
                    trial_input=Path(tmp)/"input";trial_input.mkdir()
                    value=d5.d2.read_json(input_root/"admission.json");value["source_revision"]="0"*40
                    rewrite(trial_input/"admission.json",value)
                elif kind=="readback_receipt":
                    path=output/"readback.json";value=d5.d2.read_json(path);value["status"]="FAIL";rewrite(path,value)
                try:
                    d5.verify_report(trial_input,output,start)
                except ValueError as error:
                    d5.need(str(error)==reason,"D5_UNEXPECTED_REJECTION:"+kind+":"+str(error))
                    records.append({"name":kind,"rejected":True,"reason":str(error),"expected_reason":reason})
                else:raise ValueError("D5_MUTATION_NOT_REJECTED:"+kind)
        d5.need(len(records)==len(expected),"D5_NEGATIVE_COUNT")
        receipt["status"]="PASS"
    except Exception as error:
        receipt.update(reason=str(error),error_type=type(error).__name__)
        raise
    finally:
        receipt["elapsed_seconds"]=time.monotonic()-start;d5.dump(receipt_path,receipt)
        if time.monotonic()-start>300:
            receipt.update(status="FAIL",reason="D5_NEGATIVE_FINAL_WRITE_BUDGET_EXCEEDED")
            rewrite(receipt_path,receipt);raise ValueError(receipt["reason"])
    print(json.dumps(receipt,sort_keys=True))

def cli():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--input",type=Path);p.add_argument("--output",type=Path);p.add_argument("--receipt",type=Path)
    args=p.parse_args()
    if args.self_test:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    d5.need(args.input is not None and args.output is not None and args.receipt is not None,"D5_REQUIRED_PATHS")
    negatives(args.input.resolve(),args.output.absolute(),args.receipt.absolute())

if __name__=="__main__":cli()
