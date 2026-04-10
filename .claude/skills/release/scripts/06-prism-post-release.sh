#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"

echo "=== Prism Post-Release for v${NEXT_VERSION}-prism.1 ==="

# Checkout main-prism
git checkout main-prism
git pull prism main-prism

# Create post-release branch
echo "--- Creating post-release branch ---"
git checkout -B "post-release/${NEXT_VERSION}-prism.1"

# Set post-release version
echo "--- Setting version to ${NEXT_VERSION}-prism.1-post ---"
make set-version VERSION="${NEXT_VERSION}-prism.1-post"

# Commit and push
git commit -am "chore: update all versions to ${NEXT_VERSION}-prism.1-post"
git push --set-upstream prism "post-release/${NEXT_VERSION}-prism.1"

# Create MR
echo "--- Creating GitLab MR ---"
glab mr create \
  --target-branch develop-prism \
  --source-branch "post-release/${NEXT_VERSION}-prism.1" \
  --remove-source-branch \
  --title "post-release: ${NEXT_VERSION}-prism.1" \
  --description ""

# Disable squash on the MR
echo "--- Disabling squash on MR ---"
MR_IID=$(glab api "projects/:id/merge_requests?source_branch=$(git branch --show-current)&state=opened&per_page=1" | jq '.[0].iid')
glab api "projects/:id/merge_requests/${MR_IID}" -X PUT -f squash=false > /dev/null
echo "  Squash disabled."

echo ""
echo "=== Prism post-release MR created ==="
echo "Assign a reviewer on GitLab for validation."
