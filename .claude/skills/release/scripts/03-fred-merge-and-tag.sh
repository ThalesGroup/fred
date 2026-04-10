#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"

echo "=== Fred Merge & Tag for v${NEXT_VERSION} ==="

# Merge the PR
echo "--- Merging Fred PR ---"
gh pr merge "release/${NEXT_VERSION}" --merge --delete-branch -t "release: ${NEXT_VERSION}"
echo "  PR merged."

# Checkout main and pull
git checkout main
git pull origin main

# Create and push tags
echo "--- Creating tags ---"
git tag "code/v${NEXT_VERSION}"
git tag "chart/v${NEXT_VERSION}"
git push origin "code/v${NEXT_VERSION}" "chart/v${NEXT_VERSION}"
echo "  Tags pushed: code/v${NEXT_VERSION}, chart/v${NEXT_VERSION}"

echo ""
echo "=== Fred release v${NEXT_VERSION} tagged ==="
echo "GitHub Actions will now build Docker images (code/v*) and Helm charts (chart/v*)."
