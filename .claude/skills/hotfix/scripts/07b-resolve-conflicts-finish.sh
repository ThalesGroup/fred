#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH_NAME="resolve-version-conflict-after-hotfix-${NEXT_VERSION}"

echo "=== Finish conflict resolution and open MR ==="

# Complete the merge commit BEFORE any git checkout — git checkout on the current
# branch while all conflicts are staged silently drops MERGE_HEAD, losing the merge.
if [ -f "${REPO_ROOT}/.git/MERGE_HEAD" ]; then
  echo "--- Completing merge commit after conflict resolution ---"
  git -C "$REPO_ROOT" add -A
  git -C "$REPO_ROOT" commit --no-edit
fi

git -C "$REPO_ROOT" checkout "$BRANCH_NAME"

# Set the unified post-release version for develop-prism
echo "--- Setting version to ${NEXT_VERSION}-prism.1-post ---"
make -C "$REPO_ROOT" set-version VERSION="${NEXT_VERSION}-prism.1-post"
git -C "$REPO_ROOT" add -A
git -C "$REPO_ROOT" commit -m "chore: set version to ${NEXT_VERSION}-prism.1-post after conflict resolution"

git -C "$REPO_ROOT" push --set-upstream prism "$BRANCH_NAME"

# Create GitLab MR (targeting develop-prism, sourced from GitHub's develop-based branch)
echo "--- Creating GitLab MR: $BRANCH_NAME -> develop-prism ---"
glab mr create \
  --target-branch develop-prism \
  --source-branch "$BRANCH_NAME" \
  --remove-source-branch \
  --title "chore: resolve version conflict after hotfix ${NEXT_VERSION}" \
  --description ""

# Disable squash on the MR
MR_IID=$(glab api "projects/:id/merge_requests?source_branch=${BRANCH_NAME}&state=opened&per_page=1" | jq '.[0].iid')
glab api "projects/:id/merge_requests/${MR_IID}" -X PUT -f squash=false

echo ""
echo "=== Conflict resolution MR created ==="
echo "MR: ${BRANCH_NAME} -> develop-prism (squash disabled)"
