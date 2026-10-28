#!/bin/sh
# Release may have downloaded evidence, but its tracked source must be exact.
set -eu

revision=${1:?expected source revision is required}
case "$revision" in
    *[!0-9a-f]*|'') echo "invalid release source revision" >&2; exit 1 ;;
esac
test "${#revision}" -eq 40 || {
    echo "release source revision must be a full commit SHA" >&2
    exit 1
}
test "$(git rev-parse --verify HEAD)" = "$revision" || {
    echo "release checkout does not match verified source revision" >&2
    exit 1
}
git diff --quiet HEAD -- || {
    echo "release tracked source has local changes" >&2
    exit 1
}
