#!/usr/bin/env python3
"""Exercise I020 source-patch blind one-shot authority without consuming data."""

from contextlib import redirect_stdout
import io, json, os, re, subprocess, textwrap, unittest
from pathlib import Path
from unittest.mock import patch

WORKFLOW=Path(__file__).resolve().parent/"data/i020-consumed-blind-workflow.yml"
HISTORY_BLOB="0b64f84986298943ef930977541e9f3614c25cea"
CONSUME="Partition run-ephemeral blind holdout"
BLIND="Run candidate on blind holdout with summary-only report"
CURRENT={"id":20,"run_attempt":1}
PRIOR={"id":10,"run_attempt":1}

def guard_source():
    data=WORKFLOW.read_bytes()
    actual=__import__("hashlib").sha1(
        b"blob "+str(len(data)).encode()+b"\\0"+data).hexdigest()
    if actual!=HISTORY_BLOB:
        raise ValueError("historical I020 blind workflow fixture drift")
    text=data.decode()
    block=text.split("      - name: Enforce one-shot I020 blind execution\n",1)[1]
    block=block.split("      - name: Resolve frozen candidate and development artifact\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0])

def step(name=CONSUME,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}

class GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None: runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None: jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo","GITHUB_RUN_ID":"20",
            "GITHUB_RUN_ATTEMPT":attempt,"GITHUB_REF":"refs/heads/main",
        }
        def api(args,**kwargs):
            if api_error: raise subprocess.CalledProcessError(1,args)
            endpoint=args[-1]
            if "/workflows/" in endpoint: pages=runs
            else:
                match=re.search(r"/runs/(\d+)/attempts/(\d+)/jobs\?",endpoint)
                self.assertIsNotNone(match,endpoint)
                pages=jobs.get((int(match.group(1)),int(match.group(2))),[{"jobs":[]}])
            return json.dumps(pages if "--slurp" in args else pages[0])
        with (
            patch.dict(os.environ,env,clear=True),
            patch("subprocess.check_output",side_effect=api),
            redirect_stdout(io.StringIO()),
        ):
            exec(compile(guard_source(),str(WORKFLOW),"exec"),{})

    def history(self,steps,attempts=1):
        return {
            "runs":[{"workflow_runs":[CURRENT,dict(PRIOR,run_attempt=attempts)]}],
            "jobs":{(10,1):[{"jobs":[{"steps":steps}]}]},
        }

    def test_first_dispatch_allowed(self): self.execute()

    def test_rerun_blocked(self):
        with self.assertRaises(SystemExit): self.execute(attempt="2")

    def test_partition_start_consumes(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step(CONSUME)]))

    def test_failed_or_cancelled_partition_consumes(self):
        for conclusion in ("failure","cancelled"):
            with self.subTest(conclusion=conclusion),self.assertRaises(SystemExit):
                self.execute(**self.history([step(CONSUME,conclusion)]))

    def test_blind_step_without_visible_partition_history_still_consumes(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step(BLIND)]))

    def test_pre_partition_failure_allows_new_dispatch(self):
        self.execute(**self.history([
            step("Build exact baseline and patched candidate processors","failure"),
            step(CONSUME,"skipped"),step(BLIND,"skipped")]))

    def test_skipped_partition_does_not_consume(self):
        self.execute(**self.history([step(CONSUME,"skipped"),step(BLIND,"skipped")]))

    def test_later_run_page_cannot_hide_consumption(self):
        data=self.history([step(CONSUME)])
        data["runs"]=[{"workflow_runs":[CURRENT]},{"workflow_runs":[PRIOR]}]
        with self.assertRaises(SystemExit): self.execute(**data)

    def test_later_job_page_cannot_hide_consumption(self):
        data=self.history([step(BLIND)])
        data["jobs"]={(10,1):[{"jobs":[]},{"jobs":[{"steps":[step(BLIND)]}]}]}
        with self.assertRaises(SystemExit): self.execute(**data)

    def test_missing_current_run_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(runs=[{"workflow_runs":[]}])

    def test_invalid_attempt_count_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([],attempts=0))

    def test_api_failure_fails_closed(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(api_error=True)

    def test_guard_precedes_partition(self):
        text=WORKFLOW.read_text()
        guard=text.index("      - name: Enforce one-shot I020 blind execution\n")
        self.assertLess(guard,text.index(f"      - name: {CONSUME}\n"))
        self.assertLess(guard,text.index(f"      - name: {BLIND}\n"))
        self.assertIn("if: github.event_name == 'workflow_dispatch'",text)

    def test_contract_is_event_neutral_but_qualification_is_manual_only(self):
        text=WORKFLOW.read_text()
        self.assertNotIn('test "$GITHUB_EVENT_NAME" = pull_request', text)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", text)
        self.assertIn("      - name: Enforce manual-only qualification surface\n", text)

if __name__=="__main__":
    unittest.main()
