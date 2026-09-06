#!/usr/bin/env python3
from pathlib import Path
import subprocess

BASE='699c1f604611b5018ab3cb7a712ed1a8942cedcb'
OUT=Path('.github/program/generated-p002')
OUT.mkdir(parents=True, exist_ok=True)

def base(path: str) -> str:
    return subprocess.check_output(['git','show',f'{BASE}:{path}'], text=True)

release=base('.github/workflows/release.yml')
old='''      - name: Check existing release
        id: existing
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ steps.version.outputs.tag }}
        run: |
          if gh release view "$TAG" >/dev/null 2>&1; then
            echo "release=true" >> "$GITHUB_OUTPUT"
          else
            echo "release=false" >> "$GITHUB_OUTPUT"
          fi
'''
new=old+'''      - name: Verify existing immutable release identity
        if: steps.existing.outputs.release == 'true'
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ steps.version.outputs.tag }}
          VERSION: ${{ steps.version.outputs.version }}
          VERIFIED_SHA: ${{ github.event.workflow_run.head_sha }}
        run: |
          set -euo pipefail
          python3 .github/program/existing_release_identity.py --self-test
          work=/tmp/existing-release-identity
          rm -rf "$work"
          mkdir -p "$work"
          gh api "repos/$GITHUB_REPOSITORY/releases/tags/$TAG" > "$work/release.json"
          ref_json=$(gh api "repos/$GITHUB_REPOSITORY/git/ref/tags/$TAG")
          object_type=$(jq -r '.object.type' <<<"$ref_json")
          object_sha=$(jq -r '.object.sha' <<<"$ref_json")
          while [ "$object_type" = tag ]; do
            tag_json=$(gh api "repos/$GITHUB_REPOSITORY/git/tags/$object_sha")
            object_type=$(jq -r '.object.type' <<<"$tag_json")
            object_sha=$(jq -r '.object.sha' <<<"$tag_json")
          done
          test "$object_type" = commit
          git merge-base --is-ancestor "$object_sha" "$VERIFIED_SHA"
          gh release download "$TAG" \
            --pattern "audio-pipeline-${TAG}-release-manifest.json" \
            --pattern SHA256SUMS \
            --dir "$work"
          python3 .github/program/existing_release_identity.py \
            --release-json "$work/release.json" \
            --manifest "$work/audio-pipeline-${TAG}-release-manifest.json" \
            --sha256s "$work/SHA256SUMS" \
            --tag "$TAG" --version "$VERSION" \
            --tag-peel-sha "$object_sha" --verified-sha "$VERIFIED_SHA" \
            --release-source-is-ancestor \
            --output "$work/result.json"
          cat "$work/result.json" >> "$GITHUB_STEP_SUMMARY"
'''
assert release.count(old)==1, release.count(old)
release=release.replace(old,new)
assert release.count('Verify existing immutable release identity')==1
OUT.joinpath('release.yml').write_text(release)

for iteration in ('I007','I009'):
    lower=iteration.lower()
    text=base(f'.github/workflows/{lower}-closure.yml')
    old_trigger=f'''on:\n  pull_request:\n    paths:\n      - 'docs/program/plan.json'\n      - 'docs/program/iterations/{iteration}-closure.json'\n      - 'scripts/program.py'\n      - '.github/workflows/{lower}-closure.yml'\n'''
    new_trigger=f'''on:\n  pull_request:\n    paths:\n      - 'docs/program/iterations/{iteration}-closure.json'\n'''
    assert text.count(old_trigger)==1, (iteration,text.count(old_trigger))
    text=text.replace(old_trigger,new_trigger)
    assert "docs/program/plan.json'" not in text.split('permissions:',1)[0]
    assert "scripts/program.py'" not in text.split('permissions:',1)[0]
    OUT.joinpath(f'{lower}-closure.yml').write_text(text)

print('P002 generated workflows: PASS')
