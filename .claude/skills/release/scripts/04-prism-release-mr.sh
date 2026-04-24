#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"

echo "=== Prism Release MR for v${NEXT_VERSION}-prism.1 ==="

# Ensure main is up to date
git checkout main
git pull origin main

# Checkout prism release branch and merge main
echo "--- Merging main into release/${NEXT_VERSION}-prism.1 ---"
git checkout "release/${NEXT_VERSION}-prism.1"
git pull prism "release/${NEXT_VERSION}-prism.1"

if ! git merge main --no-edit; then
  echo "  Merge conflicts detected, resolving with --theirs (keeping main's changes)..."
  git checkout --theirs .
  git add -A
  git commit --no-edit
fi
echo "  Main merged into prism release branch."

# Set prism version
echo "--- Setting version to ${NEXT_VERSION}-prism.1 ---"
make set-version VERSION="${NEXT_VERSION}-prism.1"

# Commit and push
git commit -am "chore: update all versions to ${NEXT_VERSION}-prism.1 and merge with main"
git push prism "release/${NEXT_VERSION}-prism.1"

# Create GitLab MR
echo "--- Creating GitLab MR ---"
glab mr create \
  --target-branch main-prism \
  --source-branch "release/${NEXT_VERSION}-prism.1" \
  --remove-source-branch \
  --title "release: ${NEXT_VERSION}-prism.1" \
  --description ""

echo ""
echo "=== Prism release MR created ==="
echo "Assign a reviewer on GitLab for validation."
