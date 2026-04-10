#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"
BRANCH_NAME="resolve-version-conflict-after-${NEXT_VERSION}"

echo "=== Resolve Version Conflicts after v${NEXT_VERSION} ==="

# Checkout develop
git checkout develop
git pull origin develop

# Create resolution branch
echo "--- Creating resolution branch ---"
git checkout -B "$BRANCH_NAME"

# Fetch and merge develop-prism
echo "--- Merging prism/develop-prism ---"
git fetch prism develop-prism
if ! git merge prism/develop-prism --no-edit; then
  echo "  Merge conflicts detected, resolving..."
  # Keep versions from develop-prism
  git checkout --theirs .
  # But keep release.md from develop (with Unreleased section)
  git checkout --ours frontend/public/release.md
  git add -A
  git commit --no-edit
fi

# Commit and push
git commit -am "chore: resolve develop version conflict after ${NEXT_VERSION}" || echo "  Nothing to commit (merge was clean)."
git push --set-upstream prism "$BRANCH_NAME"

# Create MR
echo "--- Creating GitLab MR ---"
glab mr create \
  --target-branch develop-prism \
  --source-branch "$BRANCH_NAME" \
  --remove-source-branch \
  --title "Merge develop into develop-prism with version conflict resolved after ${NEXT_VERSION}" \
  --description ""

# Disable squash on the MR
echo "--- Disabling squash on MR ---"
MR_IID=$(glab api "projects/:id/merge_requests?source_branch=$(git branch --show-current)&state=opened&per_page=1" | jq '.[0].iid')
glab api "projects/:id/merge_requests/${MR_IID}" -X PUT -f squash=false > /dev/null
echo "  Squash disabled."

echo ""
echo "=== Conflict resolution MR created ==="
echo "Assign a reviewer on GitLab for validation."
