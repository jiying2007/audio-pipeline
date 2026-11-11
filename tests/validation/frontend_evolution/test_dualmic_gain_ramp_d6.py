#!/usr/bin/env python3
"""D6 engineering controls and 40 qualified actual-evidence corruption tests."""
import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import dualmic_gain_ramp_d6 as d6

class Controls(unittest.TestCase):
    def test_compiler_symlink_resolves_without_relaxing_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            real=Path(tmp)/"compiler";real.write_bytes(b"compiler identity")
            link=Path(tmp)/"cc";link.symlink_to(real)
            with patch.object(d6.shutil,"which",return_value=str(link)):
                identity=d6.compiler_identity()
                self.assertEqual(identity["lookup_path"],str(link))
                self.assertEqual(identity["lookup_symlink_target"],str(real))
                self.assertEqual(identity["resolved_path"],str(real))
                self.assertEqual(d6.verify_compiler(identity),str(real))
                with self.assertRaisesRegex(ValueError,"D6_REGULAR_FILE_REQUIRED"):
                    d6.descriptor(link)
                other=Path(tmp)/"other";other.write_bytes(real.read_bytes())
                link.unlink();link.symlink_to(other)
                with self.assertRaisesRegex(ValueError,"D6_COMPILER_IDENTITY"):
                    d6.verify_compiler(identity)

    def test_compiler_bytes_change_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            real=Path(tmp)/"compiler";real.write_bytes(b"first")
            with patch.object(d6.shutil,"which",return_value=str(real)):
                identity=d6.compiler_identity()
                self.assertIsNone(identity["lookup_symlink_target"])
                real.write_bytes(b"second")
                with self.assertRaisesRegex(ValueError,"D6_COMPILER_IDENTITY"):
                    d6.verify_compiler(identity)

    def test_exact_archived_transform(self):
        raw=(d6.ROOT/"src/enhance/ap_agc.c").read_text()
        candidate=d6.derived(raw)
        self.assertIn("d6_agc_process_controlled",candidate)
        self.assertIn("ramp->previous = coefficients[159]",candidate)
        self.assertIn("if (!allow_gain_increase && target_gain > 1.0f) target_gain = 1.0f;",candidate)
        for invalid in ("",raw+raw):
            with self.assertRaisesRegex(ValueError,"D6_EXACT_INTERVENTION_SITE"):
                d6.derived(invalid)

    def test_original_state_neutral_and_dynamic_arithmetic(self):
        for target in (.1,.12589254):
            for before in (.25,.75,1.,2.,8.):
                for allow in (0,1):
                    for level in (0.,-0.,1e-20,.01,.2,2.):
                        signal=[d6.d2.f32(level if i%2 else -level) for i in range(160)]
                        args=(signal,before,allow,d6.d2.f32(target),d6.d2.f32(.7943282))
                        b,bpcm,c,coeff,pcm=d6.observation(*args,8.0,0)
                        original,_=d6.d2.gain_observation(*args)
                        self.assertEqual(b["expected_state_gain_after"],original["expected_state_gain_after"])
                        self.assertEqual(c["expected_state_gain_after"],original["expected_state_gain_after"])
                        self.assertEqual(pcm,bpcm)
                        self.assertEqual(coeff,d6.d2.bits(c["end_gain"])*160)
                        for previous in (.25,1.,8.,c["end_gain"]):
                            b,bpcm,c,coeff,pcm=d6.observation(*args,previous,1)
                            values=struct.unpack("<160f",coeff)
                            self.assertEqual(coeff[-4:],d6.d2.bits(c["end_gain"]))
                            self.assertTrue(all(abs(x)<=args[-1] for x in struct.unpack("<160f",pcm)))
                            if not allow:self.assertLessEqual(max(values),1.)
                            if previous==c["end_gain"]:self.assertEqual(pcm,bpcm)

    def test_branchwise_peak_guard_and_unity(self):
        tiny=d6.d2.f32(1e-6);limit=d6.d2.f32(1e-7)
        self.assertEqual(d6.cap_gain(2.,tiny,limit,1),(2.,0,0))
        above=struct.unpack("<f",struct.pack("<I",struct.unpack("<I",d6.d2.bits(tiny))[0]+1))[0]
        self.assertLess(d6.cap_gain(2.,above,limit,1)[0],2.)
        self.assertEqual(d6.cap_gain(2.,0.,1.,0),(1.,1,0))

    def test_nonfinite_and_extra_flag_rejected(self):
        for bad in (math.nan,math.inf,-math.inf):
            for index in range(6):
                args=[[.1]*160,1.,1,.1,.8,1.,1]
                if index==0:args[0][4]=bad
                else:args[{1:1,2:3,3:4,4:5,5:5}[index]]=bad
                with self.assertRaisesRegex(ValueError,"D6_NONFINITE_OR_CONTROL"):
                    d6.observation(*args)
        with self.assertRaisesRegex(ValueError,"D6_NONFINITE_OR_CONTROL"):
            d6.observation([.1]*160,1.,1,.1,.8,1.,2)

    def test_hard_subprocess_timeout(self):
        for remaining,expected in ((75.,30.),(2.,2.)):
            with tempfile.TemporaryDirectory() as tmp:
                with patch.object(d6,"remaining",return_value=remaining),\
                     patch.object(d6.subprocess,"run",return_value=SimpleNamespace(returncode=0)) as run:
                    d6.command(["fixed-program"],Path(tmp)/"run.log",time.monotonic())
                self.assertEqual(run.call_args.kwargs["timeout"],expected)

    def test_strong_screen_no_rounding_or_cancellation(self):
        cases=screen_fixture()
        screen=d6.development_screen(cases)
        self.assertEqual(screen["status"],"NO_ADVANCE")
        doubletalk=next(c for c in cases if c["scenario"]=="doubletalk-nominal")
        doubletalk["delta"]["common"]["near_si_sdr_change_db"]=1e-300
        self.assertTrue(d6.development_screen(cases)["passed"])
        for kind in ("common","window","far_rms","far_peak","clamp"):
            changed=copy.deepcopy(cases)
            near=next(c for c in changed if c["delta"]["common"]["near_si_sdr_change_db"] is not None)
            far=next(c for c in changed if c["scenario"]=="far-only")
            if kind=="common":near["delta"]["common"]["near_si_sdr_change_db"]=-1e-300
            elif kind=="window":near["delta"]["one_second_windows"][0]["near_si_sdr_change_db"]=-1e-300
            elif kind=="far_rms":far["stages"]["candidate"]["common"]["rms_dbfs"]+=.1
            elif kind=="far_peak":far["stages"]["candidate"]["native_whole_buffer_energy"]["peak"]+=.1
            else:near["counts"]["candidate_clamped_samples"]=1
            self.assertEqual(d6.development_screen(changed)["status"],"NO_ADVANCE")

    def test_existing_outputs_untouched(self):
        for phase,name in (("build","build-phase.json"),("run","run-phase.json"),
                           ("analysis","report.json"),("verify","readback.json")):
            with tempfile.TemporaryDirectory() as tmp:
                output=Path(tmp)/"result";output.mkdir()
                marker=output/name;marker.write_bytes(b"original")
                with patch("sys.argv",["d6",phase,"--input",tmp,"--output",str(output)]):
                    with self.assertRaisesRegex(ValueError,"D6_(FRESH_OUTPUT|NEW_PHASE_RECEIPT|NEW_PHASE_OUTPUT)_REQUIRED"):
                        d6.main()
                self.assertEqual(marker.read_bytes(),b"original")
                self.assertEqual({p.name for p in output.iterdir()},{name})

    def test_output_and_parent_symlinks(self):
        for phase in ("build","run","analysis","verify"):
            with tempfile.TemporaryDirectory() as tmp:
                target=Path(tmp)/"original";target.mkdir()
                (target/"keep").write_bytes(b"original")
                link=Path(tmp)/"link";link.symlink_to(target,target_is_directory=True)
                with patch("sys.argv",["d6",phase,"--input",tmp,"--output",str(link)]):
                    with self.assertRaises(ValueError):d6.main()
                self.assertEqual({p.name for p in target.iterdir()},{"keep"})

    def test_negative_receipts_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt=Path(tmp)/"receipt";receipt.write_bytes(b"original")
            with self.assertRaisesRegex(ValueError,"D6_FRESH_NEGATIVE_RECEIPT_REQUIRED"):
                negatives(Path(tmp),Path(tmp),receipt)
            self.assertEqual(receipt.read_bytes(),b"original")
            receipt.unlink();target=Path(tmp)/"absent";receipt.symlink_to(target)
            with self.assertRaisesRegex(ValueError,"D6_FRESH_NEGATIVE_RECEIPT_REQUIRED"):
                negatives(Path(tmp),Path(tmp),receipt)
            self.assertFalse(target.exists())

    def test_source_closure_rejects_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"extra").mkdir()
            with self.assertRaisesRegex(ValueError,"CLOSURE"):
                d6.closure(root,set(),"CLOSURE")

def screen_fixture():
    cases=[]
    for entry in d6.contract()["original_d2_case_input_lock"]["cases"]:
        catalog=entry["catalog"];scored=entry["clean_near"] is not None
        span={"near_si_sdr_change_db":0.0 if scored else None}
        level={"rms_dbfs":-20.0,"peak":.2}
        stage={"common":dict(level),"one_second_windows":[dict(level)],
               "native_whole_buffer_energy":dict(level)}
        cases.append({"key":catalog["key"],"scenario":catalog["scenario"],
                      "delta":{"common":dict(span),"one_second_windows":[dict(span)]},
                      "stages":{"baseline":copy.deepcopy(stage),"candidate":copy.deepcopy(stage)},
                      "counts":{"baseline_clamped_samples":0,"candidate_clamped_samples":0}})
    return cases

def rewrite(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n")

def reseal_report(output):
    path=output/"readback.json"
    value=d6.d2.read_json(path);value["report"]=d6.descriptor(output/"report.json")
    rewrite(path,value)

def reseal_source(output):
    path=output/"build.json";value=d6.d2.read_json(path)
    value["source_files"]={p.relative_to(output/"source").as_posix():d6.descriptor(p)
                           for p in (output/"source").rglob("*") if p.is_file()}
    rewrite(path,value)

def negatives(input_root,original,receipt_path):
    start=time.monotonic()
    d6.need(not receipt_path.exists() and d6.no_symlink_path(receipt_path),
            "D6_FRESH_NEGATIVE_RECEIPT_REQUIRED")
    expected={
            "baseline_sample": "D6_BASELINE_NOT_ORIGINAL",
            "candidate_sample": "D6_CANDIDATE_OUTPUT_FORMULA",
            "baseline_state": "D6_BASELINE_FULL_STATE",
            "candidate_state": "D6_CANDIDATE_STATE_NOT_ORIGINAL",
            "coefficient_sample": "D6_COEFFICIENT_FORMULA",
            "coefficient_endpoint": "D6_COEFFICIENT_ENDPOINT",
            "extra_previous": "D6_EXTRA_PREVIOUS",
            "extra_initialized": "D6_EXTRA_INITIALIZED",
            "start_gain": "D6_START_GAIN",
            "end_gain": "D6_END_GAIN",
            "trace_control": "D6_TRACE_CONTROLS",
            "zero_flag": "D6_ZERO_FLAG",
            "control_bytes": "D6_CONTROLS_CHANGED",
            "target": "D6_READBACK_CASE_DIFFERS",
            "alpha": "D6_READBACK_CASE_DIFFERS",
            "wrong_window": "D6_READBACK_CASE_DIFFERS",
            "missing_case": "D6_REPORT_CASE_SET",
            "null_to_zero": "D6_READBACK_CASE_DIFFERS",
            "screen_decision": "D6_SCREEN_DECISION",
            "screen_predicate": "D6_SCREEN_PREDICATES",
            "source_tree": "D6_SOURCE_IDENTITY",
            "report_source": "D6_REPORT_SOURCE_CHANGED",
            "source_resealed": "D6_SAVED_SOURCE_CHANGED",
            "candidate_source_resealed": "D6_CANDIDATE_DERIVATION",
            "header_resealed": "D6_SAVED_HEADER_CHANGED",
            "argv": "D6_BUILD_ARGV_CHANGED",
            "execution_argv": "D6_COMMAND_ARGV_CHANGED",
            "source_extra_file": "D6_SOURCE_CLOSURE",
            "source_extra_dir": "D6_SOURCE_CLOSURE",
            "extra_file": "D6_OUTPUT_CLOSURE",
            "extra_dir": "D6_OUTPUT_CLOSURE",
            "output_symlink": "D6_OUTPUT_CLOSURE",
            "failed_build_phase": "D6_PHASE_FAILED",
            "failed_run_phase": "D6_PHASE_FAILED",
            "failed_analysis_phase": "D6_PHASE_FAILED",
            "failed_verify_phase": "D6_PHASE_FAILED",
            "failed_command": "D6_COMMAND_RECEIPT_FAILED",
            "saved_admission": "D6_SAVED_INPUT_CHANGED",
            "input_binding": "D6_INPUT_NOT_ADMITTED",
            "readback_receipt": "D6_READBACK_RECEIPT_CHANGED"
    }
    records=[];receipt={"experiment":d6.EXPERIMENT,"status":"FAIL","budget_seconds":300,"tests":records}
    try:
        d6.phase_pass(original,"verify")
        d6.need((original/"readback.json").is_file(),"D6_QUALIFIED_BASELINE_REQUIRED")
        d6.need(set(expected)==set(d6.contract()["test_contract"]["actual_negative_mutations"]) and len(expected)==40,
                "D6_NEGATIVE_CONTRACT_SET")
        d6.verify_report(input_root,original,start)
        receipt["unmodified_baseline_verified"]=True
        first=d6.d2.read_json(original/"report.json")["cases"][0]["key"]
        for kind,reason in expected.items():
            d6.remaining(start,300)
            with tempfile.TemporaryDirectory(prefix="d6-negative-") as tmp:
                output=Path(tmp)/"result";shutil.copytree(original,output)
                folder=output/"cases"/first;trial_input=input_root
                if kind in ("baseline_sample","candidate_sample"):
                    path=folder/("baseline.f32le" if kind=="baseline_sample" else "candidate.f32le")
                    data=bytearray(path.read_bytes());data[:4]=struct.pack("<f",.123);path.write_bytes(data)
                elif kind in ("coefficient_sample","coefficient_endpoint"):
                    path=folder/"candidate-gain.f32le";data=bytearray(path.read_bytes())
                    offset=636 if kind=="coefficient_endpoint" else 0
                    data[offset:offset+4]=struct.pack("<f",.123);path.write_bytes(data)
                elif kind in ("baseline_state","candidate_state","extra_previous","extra_initialized",
                              "start_gain","end_gain","trace_control","zero_flag"):
                    path=folder/"trace.bin";data=bytearray(path.read_bytes())
                    offset={"baseline_state":4,"candidate_state":36,"extra_previous":48,"extra_initialized":52,
                            "start_gain":64,"end_gain":68,"trace_control":72,"zero_flag":80}[kind]
                    data[offset:offset+4]=struct.pack("<I",3) if kind in ("extra_initialized","trace_control","zero_flag") else struct.pack("<f",.123)
                    path.write_bytes(data)
                elif kind=="control_bytes":
                    path=folder/"control.bin";data=bytearray(path.read_bytes());data[0]^=1;path.write_bytes(data)
                elif kind in ("target","alpha","wrong_window","missing_case","null_to_zero","report_source","screen_decision","screen_predicate"):
                    path=output/"report.json";value=d6.d2.read_json(path)
                    if kind in ("target","alpha"):
                        value["cases"][0]["frame_audit"][0]["candidate"]["target_gain" if kind=="target" else "alpha"]+=.1
                    elif kind=="wrong_window":value["cases"][0]["stages"]["candidate"]["one_second_windows"][0]["physical_sample_range"][0]+=160
                    elif kind=="missing_case":value["cases"].pop()
                    elif kind=="report_source":value["source"]["revision"]="0"*40
                    elif kind=="screen_decision":
                        value["development_screen"]["status"]="CORRUPTED"
                        value["status"]="CORRUPTED"
                    elif kind=="screen_predicate":
                        predicates=value["development_screen"]["predicates"]
                        predicates["all32_common_nonnegative"]=not predicates["all32_common_nonnegative"]
                    else:
                        case=next(c for c in value["cases"] if c["group"]=="C")
                        case["stages"]["candidate"]["common"]["near_si_sdr_db"]=0.0
                        case["stages"]["candidate"]["common"]["near_si_sdr_null_reason"]=None
                    rewrite(path,value);reseal_report(output)
                elif kind in ("source_tree","argv"):
                    path=output/"build.json";value=d6.d2.read_json(path)
                    if kind=="source_tree":value["source"]["tree"]="0"*40
                    else:value["command"].append("-ffast-math")
                    rewrite(path,value)
                elif kind in ("source_resealed","candidate_source_resealed","header_resealed"):
                    path=output/"source"/("repository/"+d6.PLAN if kind=="source_resealed" else
                                          "candidate-api.h" if kind=="header_resealed" else "candidate.c")
                    path.write_bytes(path.read_bytes()+b"\n");reseal_source(output)
                elif kind in ("execution_argv","failed_command"):
                    path=folder/"execution-command.json";value=d6.d2.read_json(path)
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
                    path=output/(phase+"-phase.json");value=d6.d2.read_json(path);value["status"]="FAIL";rewrite(path,value)
                elif kind=="saved_admission":
                    path=output/"admission.json";value=d6.d2.read_json(path);value["source_revision"]="0"*40;rewrite(path,value)
                elif kind=="input_binding":
                    trial_input=Path(tmp)/"input";trial_input.mkdir()
                    value=d6.d2.read_json(input_root/"admission.json");value["source_revision"]="0"*40
                    rewrite(trial_input/"admission.json",value)
                elif kind=="readback_receipt":
                    path=output/"readback.json";value=d6.d2.read_json(path);value["status"]="FAIL";rewrite(path,value)
                try:
                    d6.verify_report(trial_input,output,start)
                except ValueError as error:
                    d6.need(str(error)==reason,"D6_UNEXPECTED_REJECTION:"+kind+":"+str(error))
                    records.append({"name":kind,"rejected":True,"reason":str(error),"expected_reason":reason})
                else:raise ValueError("D6_MUTATION_NOT_REJECTED:"+kind)
        d6.need(len(records)==len(expected),"D6_NEGATIVE_COUNT")
        receipt["status"]="PASS"
    except Exception as error:
        receipt.update(reason=str(error),error_type=type(error).__name__)
        raise
    finally:
        receipt["elapsed_seconds"]=time.monotonic()-start;d6.dump(receipt_path,receipt)
        if time.monotonic()-start>300:
            receipt.update(status="FAIL",reason="D6_NEGATIVE_FINAL_WRITE_BUDGET_EXCEEDED")
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
    d6.need(args.input is not None and args.output is not None and args.receipt is not None,"D6_REQUIRED_PATHS")
    negatives(args.input.absolute(),args.output.absolute(),args.receipt.absolute())

if __name__=="__main__":cli()
