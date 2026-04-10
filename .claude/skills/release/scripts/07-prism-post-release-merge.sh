#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"

echo "=== Prism Post-Release Merge for v${NEXT_VERSION}-prism.1 ==="

# Merge the MR
echo "--- Merging Prism post-release MR ---"
glab mr merge "post-release/${NEXT_VERSION}-prism.1" \
  --auto-merge \
  --remove-source-branch \
  --message "post-release: ${NEXT_VERSION}-prism.1"
echo "  MR merged."

echo ""
echo "=== Prism post-release complete ==="
