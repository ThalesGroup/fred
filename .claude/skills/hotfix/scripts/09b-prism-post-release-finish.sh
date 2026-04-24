#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH_NAME="post-release/${NEXT_VERSION}-prism.1"

echo "=== Prism: Finish post-release MR for $NEXT_VERSION ==="

# Complete the merge commit BEFORE any git checkout — git checkout on the current
# branch while all conflicts are staged silently drops MERGE_HEAD, losing the merge.
if [ -f "${REPO_ROOT}/.git/MERGE_HEAD" ]; then
  echo "--- Completing merge commit after conflict resolution ---"
  git -C "$REPO_ROOT" add -A
  # Use --allow-empty in case all conflicts resolved to identical content
  git -C "$REPO_ROOT" commit --no-edit --allow-empty
fi

git -C "$REPO_ROOT" checkout "$BRANCH_NAME"

git -C "$REPO_ROOT" push --set-upstream prism "$BRANCH_NAME"

# Create GitLab MR
echo "--- Creating GitLab MR: $BRANCH_NAME -> develop-prism ---"
glab mr create \
  --target-branch develop-prism \
  --source-branch "$BRANCH_NAME" \
  --remove-source-branch \
  --title "post-release: ${NEXT_VERSION}-prism.1" \
  --description ""

# Disable squash on the MR
MR_IID=$(glab api "projects/:id/merge_requests?source_branch=${BRANCH_NAME}&state=opened&per_page=1" | jq '.[0].iid')
glab api "projects/:id/merge_requests/${MR_IID}" -X PUT -f squash=false

echo ""
echo "=== Prism post-release MR created ==="
echo "MR: ${BRANCH_NAME} -> develop-prism (squash disabled)"
