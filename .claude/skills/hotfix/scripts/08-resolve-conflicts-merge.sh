#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH_NAME="resolve-version-conflict-after-hotfix-${NEXT_VERSION}"

echo "=== Merge conflict resolution MR ==="

echo "--- Merging: $BRANCH_NAME -> develop-prism ---"
glab mr merge "$BRANCH_NAME" \
  --auto-merge \
  --remove-source-branch \
  --message "chore: resolve version conflict after hotfix ${NEXT_VERSION}"

echo ""
echo "=== Conflict resolution merged into develop-prism ==="
echo ""
echo "Next: bash /tmp/fred-hotfix-scripts/09a-prism-post-release-start.sh ${NEXT_VERSION}"
