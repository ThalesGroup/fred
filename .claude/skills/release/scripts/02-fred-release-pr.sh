#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"

echo "=== Fred Release PR for v${NEXT_VERSION} ==="

# Checkout release branch
git checkout "release/${NEXT_VERSION}"

# Set version across all components
echo "--- Setting version to ${NEXT_VERSION} ---"
make set-version VERSION="${NEXT_VERSION}"

echo ""
echo "--- Version update complete ---"
echo ""
echo "IMPORTANT: The release notes in frontend/public/release.md need to be updated."
echo "  - Replace 'Unreleased' title with 'v${NEXT_VERSION}'"
echo "  - Set today's date"
echo "  - Verify content against commits: git log main..release/${NEXT_VERSION} --oneline --no-merges"
echo ""
echo "Once the release notes are updated, commit and push will be done by the agent."
echo ""

# Stage all version changes (but NOT the release notes yet — agent will handle that)
git add -A
echo "  All version changes staged."

echo "--- Creating Pull Request ---"
# Create PR (may fail if already exists, that's ok)
if gh pr view "release/${NEXT_VERSION}" --json number &>/dev/null; then
  echo "  PR for release/${NEXT_VERSION} already exists."
  gh pr view "release/${NEXT_VERSION}" --json url -q '.url'
else
  gh pr create \
    --base main \
    --head "release/${NEXT_VERSION}" \
    --title "release: ${NEXT_VERSION}" \
    --body "" \
    --draft
  echo "  PR created as draft (release notes still need updating)."
fi

echo ""
echo "=== Fred release PR ready ==="
echo "Next: Update release notes, then commit and push."
