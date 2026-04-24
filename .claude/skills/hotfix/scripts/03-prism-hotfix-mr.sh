#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
PRISM_BRANCH="hotfix/${NEXT_VERSION}-prism.1"

echo "=== Prism: Create hotfix branch and MR for $NEXT_VERSION ==="

# Pull latest main-prism
echo "--- Pulling latest main-prism ---"
git -C "$REPO_ROOT" checkout main-prism
git -C "$REPO_ROOT" pull prism main-prism

# Create Prism hotfix branch from main-prism
echo "--- Creating $PRISM_BRANCH from main-prism ---"
git -C "$REPO_ROOT" checkout -B "$PRISM_BRANCH"

# Merge main (which now contains the hotfix) into the Prism hotfix branch
echo "--- Merging main into $PRISM_BRANCH to bring in the hotfix ---"
git -C "$REPO_ROOT" fetch origin main
if ! git -C "$REPO_ROOT" merge origin/main --no-edit; then
  echo "--- Merge conflict detected. Resolving by taking 'theirs' (main) ---"
  git -C "$REPO_ROOT" checkout --theirs .
  git -C "$REPO_ROOT" add -A
  git -C "$REPO_ROOT" commit --no-edit
fi

# Set Prism version
echo "--- Setting version to ${NEXT_VERSION}-prism.1 ---"
make -C "$REPO_ROOT" set-version VERSION="${NEXT_VERSION}-prism.1"
git -C "$REPO_ROOT" add -A
git -C "$REPO_ROOT" commit -m "chore: set version to ${NEXT_VERSION}-prism.1"

git -C "$REPO_ROOT" push --set-upstream prism "$PRISM_BRANCH"

# Create GitLab MR
echo "--- Creating GitLab MR: $PRISM_BRANCH -> main-prism ---"
glab mr create \
  --target-branch main-prism \
  --source-branch "$PRISM_BRANCH" \
  --remove-source-branch \
  --title "hotfix: ${NEXT_VERSION}-prism.1" \
  --description ""

# Disable squash on the MR
MR_IID=$(glab api "projects/:id/merge_requests?source_branch=${PRISM_BRANCH}&state=opened&per_page=1" | jq '.[0].iid')
glab api "projects/:id/merge_requests/${MR_IID}" -X PUT -f squash=false

echo ""
echo "=== Prism hotfix MR created ==="
echo "MR: ${PRISM_BRANCH} -> main-prism (squash disabled)"
