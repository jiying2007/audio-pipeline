#!/bin/sh
# Research builds must bind an exact tracked source; no GitHub Release or product authority.
set -eu

revision=${1:?expected source revision is required}
case "$revision" in
    *[!0-9a-f]*|'') echo "invalid research source revision" >&2; exit 1 ;;
esac
test "${#revision}" -eq 40 || {
    echo "research source revision must be a full commit SHA" >&2
    exit 1
}
test "$(git rev-parse --verify HEAD)" = "$revision" || {
    echo "research checkout does not match verified source revision" >&2
    exit 1
}
if ! git diff --quiet -- || ! git diff --cached --quiet HEAD --; then
    echo "research tracked source has local changes" >&2
    exit 1
fi
