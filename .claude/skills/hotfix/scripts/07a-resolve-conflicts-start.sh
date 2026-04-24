#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH_NAME="resolve-version-conflict-after-hotfix-${NEXT_VERSION}"

echo "=== Resolve develop/develop-prism version conflict ==="
echo "--- Creating $BRANCH_NAME from develop-prism ---"

git -C "$REPO_ROOT" fetch origin develop
git -C "$REPO_ROOT" fetch prism develop-prism

git -C "$REPO_ROOT" checkout -B "$BRANCH_NAME" prism/develop-prism

# Merge develop — version conflicts are expected (develop has -post, develop-prism has -prism.1-post)
echo "--- Merging origin/develop into $BRANCH_NAME ---"
if git -C "$REPO_ROOT" merge origin/develop --no-edit; then
  echo "Merge succeeded with no conflicts."
else
  echo ""
  echo "=== Merge conflict(s) detected (expected) ==="
  echo "Only version conflicts are expected here."
  echo "Ignore them all — we will set the final version with make set-version after."
  echo ""
  echo "Run: git checkout --ours . && git checkout --theirs frontend/public/release.md"
  echo "(keep theirs for release.md — develop has the correct Unreleased + hotfix entry from Fred)"
  echo ""
  echo "Once resolved, run:"
  echo "  bash /tmp/fred-hotfix-scripts/07b-resolve-conflicts-finish.sh ${NEXT_VERSION}"
  exit 0
fi

echo ""
echo "No conflicts — you can proceed directly to 07b:"
echo "  bash /tmp/fred-hotfix-scripts/07b-resolve-conflicts-finish.sh ${NEXT_VERSION}"
