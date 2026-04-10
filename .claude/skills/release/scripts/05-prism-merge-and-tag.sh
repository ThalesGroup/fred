#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"

echo "=== Prism Merge & Tag for v${NEXT_VERSION}-prism.1 ==="

# Merge the MR
echo "--- Merging Prism MR ---"
glab mr merge "release/${NEXT_VERSION}-prism.1" \
  --auto-merge \
  --remove-source-branch \
  --message "release: ${NEXT_VERSION}-prism.1"
echo "  MR merged."

# Checkout main-prism and pull
git checkout main-prism
git pull prism main-prism

# Create and push tags
echo "--- Creating tags ---"
git tag "code/v${NEXT_VERSION}-prism.1"
git tag "chart/v${NEXT_VERSION}-prism.1"
git push prism "code/v${NEXT_VERSION}-prism.1" "chart/v${NEXT_VERSION}-prism.1"
echo "  Tags pushed: code/v${NEXT_VERSION}-prism.1, chart/v${NEXT_VERSION}-prism.1"

echo ""
echo "=== Prism release v${NEXT_VERSION}-prism.1 tagged ==="
