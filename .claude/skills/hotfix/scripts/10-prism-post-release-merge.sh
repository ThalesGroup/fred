#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH_NAME="post-release/${NEXT_VERSION}-prism.1"

echo "=== Prism: Merge post-release MR ==="

echo "--- Merging: $BRANCH_NAME -> develop-prism ---"
glab mr merge "$BRANCH_NAME" \
  --auto-merge \
  --remove-source-branch \
  --message "post-release: ${NEXT_VERSION}-prism.1"

echo ""
echo "=== Hotfix $NEXT_VERSION release complete! ==="
echo ""
echo "Summary:"
echo "  - Fred hotfix merged into main and tagged (code/v${NEXT_VERSION}, chart/v${NEXT_VERSION})"
echo "  - Prism hotfix merged into main-prism and tagged (code/v${NEXT_VERSION}-prism.1, chart/v${NEXT_VERSION}-prism.1)"
echo "  - Fred post-release merged into develop (version: ${NEXT_VERSION}-post)"
echo "  - develop/develop-prism conflict resolved (version: ${NEXT_VERSION}-prism.1-post)"
echo "  - Prism post-release merged into develop-prism"
