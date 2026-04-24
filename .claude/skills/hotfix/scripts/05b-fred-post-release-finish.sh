#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH_NAME="post-release/${NEXT_VERSION}"

echo "=== Fred: Finish post-release PR for $NEXT_VERSION ==="

# Complete the merge commit BEFORE any git checkout — git checkout on the current
# branch while all conflicts are staged silently drops MERGE_HEAD, losing the merge.
if [ -f "${REPO_ROOT}/.git/MERGE_HEAD" ]; then
  echo "--- Completing merge commit after conflict resolution ---"
  git -C "$REPO_ROOT" add -A
  git -C "$REPO_ROOT" commit --no-edit
fi

git -C "$REPO_ROOT" checkout "$BRANCH_NAME"

# Set post-release version
echo "--- Setting version to ${NEXT_VERSION}-post ---"
make -C "$REPO_ROOT" set-version VERSION="${NEXT_VERSION}-post"

# Ensure Unreleased section exists at top of release notes
RELEASE_MD="${REPO_ROOT}/frontend/public/release.md"
if ! grep -q "^\*\*Unreleased\*\*" "$RELEASE_MD"; then
  sed -i "1i **Unreleased** — XXXX-XX-XX\n" "$RELEASE_MD"
fi

git -C "$REPO_ROOT" add -A
git -C "$REPO_ROOT" commit -m "Chore: update release note and all versions to ${NEXT_VERSION}"

git -C "$REPO_ROOT" push --set-upstream origin "$BRANCH_NAME"

# Create GitHub PR
echo "--- Creating GitHub PR: $BRANCH_NAME -> develop ---"
gh pr create \
  --base develop \
  --head "$BRANCH_NAME" \
  --title "post-release: ${NEXT_VERSION}" \
  --body ""

echo ""
echo "=== Fred post-release PR created ==="
echo "PR: ${BRANCH_NAME} -> develop"
