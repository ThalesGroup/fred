#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH_NAME="post-release/${NEXT_VERSION}-prism.1"

echo "=== Prism: Start post-release branch and merge develop-prism ==="

git -C "$REPO_ROOT" fetch prism main-prism develop-prism

# Create post-release branch from main-prism
echo "--- Creating $BRANCH_NAME from main-prism ---"
git -C "$REPO_ROOT" checkout main-prism
git -C "$REPO_ROOT" pull prism main-prism
git -C "$REPO_ROOT" checkout -B "$BRANCH_NAME"

# Merge develop-prism (which now has the -prism.1-post version set)
# Conflict expected: version strings differ between main-prism and develop-prism
echo "--- Merging develop-prism into $BRANCH_NAME ---"
if git -C "$REPO_ROOT" merge prism/develop-prism --no-edit; then
  echo "Merge succeeded with no conflicts."
else
  echo ""
  echo "=== Merge conflict(s) detected (expected) ==="
  echo "Keep the -prism.1-post version from develop-prism (theirs)."
  echo ""
  echo "Quick resolution: git checkout --theirs . && git add -A"
  echo ""
  echo "Once resolved, run:"
  echo "  bash /tmp/fred-hotfix-scripts/09b-prism-post-release-finish.sh ${NEXT_VERSION}"
  exit 0
fi

echo ""
echo "No conflicts — you can proceed directly to 09b:"
echo "  bash /tmp/fred-hotfix-scripts/09b-prism-post-release-finish.sh ${NEXT_VERSION}"
