#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH_NAME="post-release/${NEXT_VERSION}"

echo "=== Fred: Start post-release branch and merge develop ==="

git -C "$REPO_ROOT" fetch origin main develop

# Create post-release branch from main (which has the hotfix)
echo "--- Creating $BRANCH_NAME from main ---"
git -C "$REPO_ROOT" checkout main
git -C "$REPO_ROOT" pull origin main
git -C "$REPO_ROOT" checkout -B "$BRANCH_NAME"

# Attempt to merge develop — conflict on release.md is expected
echo "--- Merging develop into $BRANCH_NAME ---"
if git -C "$REPO_ROOT" merge origin/develop --no-edit; then
  echo "Merge succeeded with no conflicts."
else
  echo ""
  echo "=== Merge conflict(s) detected (expected) ==="
  echo "Please resolve conflicts in frontend/public/release.md:"
  echo "  - Keep the 'Unreleased' section from develop at the top"
  echo "  - Insert the hotfix v${NEXT_VERSION} entry below it"
  echo ""
  echo "Once resolved, run:"
  echo "  bash /tmp/fred-hotfix-scripts/05b-fred-post-release-finish.sh ${NEXT_VERSION}"
  exit 0
fi

echo ""
echo "No conflicts — you can proceed directly to 05b:"
echo "  bash /tmp/fred-hotfix-scripts/05b-fred-post-release-finish.sh ${NEXT_VERSION}"
