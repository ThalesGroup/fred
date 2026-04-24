#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH_NAME="post-release/${NEXT_VERSION}"

echo "=== Fred: Merge post-release PR ==="

git -C "$REPO_ROOT" checkout develop
git -C "$REPO_ROOT" pull origin develop

echo "--- Merging Fred post-release PR: $BRANCH_NAME ---"
gh pr merge "$BRANCH_NAME" --merge --delete-branch -t "post-release: ${NEXT_VERSION}"

git -C "$REPO_ROOT" pull origin develop

echo ""
echo "=== Fred post-release merged into develop ==="
echo ""
echo "Next: bash /tmp/fred-hotfix-scripts/07a-resolve-conflicts-start.sh ${NEXT_VERSION}"
