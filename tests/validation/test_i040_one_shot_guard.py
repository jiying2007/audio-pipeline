#!/usr/bin/env python3
"""Exercise I040 one-shot authority and synthesis/overlap-add boundaries."""

from contextlib import redirect_stdout
import ast,io,json,os,re,subprocess,textwrap,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
WORKFLOW=ROOT/".github/workflows/research-i040-ns-synthesis-overlap-add-transfer-decomposition-v1.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i040-ns-synthesis-overlap-add-transfer-decomposition-v1.json"
EVALUATOR=ROOT/"tests/validation/i040_ns_synthesis_overlap_add_transfer_decomposition.py"
PROBE=ROOT/"tests/validation/i040_ns_synthesis_overlap_add_transfer_probe.c"
MATERIALIZE="Materialize fresh I040 target public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero synthesis-overlap-add transfer"
CURRENT={"id":37,"run_attempt":1}
PRIOR={"id":27,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I040 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen I040 inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class I040GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"37",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":
                "research-i040-ns-synthesis-overlap-add-transfer-decomposition-v1.yml",
        }
        def api(args,**kwargs):
            if api_error:
                raise subprocess.CalledProcessError(1,args)
            endpoint=args[-1]
            if "/workflows/" in endpoint:
                pages=runs
            else:
                match=re.search(r"/runs/(\d+)/attempts/(\d+)/jobs\?",endpoint)
                self.assertIsNotNone(match,endpoint)
                pages=jobs.get(
                    (int(match.group(1)),int(match.group(2))),
                    [{"jobs":[]}],
                )
            return json.dumps(pages if "--slurp" in args else pages[0])
        with (
            patch.dict(os.environ,env,clear=True),
            patch("subprocess.check_output",side_effect=api),
            redirect_stdout(io.StringIO()),
        ):
            exec(compile(guard_source(),str(WORKFLOW),"exec"),{})

    def history(self,steps):
        return {
            "runs":[{"workflow_runs":[CURRENT,PRIOR]}],
            "jobs":{(27,1):[{"jobs":[{"steps":steps}]}]},
        }

    def test_first_dispatch_allowed(self):
        self.execute()

    def test_rerun_and_prior_consumption_blocked(self):
        with self.assertRaises(SystemExit):
            self.execute(attempt="2")
        for name in (MATERIALIZE,EVALUATE):
            for conclusion in ("success","failure","cancelled"):
                with (
                    self.subTest(name=name,conclusion=conclusion),
                    self.assertRaises(SystemExit),
                ):
                    self.execute(**self.history([step(name,conclusion)]))

    def test_pre_materialization_failure_does_not_consume(self):
        self.execute(**self.history([
            step("Build I040 synthesis-overlap-add probe","failure"),
            step(MATERIALIZE,"skipped"),
            step(EVALUATE,"skipped"),
        ]))

    def test_workflow_is_manual_only_and_guard_precedes_consumption(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertNotIn("\n  push:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        guard="      - name: Enforce one-shot I040 diagnostic execution\n"
        self.assertLess(text.index(guard),text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(text.index(guard),text.index(f"      - name: {EVALUATE}\n"))

    def test_contract_requires_fresh_zero_authority_suppression_transfer(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        a=c["fresh_diagnostic_authority"]
        self.assertEqual(len(a["target_seeds"]),6)
        self.assertEqual(len(set(a["target_seeds"])),6)
        self.assertEqual(a["candidate_limit"],0)
        self.assertEqual(a["confirmation_limit"],0)
        self.assertEqual(c["diagnostic_gates"]["noise_rms_bitwise_mismatch_frames"],0)
        self.assertLessEqual(
            c["diagnostic_gates"]["max_post_ns_partition_energy_share_gap"],2e-5
        )
        self.assertLessEqual(
            c["diagnostic_gates"]["max_predicted_post_ns_partition_energy_share_gap"],2e-5
        )
        self.assertLessEqual(
            c["diagnostic_gates"]["max_suppression_attenuation_identity_gap_db"],2e-5
        )
        self.assertLessEqual(
            c["diagnostic_gates"]["max_predicted_suppressed_power_excess_db"],2e-5
        )
        self.assertLessEqual(
            c["diagnostic_gates"]["max_synthesis_output_abs_sample_delta"],2e-5
        )
        self.assertLessEqual(
            c["diagnostic_gates"]["max_synthesis_output_rmse"],5e-6
        )
        self.assertTrue(c["exact_order_reconstruction"]["post_hoc_tolerance_not_allowed"])
        self.assertTrue(c["fixed_spectral_partitions"]["boundaries_are_fixed_not_searched"])
        self.assertFalse(
            c["synthesis_overlap_add_observation"]["selection_or_tuning_allowed"]
        )
        self.assertEqual(
            c["synthesis_overlap_add_observation"]["domains"],
            ["all","low","speech","high"],
        )
        self.assertEqual(c["synthesis_overlap_add_observation"]["fixed_ns_floor"],0.12)
        self.assertFalse(c["shipping_synthesis_reference"]["selection_or_tuning_allowed"])
        self.assertTrue(all(
            value is False for value in c["authority_boundary"].values()
        ))

    def test_probe_retains_suppression_and_mirrors_synthesis_path(self):
        text=PROBE.read_text(encoding="utf-8")
        for token in (
            "float all_noise_sum = 1.0e-18f",
            "all_noise_sum += noise_result.noise",
            "all_noise_rms_bits",
            "ns_noise_rms_bits",
            "noise_rms_bitwise_match",
            "post_ns_previous",
            "post_ns_spectrum",
            "measure_post_ns_components",
            "suppression_post = power / (noise_result.noise + 1.0e-12f)",
            "sqrtf((suppression_post - 1.0f) / suppression_post)",
            "clampf_local(suppression_gain, NS_FLOOR, 1.0f)",
            "predicted_suppressed_power",
            "suppression_speech_floor_fraction",
            "synthesize_suppressed_spectrum",
            "ap_fft(synthesis_spectrum, nfft, 1)",
            "synthesis_overlap",
            "predicted_ns_output",
            "predicted_post_ns_speech_mean_power_dbfs",
            "synthesis_max_abs_sample_delta",
        ):
            self.assertIn(token,text)
        mirror=text.split(
            "static void mirror_upstream_components",1
        )[1].split("static void process_vad_diagnostic",1)[0]
        self.assertLess(
            mirror.index("all_noise_sum += noise_result.noise"),
            mirror.index("if (k <= low_last)"),
        )
        self.assertNotIn("tolerance_candidates",text)

    def test_evaluator_requires_synthesis_transfer_and_has_no_search(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        tree=ast.parse(text)
        for token in (
            "noise_rms_bitwise_mismatch_frames",
            "noise_rms_bitwise_reconstruction",
            "suppression_gain_formula_mirrors_shipping_full_mode",
            "predicted_suppressed_power_is_observation_only",
            "inverse_fft_operation_order_mirrors_shipping",
            "synthesis_window_operation_order_mirrors_shipping",
            "overlap_add_state_is_diagnostic_only_and_mirrors_shipping",
            "predicted_synthesized_output_reanalysis_uses_same_fixed_domains",
            "synthesis_overlap_add_transfer",
            "HORIZONS=(1,2,4,8)",
        ):
            self.assertIn(token,text)
        for forbidden in (
            "band_candidates","domain_candidates","window_candidates","overlap_candidates","floor_candidates","gain_candidates","estimator_candidates","alpha_candidates",
            "threshold_candidates","mapping_candidates","argmin","argmax",
            "def source_candidate",
        ):
            self.assertNotIn(forbidden,text)
        funcs={n.name for n in tree.body if isinstance(n,ast.FunctionDef)}
        self.assertIn("analyze_case",funcs)
        self.assertIn("horizon_review",funcs)

    def test_packaging_is_hash_manifest_first_and_uses_current_result_key(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("printf '%s\\n' \"$rc\"",text)
        self.assertIn("-printf '%f\\n'",text)
        self.assertIn("+'\\n')",text)
        self.assertNotIn("printf '%s\\\\n' \"$rc\"",text)
        evaluate=text.split(
            "      - name: Evaluate candidate-zero suppression-transfer path\n",1
        )[1].split(
            "      - name: Enforce suppression-transfer-diagnostic-only authority\n",1
        )[0]
        self.assertIn("'synthesis_overlap_add_transfer':r['synthesis_overlap_add_transfer']",evaluate)
        self.assertIn("'transfer_invariants':r['transfer_invariants']",evaluate)
        self.assertNotIn("'aggregation_domain':r['aggregation_domain']",evaluate)
        self.assertNotIn("'matched_domain_transfer':r['matched_domain_transfer']",evaluate)
        self.assertNotIn("'suppression_transfer_path':r['suppression_transfer_path']",evaluate)
        self.assertLess(
            evaluate.index("while read -r file; do sha256sum"),
            evaluate.index('if test "$summary_rc" -ne 0'),
        )


if __name__=="__main__":
    unittest.main()
