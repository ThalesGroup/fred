#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
PRISM_BRANCH="hotfix/${NEXT_VERSION}-prism.1"

echo "=== Prism: Merge hotfix MR and tag ${NEXT_VERSION}-prism.1 ==="

git -C "$REPO_ROOT" checkout main-prism
git -C "$REPO_ROOT" pull prism main-prism

# Merge the approved MR on GitLab
echo "--- Merging Prism hotfix MR: $PRISM_BRANCH ---"
glab mr merge "$PRISM_BRANCH" \
  --auto-merge \
  --remove-source-branch \
  --message "hotfix: ${NEXT_VERSION}-prism.1"

# Pull merged main-prism
git -C "$REPO_ROOT" pull prism main-prism

# Create tags
echo "--- Creating tags code/v${NEXT_VERSION}-prism.1 and chart/v${NEXT_VERSION}-prism.1 ---"
git -C "$REPO_ROOT" tag "code/v${NEXT_VERSION}-prism.1"
git -C "$REPO_ROOT" tag "chart/v${NEXT_VERSION}-prism.1"
git -C "$REPO_ROOT" push prism "code/v${NEXT_VERSION}-prism.1" "chart/v${NEXT_VERSION}-prism.1"

echo ""
echo "=== Prism hotfix merged and tagged ==="
echo "Tags pushed: code/v${NEXT_VERSION}-prism.1, chart/v${NEXT_VERSION}-prism.1"
echo ""
echo "Next: bash /tmp/fred-hotfix-scripts/05-fred-post-release-pr.sh $NEXT_VERSION"
