#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

plan = Path('docs/program/plan.json')
s = plan.read_text()
new_block = '''    {
      "id": "I009", "priority": 75, "status": "CLOSED", "lane": "acoustic",
      "title": "Activity double-talk admission root cause after I006 handoff",
      "depends_on": ["I006", "P001"], "handler": null, "contract": "docs/program/iterations/I009-closure.json",
      "exit": "Fresh Activity gap and signal-domain root cause are archived; the only authorized residual/echo source candidate is rejected by frozen fresh pure-far and Hosted Real AEC movement regressions; confirmation remains unused and v2.3.12 stays shipping",
      "evidence": [
        {"source_sha": "e61b2998bde4902159eed07c8befc9703f014c1d", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34031305098", "meaning": "Fresh I009 Development baseline: artifact 9988691434/digest ab6f36bc... independently verified 284/284; 5/6 partitions fail the frozen double-talk activity gate with the inherited 3 smoothed-limit + 3 both-gates mechanism reproduced on new seeds."},
        {"source_sha": "317756d9feb17de5f7065b619e08dd7a77b9f166", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34031731756", "meaning": "Candidate-zero direct echo-normalization differential: artifact 9988834254/digest 3111f6ac... independently verified 301/301; 6/6 near/far repaired but 0/3 pure-far protected, so direct mic/echo normalization was rejected without source candidate authority."},
        {"source_sha": "497c3ca3a6be0a4e319a3493e256eac7391a7f18", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34033842566", "meaning": "Candidate-zero residual/echo rescue differential: artifact 9989499865/digest 1965a49e... independently verified 301/301; frozen 6/6 near/far + 3/3 pure-far support gates all pass with no Activity numeric threshold changes, authorizing exactly one structural source candidate."},
        {"source_sha": "7acd0a3a944573f35a4c60644f9d94e7aa20cf29", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34034482037", "meaning": "Only authorized I009 source candidate consumed 1/1 candidate and 0 confirmation. Artifact 9989713478/digest 51e5023b... independently verified 8/8; fresh near/far improves 0/6 to 6/6 but pure-far is only 2/3 with seed 18109 at 5.3521% false double-talk. Final decision KEEP_BASELINE_CANDIDATE_REJECTED; PR #119 closed unmerged."},
        {"source_sha": "7acd0a3a944573f35a4c60644f9d94e7aa20cf29", "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/34034482048", "meaning": "Independent Hosted Real AEC regression for the same frozen candidate: artifact 9989725745/digest ec24563f... independently verified 18/18; only 2/4 cases pass, static 2/2 but movement 0/2 with correlation-reduction regressions. Confirmation is not executed and shipping remains v2.3.12."}
      ]
    },
'''
pattern = re.compile(r'    \{\n      "id": "I009".*?    \},\n(?=    \{\n      "id": "I008")', re.S)
s, n = pattern.subn(new_block, s)
assert n == 1, n
plan.write_text(s)

program = Path('scripts/program.py')
p = program.read_text()
old = '''    i009 = by_id["I009"]
    require(i009["status"] == "PLANNED" and i009["handler"] is None and
            i009["contract"] == "docs/program/iterations/I009-inherited-double-talk-evidence.json" and
            not i009["evidence"],
            "I006 CLOSED must register I009 as non-executable inherited context")
'''
new = '''    i009 = by_id["I009"]
    require(i009["handler"] is None and (
                (i009["status"] == "PLANNED" and
                 i009["contract"] == "docs/program/iterations/I009-inherited-double-talk-evidence.json" and
                 not i009["evidence"]) or
                (i009["status"] == "CLOSED" and
                 i009["contract"] == "docs/program/iterations/I009-closure.json" and
                 bool(i009["evidence"]))),
            "I006 CLOSED permits only inherited-context PLANNED or evidence-backed CLOSED I009")
'''
assert p.count(old) == 1, p.count(old)
p = p.replace(old, new)

validator = '''
def validate_i009_closed(plan: dict, root: Path) -> None:
    by_id = {task["id"]: task for task in plan["tasks"]}
    i009 = by_id["I009"]
    if i009["status"] != "CLOSED":
        return
    require(i009["handler"] is None and
            i009["contract"] == "docs/program/iterations/I009-closure.json" and
            len(i009["evidence"]) == 5,
            "I009 CLOSED must be terminal and evidence-backed")
    c = json.loads(repo_file(root, "docs/program/iterations/I009-closure.json").read_text())
    require(c["schema_version"] == 1 and c["iteration_id"] == "I009" and
            c["state"] == "CLOSED_KEEP_BASELINE" and c["lane"] == "acoustic" and
            c["root_cause_id"] == "activity-double-talk-energy-domain-ambiguity" and
            c["closed_from_main_sha"] == "497c3ca3a6be0a4e319a3493e256eac7391a7f18",
            "I009 closure identity")
    require(c["shipping_baseline"] == {
                "release": "v2.3.12",
                "source_sha": plan["baseline"]["source_sha"],
                "unchanged": True,
            }, "I009 shipping baseline")
    e = c["evidence_chain"]
    require((e["fresh_baseline"]["run_id"], e["fresh_baseline"]["artifact_id"],
             e["fresh_baseline"]["internal_sha256s_verified"], e["fresh_baseline"]["gate_failure_partitions"]) ==
            (34031305098, 9988691434, 284, 5), "I009 fresh baseline evidence")
    require((e["rejected_echo_normalized_differential"]["run_id"],
             e["rejected_echo_normalized_differential"]["artifact_id"],
             e["rejected_echo_normalized_differential"]["internal_sha256s_verified"],
             e["rejected_echo_normalized_differential"]["near_far_passed"],
             e["rejected_echo_normalized_differential"]["pure_far_passed"]) ==
            (34031731756, 9988834254, 301, 6, 0), "I009 rejected echo-normalized evidence")
    require((e["supported_residual_echo_differential"]["run_id"],
             e["supported_residual_echo_differential"]["artifact_id"],
             e["supported_residual_echo_differential"]["internal_sha256s_verified"],
             e["supported_residual_echo_differential"]["near_far_passed"],
             e["supported_residual_echo_differential"]["pure_far_passed"]) ==
            (34033842566, 9989499865, 301, 6, 3), "I009 supported residual/echo evidence")
    candidate = e["bounded_source_candidate"]
    require(candidate["candidate_id"] == "activity-residual-echo-rescue-v1" and
            candidate["pr"] == 119 and candidate["pr_closed"] is True and candidate["pr_merged"] is False and
            candidate["head_sha"] == "7acd0a3a944573f35a4c60644f9d94e7aa20cf29" and
            candidate["run_id"] == 34034482037 and candidate["artifact_id"] == 9989713478 and
            candidate["internal_sha256s_verified"] == 8 and
            candidate["candidate_fresh_near_far_passed"] == 6 and
            candidate["candidate_fresh_pure_far_passed"] == 2 and
            candidate["decision"] == "KEEP_BASELINE_CANDIDATE_REJECTED" and
            candidate["candidate_limit"] == candidate["candidate_limit_consumed"] == 1 and
            candidate["confirmation_limit_consumed"] == 0 and
            candidate["reserved_confirmation_executed"] is False,
            "I009 rejected candidate evidence")
    hosted = e["hosted_real_aec_regression"]
    require(hosted["run_id"] == 34034482048 and hosted["artifact_id"] == 9989725745 and
            hosted["internal_sha256s_verified"] == 18 and hosted["cases"] == 4 and
            hosted["passed_cases"] == 2 and hosted["movement_passed"] == 0 and
            hosted["movement_cases"] == 2 and hosted["decision"] == "REGRESSION_FAIL",
            "I009 Hosted Real AEC rejection evidence")
    require(c["candidate_budget"] == {
                "limit": 1, "consumed": 1, "remaining": 0,
                "second_candidate_authorized": False,
                "post_result_candidate_change_authorized": False,
            }, "I009 candidate budget")
    require(c["confirmation"] == {
                "consumed": 0, "reserved_source_executed": False,
                "reserved_seeds": [19109, 29109, 39109],
                "may_rescue_rejected_candidate": False,
                "may_be_used_for_post_result_candidate_change": False,
            }, "I009 confirmation boundary")
    require(c["closure_decision"]["keep_baseline"] is True and
            c["closure_decision"]["merge_shipping_candidate"] is False and
            c["closure_decision"]["create_release"] is False and
            c["closure_decision"]["consume_confirmation"] is False and
            c["closure_decision"]["allow_second_candidate"] is False and
            c["closure_decision"]["allow_post_result_candidate_change"] is False,
            "I009 closure authority")
    require(c["authority_boundary"] == {
                "shipping_source_changed": False, "software_candidate_promoted": False,
                "release_created": False, "product_qualification": "DEFERRED_BY_SCOPE",
                "hardware_collection": False, "dut_hil": "DEFERRED_BY_SCOPE",
            }, "I009 product boundary")

'''
marker = '\ndef validate(plan: dict, root: Path | None = None) -> None:\n'
assert p.count(marker) == 1, p.count(marker)
p = p.replace(marker, '\n' + validator + 'def validate(plan: dict, root: Path | None = None) -> None:\n')
old_calls = '''        validate_i006_review_required(plan, root)
        validate_i006_closed(plan, root)
'''
new_calls = '''        validate_i006_review_required(plan, root)
        validate_i006_closed(plan, root)
        validate_i009_closed(plan, root)
'''
assert p.count(old_calls) == 1, p.count(old_calls)
p = p.replace(old_calls, new_calls)
program.write_text(p)
