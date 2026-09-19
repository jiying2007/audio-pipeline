#!/usr/bin/env python3
"""Repository-wide execution contract for schema-v2 source candidates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".github/research/continuous-optimization"))

import source_candidate_authority_v2 as authority_v2

CANDIDATE_DIR = Path(".github/research/continuous-optimization/source-candidates")
WORKFLOW_DIR = Path(".github/workflows")
PREFLIGHT = WORKFLOW_DIR / "research-source-candidate-v2-preflight.yml"
POLICY = Path(".github/research/continuous-optimization/source-candidate-authority-v2.json")
V2_WORKFLOW_GLOB = "research-source-candidate-v2-*.yml"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def on_block(text: str) -> str:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line == "on:"), None)
    if start is None:
        raise ValueError("workflow has no top-level on block")
    block: list[str] = []
    for line in lines[start + 1:]:
        if line and not line.startswith((" ", "\t")):
            break
        block.append(line)
    return "\n".join(block)


def job_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line == "jobs:"), None)
    if start is None:
        raise ValueError("workflow has no top-level jobs block")
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[start + 1:]:
        if line and not line.startswith((" ", "\t")):
            break
        match = re.fullmatch(r"  ([A-Za-z0-9_-]+):\s*", line)
        if match:
            current = match.group(1)
            if current in blocks:
                raise ValueError(f"duplicate workflow job id: {current}")
            blocks[current] = [line]
        elif current is not None:
            blocks[current].append(line)
    return {name: "\n".join(lines_) for name, lines_ in blocks.items()}


def validate_preflight(root: Path) -> None:
    path = root / PREFLIGHT
    if not path.is_file():
        raise ValueError(f"missing reusable v2 authority preflight: {PREFLIGHT}")
    text = path.read_text(encoding="utf-8")
    triggers = on_block(text)
    if not re.search(r"(?m)^  workflow_call:\s*$", triggers):
        raise ValueError("v2 preflight must be workflow_call-only")
    for forbidden in ("workflow_dispatch", "pull_request", "push", "schedule"):
        if re.search(rf"(?m)^  {re.escape(forbidden)}:", triggers):
            raise ValueError(f"v2 preflight cannot expose trigger: {forbidden}")
    for required in (
        "--describe-contract",
        "--validate-lock",
        "candidate_execution_allowed",
        "refs/heads/main",
        "selected_authority_json",
    ):
        if required not in text:
            raise ValueError(f"v2 preflight missing required lock boundary: {required}")


def _needs_authority(block: str) -> bool:
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("needs:"):
            continue
        value = stripped.split(":", 1)[1].strip()
        if value == "authority":
            return True
        if value.startswith("[") and value.endswith("]"):
            names = [item.strip() for item in value[1:-1].split(",")]
            if "authority" in names:
                return True
    return False


def validate_execution_workflow(
    root: Path,
    workflow_path: Path,
    candidate_contract_path: Path,
) -> None:
    path = root / workflow_path
    if not path.is_file():
        raise ValueError(f"bound v2 execution workflow missing: {workflow_path}")
    text = path.read_text(encoding="utf-8")
    triggers = on_block(text)
    for required in ("pull_request", "workflow_dispatch"):
        if not re.search(rf"(?m)^  {required}:", triggers):
            raise ValueError(f"{workflow_path} must retain trigger: {required}")
    for forbidden in ("push", "schedule", "workflow_call"):
        if re.search(rf"(?m)^  {forbidden}:", triggers):
            raise ValueError(f"{workflow_path} cannot expose trigger: {forbidden}")

    jobs = job_blocks(text)
    if set(jobs) != {"contract", "authority", "candidate"}:
        raise ValueError(
            f"{workflow_path} v2 jobs must be exactly contract/authority/candidate: "
            f"{sorted(jobs)}"
        )

    authority_block = jobs["authority"]
    if "if: github.event_name == 'workflow_dispatch'" not in authority_block:
        raise ValueError(f"{workflow_path} authority job must be dispatch-only")
    if "uses: ./.github/workflows/research-source-candidate-v2-preflight.yml" not in authority_block:
        raise ValueError(f"{workflow_path} authority job must use reusable v2 preflight")
    required_contract_binding = f"candidate_contract: {candidate_contract_path.as_posix()}"
    if required_contract_binding not in authority_block:
        raise ValueError(
            f"{workflow_path} authority job must bind exact candidate contract: "
            f"{candidate_contract_path}"
        )

    candidate_block = jobs["candidate"]
    if not _needs_authority(candidate_block):
        raise ValueError(f"{workflow_path} candidate job must need authority")
    if "github.event_name == 'workflow_dispatch'" not in candidate_block:
        raise ValueError(f"{workflow_path} candidate job must be dispatch-only")
    if "needs.authority.outputs.candidate_execution_allowed == 'true'" not in candidate_block:
        raise ValueError(
            f"{workflow_path} candidate job must gate on validated authority output"
        )

    contract_block = jobs["contract"]
    if "candidate_execution_allowed" in contract_block:
        raise ValueError(
            f"{workflow_path} contract job cannot synthesize candidate execution authority"
        )


def validate_repository(root: Path = ROOT) -> dict[str, Any]:
    policy_path = root / POLICY
    policy = load_json(policy_path)
    authority_v2.validate_policy(policy)
    validate_preflight(root)

    expected_workflows: dict[Path, Path] = {}
    candidate_root = root / CANDIDATE_DIR
    for contract_path in sorted(candidate_root.glob("*.json")):
        contract = load_json(contract_path)
        if contract.get("schema_version") != 2:
            continue
        binding = authority_v2.validate_candidate_contract(
            contract, policy, contract_path
        )
        workflow_path = Path(binding["execution_workflow"])
        if workflow_path == PREFLIGHT:
            raise ValueError("candidate execution workflow cannot be the reusable preflight")
        if workflow_path in expected_workflows:
            raise ValueError(
                f"v2 execution workflow reused by multiple contracts: {workflow_path}"
            )
        expected_workflows[workflow_path] = contract_path.relative_to(root)
        validate_execution_workflow(
            root, workflow_path, contract_path.relative_to(root)
        )

    actual_workflows = {
        path.relative_to(root)
        for path in (root / WORKFLOW_DIR).glob(V2_WORKFLOW_GLOB)
        if path.relative_to(root) != PREFLIGHT
    }
    expected_paths = set(expected_workflows)
    rogue = sorted(str(path) for path in actual_workflows - expected_paths)
    missing = sorted(str(path) for path in expected_paths - actual_workflows)
    if rogue:
        raise ValueError(f"unregistered v2 source-candidate workflow(s): {rogue}")
    if missing:
        raise ValueError(f"registered v2 source-candidate workflow(s) missing: {missing}")

    return {
        "result": "PASS",
        "schema_v2_candidates": len(expected_workflows),
        "execution_workflows": sorted(str(path) for path in expected_paths),
        "reusable_preflight": str(PREFLIGHT),
    }


def _fixture_workflow(contract_path: Path) -> str:
    return f"""name: fixture

on:
  pull_request:
  workflow_dispatch:

jobs:
  contract:
    runs-on: ubuntu-latest
    steps:
      - run: echo contract

  authority:
    if: github.event_name == 'workflow_dispatch'
    uses: ./.github/workflows/research-source-candidate-v2-preflight.yml
    with:
      candidate_contract: {contract_path.as_posix()}

  candidate:
    needs: [contract, authority]
    if: github.event_name == 'workflow_dispatch' && needs.authority.outputs.candidate_execution_allowed == 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo candidate
"""


def self_test() -> None:
    import tempfile

    policy = load_json(POLICY)
    authority_v2.validate_policy(policy)

    with tempfile.TemporaryDirectory(prefix="ap-v2-execution-contract-") as tmp:
        root = Path(tmp)
        (root / CANDIDATE_DIR).mkdir(parents=True)
        (root / WORKFLOW_DIR).mkdir(parents=True)

        (root / POLICY).parent.mkdir(parents=True, exist_ok=True)
        (root / POLICY).write_text(
            json.dumps(policy, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        preflight = root / PREFLIGHT
        preflight.write_text(
            """name: preflight

on:
  workflow_call:

jobs:
  authority:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo refs/heads/main
          echo --describe-contract
          echo --validate-lock
          echo candidate_execution_allowed
          echo selected_authority_json
""",
            encoding="utf-8",
        )

        contract = authority_v2._future_contract(
            policy, "vad-stage", "ap_process_pcm", {}
        )
        contract_path = CANDIDATE_DIR / f"{contract['candidate_id']}.json"
        (root / contract_path).write_text(
            json.dumps(contract, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        workflow_path = Path(contract["execution_workflow"])
        (root / workflow_path).write_text(
            _fixture_workflow(contract_path),
            encoding="utf-8",
        )

        result = validate_repository(root)
        assert result["schema_v2_candidates"] == 1

        bad = (root / workflow_path).read_text(encoding="utf-8").replace(
            "needs: [contract, authority]", "needs: contract"
        )
        (root / workflow_path).write_text(bad, encoding="utf-8")
        try:
            validate_repository(root)
        except ValueError as exc:
            assert "must need authority" in str(exc)
        else:
            raise AssertionError("v2 candidate bypassed authority dependency")

        (root / workflow_path).write_text(
            _fixture_workflow(contract_path),
            encoding="utf-8",
        )
        rogue = root / WORKFLOW_DIR / "research-source-candidate-v2-rogue.yml"
        rogue.write_text(_fixture_workflow(contract_path), encoding="utf-8")
        try:
            validate_repository(root)
        except ValueError as exc:
            assert "unregistered v2 source-candidate workflow" in str(exc)
        else:
            raise AssertionError("unregistered v2 execution workflow was accepted")

    print("source-candidate v2 execution contract self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.self_test and not args.check:
        parser.error("choose --self-test and/or --check")
    if args.self_test:
        self_test()
    if args.check:
        print(json.dumps(validate_repository(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
