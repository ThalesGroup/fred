#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
FRED_BRANCH="hotfix/${NEXT_VERSION}"

echo "=== Fred: Merge hotfix PR and tag $NEXT_VERSION ==="

git -C "$REPO_ROOT" checkout main
git -C "$REPO_ROOT" pull origin main

# Merge the approved PR on GitHub
echo "--- Merging Fred hotfix PR: $FRED_BRANCH ---"
gh pr merge "$FRED_BRANCH" --merge --delete-branch -t "hotfix: ${NEXT_VERSION}"

# Pull merged main
git -C "$REPO_ROOT" pull origin main

# Create tags
echo "--- Creating tags code/v${NEXT_VERSION} and chart/v${NEXT_VERSION} ---"
git -C "$REPO_ROOT" tag "code/v${NEXT_VERSION}"
git -C "$REPO_ROOT" tag "chart/v${NEXT_VERSION}"
git -C "$REPO_ROOT" push origin "code/v${NEXT_VERSION}" "chart/v${NEXT_VERSION}"

echo ""
echo "=== Fred hotfix merged and tagged ==="
echo "Tags pushed: code/v${NEXT_VERSION}, chart/v${NEXT_VERSION}"
echo ""
echo "Next: bash /tmp/fred-hotfix-scripts/03-prism-hotfix-mr.sh $NEXT_VERSION"
