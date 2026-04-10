#!/usr/bin/env bash
set -euo pipefail

NEXT_VERSION="${1:?Usage: $0 <version>}"
SCRIPTS_SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_TMP_DIR="/tmp/fred-release-scripts"

echo "=== Release Setup for v${NEXT_VERSION} ==="

# Copy scripts to /tmp so they survive branch switches
echo "--- Copying release scripts to ${SCRIPTS_TMP_DIR} ---"
rm -rf "$SCRIPTS_TMP_DIR"
cp -r "$SCRIPTS_SRC_DIR" "$SCRIPTS_TMP_DIR"
chmod +x "$SCRIPTS_TMP_DIR"/*.sh
echo "  OK: Scripts copied to ${SCRIPTS_TMP_DIR}"

# Check prerequisites
echo "--- Checking prerequisites ---"
for cmd in gh glab jq; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: '$cmd' is not installed." >&2
    exit 1
  fi
  echo "  OK: $cmd"
done

# Check git remotes
echo "--- Checking git remotes ---"
if ! git remote get-url origin &>/dev/null; then
  echo "ERROR: 'origin' remote not configured." >&2
  exit 1
fi
echo "  OK: origin -> $(git remote get-url origin)"

if ! git remote get-url prism &>/dev/null; then
  echo "ERROR: 'prism' remote not configured." >&2
  exit 1
fi
echo "  OK: prism -> $(git remote get-url prism)"

# Check clean working tree
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: Working tree has uncommitted changes. Please commit or stash them." >&2
  exit 1
fi
echo "  OK: Working tree is clean"

# Pull latest branches
echo "--- Pulling latest branches ---"
git checkout develop
git pull origin develop

git checkout develop-prism
git pull prism develop-prism

# Verify sync
echo "--- Checking branch sync ---"
SYNC=$(git rev-list --left-right --count origin/develop...prism/develop-prism)
LEFT=$(echo "$SYNC" | awk '{print $1}')
echo "  develop is $LEFT commit(s) ahead of develop-prism"
if [ "$LEFT" != "0" ]; then
  echo "WARNING: develop has $LEFT commits not in develop-prism. This may be expected."
fi

# Create release branches
echo "--- Creating release branches ---"

# Fred release branch
git checkout develop
if git show-ref --verify --quiet "refs/heads/release/${NEXT_VERSION}"; then
  echo "  Branch release/${NEXT_VERSION} already exists locally, checking out."
  git checkout "release/${NEXT_VERSION}"
else
  git checkout -B "release/${NEXT_VERSION}"
fi
git push --set-upstream origin "release/${NEXT_VERSION}"
echo "  OK: release/${NEXT_VERSION} pushed to origin"

# Prism release branch
git checkout prism/develop-prism
if git show-ref --verify --quiet "refs/heads/release/${NEXT_VERSION}-prism.1"; then
  echo "  Branch release/${NEXT_VERSION}-prism.1 already exists locally, checking out."
  git checkout "release/${NEXT_VERSION}-prism.1"
else
  git checkout -B "release/${NEXT_VERSION}-prism.1"
fi
git push --set-upstream prism "release/${NEXT_VERSION}-prism.1"
echo "  OK: release/${NEXT_VERSION}-prism.1 pushed to prism"

echo ""
echo "=== Setup complete ==="
echo "  Fred release branch:  release/${NEXT_VERSION}"
echo "  Prism release branch: release/${NEXT_VERSION}-prism.1"
