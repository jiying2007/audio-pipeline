#!/usr/bin/env python3
from pathlib import Path
import json
import subprocess

BASE='699c1f604611b5018ab3cb7a712ed1a8942cedcb'
text=subprocess.check_output(['git','show',f'{BASE}:scripts/research_registry.py'], text=True)
path=Path('scripts/research_registry.py')
anchor='''    records = data.get("records")\n    if not isinstance(records, list):\n        raise ValueError("research registry records must be a list")\n'''
insert='''    records = data.get("records")\n    if not isinstance(records, list):\n        raise ValueError("research registry records must be a list")\n    active_dependencies = data.get("active_dependencies", [])\n    if not isinstance(active_dependencies, list):\n        raise ValueError("active_dependencies must be a list")\n    seen_dependencies: set[tuple[str | None, str | None]] = set()\n    for index, dependency in enumerate(active_dependencies):\n        if not isinstance(dependency, dict) or set(dependency) != {"branch", "head_sha", "reason"}:\n            raise ValueError(f"active dependency {index} must have branch/head_sha/reason")\n        branch = dependency["branch"]\n        head_sha = dependency["head_sha"]\n        reason = dependency["reason"]\n        if branch is not None and (not isinstance(branch, str) or not branch.startswith(GC_PREFIXES)):\n            raise ValueError(f"invalid active dependency branch at {index}")\n        if head_sha is not None and not SHA_RE.fullmatch(str(head_sha)):\n            raise ValueError(f"invalid active dependency head_sha at {index}")\n        if branch is None and head_sha is None:\n            raise ValueError(f"active dependency {index} must bind branch or head_sha")\n        if not isinstance(reason, str) or not reason:\n            raise ValueError(f"active dependency {index} requires reason")\n        key = (branch, head_sha)\n        if key in seen_dependencies:\n            raise ValueError(f"duplicate active dependency at {index}")\n        seen_dependencies.add(key)\n'''
assert text.count(anchor)==1
text=text.replace(anchor,insert)
anchor2='''def delete_branch(repository: str, branch: str) -> None:\n'''
helper='''def active_dependency_reasons(data: dict, branch: str, head_sha: str) -> list[str]:\n    reasons = []\n    for dependency in data.get("active_dependencies", []):\n        if dependency["branch"] == branch or dependency["head_sha"] == head_sha:\n            reasons.append(dependency["reason"])\n    return reasons\n\n\n'''
assert text.count(anchor2)==1
text=text.replace(anchor2,helper+anchor2)
old='''        elif current != expected:\n            item["action"] = "BLOCK_SHA_DRIFT"\n        else:\n            prs = open_prs(repository, branch)\n            if prs:\n                item["action"] = "BLOCK_OPEN_PR"\n                item["open_prs"] = [int(pr["number"]) for pr in prs]\n            else:\n                item["action"] = "DELETE_DRY_RUN"\n                deletable.append((item, branch))\n'''
new='''        elif current != expected:\n            item["action"] = "BLOCK_SHA_DRIFT"\n        else:\n            dependencies = active_dependency_reasons(data, branch, expected)\n            if dependencies:\n                item["action"] = "BLOCK_ACTIVE_DEPENDENCY"\n                item["active_dependencies"] = dependencies\n            else:\n                prs = open_prs(repository, branch)\n                if prs:\n                    item["action"] = "BLOCK_OPEN_PR"\n                    item["open_prs"] = [int(pr["number"]) for pr in prs]\n                else:\n                    item["action"] = "DELETE_DRY_RUN"\n                    deletable.append((item, branch))\n'''
assert text.count(old)==1
text=text.replace(old,new)
oldgood='''        "schema_version": 1,\n        "records": [\n'''
newgood='''        "schema_version": 1,\n        "active_dependencies": [],\n        "records": [\n'''
assert text.count(oldgood)==1
text=text.replace(oldgood,newgood)
needle='''    validate_registry(good)\n'''
extra='''    validate_registry(good)\n    active = json.loads(json.dumps(good))\n    active["active_dependencies"] = [{\n        "branch": "research/example-v1", "head_sha": None, "reason": "program:P002-fixture"\n    }]\n    validate_registry(active)\n    assert active_dependency_reasons(active, "research/example-v1", "a" * 40) == ["program:P002-fixture"]\n'''
assert text.count(needle)==1
text=text.replace(needle,extra)
path.write_text(text)

base=subprocess.check_output(['git','show',f'{BASE}:.github/research/evidence-index.json'], text=True)
old_registry='''    "gc_requires": ["terminal status", "exact head_sha", "sealed evidence", "no open PR", "live ref SHA match"],\n    "unclassified_refs_are_retained": true\n  },\n  "records": [\n'''
new_registry='''    "gc_requires": ["terminal status", "exact head_sha", "sealed evidence", "no open PR", "live ref SHA match", "no active dependency"],\n    "unclassified_refs_are_retained": true\n  },\n  "active_dependencies": [],\n  "records": [\n'''
assert base.count(old_registry)==1
Path('.github/research/evidence-index.json').write_text(base.replace(old_registry,new_registry))
