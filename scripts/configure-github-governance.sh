#!/bin/sh
set -eu

REPO=${1:-jiying2007/audio-pipeline}
API_VERSION=${GITHUB_API_VERSION:-2026-03-10}

if ! command -v gh >/dev/null 2>&1; then
    echo "gh CLI is required" >&2
    exit 2
fi
if ! gh auth status >/dev/null 2>&1; then
    echo "authenticate gh with repository Administration:write permission" >&2
    exit 2
fi

upsert_ruleset() {
    name=$1
    file=$2
    id=$(gh api -H "X-GitHub-Api-Version: $API_VERSION" \
        "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$name\") | .id" | head -n1)
    if [ -n "$id" ]; then
        gh api --method PUT -H "X-GitHub-Api-Version: $API_VERSION" \
            "repos/$REPO/rulesets/$id" --input "$file" >/dev/null
        echo "updated ruleset: $name ($id)"
    else
        gh api --method POST -H "X-GitHub-Api-Version: $API_VERSION" \
            "repos/$REPO/rulesets" --input "$file" >/dev/null
        echo "created ruleset: $name"
    fi
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM
cat > "$TMP/main.json" <<'JSON'
{
  "name": "main-release-gate",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "required_linear_history"},
    {"type": "pull_request", "parameters": {
      "allowed_merge_methods": ["squash", "rebase"],
      "dismiss_stale_reviews_on_push": false,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_approving_review_count": 0,
      "required_review_thread_resolution": true
    }},
    {"type": "required_status_checks", "parameters": {
      "do_not_enforce_on_create": false,
      "required_status_checks": [{"context": "summary"}],
      "strict_required_status_checks_policy": true
    }}
  ]
}
JSON
cat > "$TMP/tags.json" <<'JSON'
{
  "name": "immutable-release-tags",
  "target": "tag",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"}
  ]
}
JSON

upsert_ruleset main-release-gate "$TMP/main.json"
upsert_ruleset immutable-release-tags "$TMP/tags.json"

gh api --method PUT -H "X-GitHub-Api-Version: $API_VERSION" \
    "repos/$REPO/immutable-releases" >/dev/null

gh api -H "X-GitHub-Api-Version: $API_VERSION" "repos/$REPO/immutable-releases"
echo "repository governance configured: PR+summary gate, no force/delete, protected v* tags, immutable releases"
