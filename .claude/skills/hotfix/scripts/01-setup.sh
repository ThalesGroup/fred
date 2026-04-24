#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version> (e.g. 1.4.1)}"

SCRIPTS_SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_TMP_DIR="/tmp/fred-hotfix-scripts"
REPO_ROOT="$(git rev-parse --show-toplevel)"

echo "=== Hotfix Setup: $NEXT_VERSION ==="

# Copy scripts to /tmp so they survive branch switches
echo "--- Copying scripts to $SCRIPTS_TMP_DIR ---"
rm -rf "$SCRIPTS_TMP_DIR"
cp -r "$SCRIPTS_SRC_DIR" "$SCRIPTS_TMP_DIR"
chmod +x "$SCRIPTS_TMP_DIR"/*.sh

# Check prerequisites
echo "--- Checking prerequisites ---"
for cmd in gh glab jq make git; do
  command -v "$cmd" &>/dev/null || { echo "ERROR: '$cmd' not found in PATH"; exit 1; }
done

# Check remotes
git -C "$REPO_ROOT" remote get-url origin &>/dev/null || { echo "ERROR: remote 'origin' (GitHub) not found"; exit 1; }
git -C "$REPO_ROOT" remote get-url prism  &>/dev/null || { echo "ERROR: remote 'prism' (GitLab) not found"; exit 1; }

# Check working tree is clean
if ! git -C "$REPO_ROOT" diff --quiet || ! git -C "$REPO_ROOT" diff --cached --quiet; then
  echo "ERROR: Working tree is not clean. Stash or commit your changes first."
  exit 1
fi

# Pull latest main branches
echo "--- Pulling latest main and main-prism ---"
git -C "$REPO_ROOT" checkout main && git -C "$REPO_ROOT" pull origin main
git -C "$REPO_ROOT" checkout main-prism && git -C "$REPO_ROOT" pull prism main-prism

# Verify the Fred hotfix PR exists and is approved
echo "--- Verifying Fred hotfix PR for hotfix/${NEXT_VERSION} ---"
PR_STATE=$(gh pr view "hotfix/${NEXT_VERSION}" --json state,reviewDecision --jq '"state=\(.state) review=\(.reviewDecision)"' 2>/dev/null || echo "NOT_FOUND")
if [[ "$PR_STATE" == "NOT_FOUND" ]]; then
  echo "ERROR: No open PR found for branch hotfix/${NEXT_VERSION} on GitHub."
  echo "The hotfix PR must already exist and be approved before running this skill."
  exit 1
fi
echo "Fred hotfix PR: $PR_STATE"

echo ""
echo "=== Setup complete ==="
echo "Scripts copied to: $SCRIPTS_TMP_DIR"
echo ""
echo "Next: bash $SCRIPTS_TMP_DIR/02-fred-hotfix-merge-and-tag.sh $NEXT_VERSION"
