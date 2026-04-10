#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"

echo "=== Fred Post-Release Merge for v${NEXT_VERSION} ==="

# Merge the PR
echo "--- Merging Fred post-release PR ---"
gh pr merge "post-release/${NEXT_VERSION}" --merge --delete-branch -t "post-release: ${NEXT_VERSION}"
echo "  PR merged."

echo ""
echo "=== Fred post-release complete ==="
