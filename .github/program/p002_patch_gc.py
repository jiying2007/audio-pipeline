#!/usr/bin/env python3
from pathlib import Path
import json

path=Path('scripts/research_registry.py')
text=path.read_text()
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

idx=Path('.github/research/evidence-index.json')
data=json.loads(idx.read_text())
data['policy']['gc_requires']=[
    'terminal status','exact head_sha','sealed evidence','no open PR','live ref SHA match','no active dependency'
]
data['active_dependencies']=[]
# Keep stable top-level presentation: schema, updated_at, policy, active_dependencies, records.
ordered={k:data[k] for k in ('schema_version','updated_at','policy','active_dependencies','records')}
idx.write_text(json.dumps(ordered, separators=(',',':'))+'\n')
