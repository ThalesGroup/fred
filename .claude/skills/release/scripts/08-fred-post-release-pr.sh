#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"

echo "=== Fred Post-Release PR for v${NEXT_VERSION} ==="

# Checkout main
git checkout main
git pull origin main

# Create post-release branch
echo "--- Creating post-release branch ---"
git checkout -B "post-release/${NEXT_VERSION}"

# Set post-release version
echo "--- Setting version to ${NEXT_VERSION}-post ---"
make set-version VERSION="${NEXT_VERSION}-post"

# Add Unreleased section to release notes
echo "--- Adding Unreleased section to release notes ---"
sed -i '1i **Unreleased** — XXXX-XX-XX\n' frontend/public/release.md
echo "  Unreleased section added."

# Commit and push
git commit -am "Chore: update release note and all versions to ${NEXT_VERSION}"
git push --set-upstream origin "post-release/${NEXT_VERSION}"

# Create PR
echo "--- Creating Pull Request ---"
gh pr create \
  --base develop \
  --head "post-release/${NEXT_VERSION}" \
  --title "post-release: ${NEXT_VERSION}" \
  --body ""

echo ""
echo "=== Fred post-release PR created ==="
echo "Assign a reviewer for validation."
