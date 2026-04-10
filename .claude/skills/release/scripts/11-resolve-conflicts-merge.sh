#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"
BRANCH_NAME="resolve-version-conflict-after-${NEXT_VERSION}"

echo "=== Resolve Conflicts Merge after v${NEXT_VERSION} ==="

# Merge the MR
echo "--- Merging conflict resolution MR ---"
glab mr merge "$BRANCH_NAME" \
  --auto-merge \
  --remove-source-branch \
  --message "Merge develop into develop-prism with version conflict resolved"
echo "  MR merged."

echo ""
echo "=== Version conflict resolution complete ==="
