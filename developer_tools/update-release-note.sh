#!/usr/bin/env bash
set -euo pipefail

# Generate Markdown release notes for the NEXT code/ tag.
#
# Workflow:
#   1. All code changes are merged to main.
#   2. Run this script (before creating the tag):
#        ./update-release-note.sh --tag v1.0.7 \
#          --message "Short release summary / migration note" \
#          --file frontend/public/release.md
#   3. Commit release.md
#   4. Create and push the tag:
#        git tag -a code/v1.0.7 -m "Short release summary / migration note"
#        git push origin code/v1.0.7
#
# The script:
#   - Finds the latest existing code/* tag (e.g. code/v1.0.6).
#   - Computes commits in range: last_tag..HEAD (excluding merges).
#   - Splits them into "Features" vs "Bug fixes".
#   - Writes a new block for the *next* tag (v1.0.7) either:
#       - to stdout, or
#       - prepended to a file (if --file is given).

TAG=""
FILE=""
MESSAGE=""

usage() {
  cat <<EOF
Usage:
  $(basename "$0") --tag v1.0.7 --message "Summary" [--file RELEASE_NOTES.md]

Examples:
  # Just print the block for v1.0.7 to stdout
  $(basename "$0") --tag v1.0.7 --message "Image preview versioning and clean delete"

  # Prepend the block for v1.0.7 to frontend/public/release.md
  $(basename "$0") --tag v1.0.7 \
    --message "Image preview versioning and clean delete" \
    --file frontend/public/release.md

Options:
  -t, --tag       TAG        Next version tag (with or without 'code/' prefix), e.g. v1.0.7 or code/v1.0.7
  -m, --message   MESSAGE    General comment / migration note for this release (optional but recommended)
  -f, --file      FILE       File to prepend the generated release block to (if omitted, prints to stdout)
  -h, --help                 Show this help
EOF
}

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--tag)
      TAG="${2:-}"
      shift 2
      ;;
    -m|--message)
      MESSAGE="${2:-}"
      shift 2
      ;;
    -f|--file)
      FILE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [ -z "$TAG" ]; then
  echo "Error: --tag is required." >&2
  usage
  exit 1
fi

# Normalize the next tag name for display and internal use
normalize_tag() {
  local raw_tag="$1"
  if [[ "$raw_tag" == code/* ]]; then
    printf '%s\n' "$raw_tag"
  else
    printf 'code/%s\n' "$raw_tag"
  fi
}

next_full_tag="$(normalize_tag "$TAG")"
next_display_tag="${next_full_tag#code/}"

# Find the latest existing code/* tag (previous release)
find_previous_tag() {
  git for-each-ref \
    --sort=creatordate \
    --format="%(refname:short)" \
    "refs/tags/code/" | tail -n 1
}

prev_tag="$(find_previous_tag || true)"

if [ -z "$prev_tag" ]; then
  echo "Warning: no existing code/ tags found. Using HEAD only." >&2
fi

# Generate the release block for the *next* tag based on prev_tag..HEAD
generate_block_for_next_tag() {
  local display_tag="$1"
  local message="$2"
  local prev="$3"

  # Release date = date of current HEAD
  local release_date=""
  release_date=$(git log -1 --pretty=format:"%ad" --date=short HEAD 2>/dev/null || true)
  local display_date="${release_date:-TBD}"

  # Commit range
  local range=""
  if [ -n "$prev" ]; then
    range="${prev}..HEAD"
  else
    range="HEAD"
  fi

  # All commit subjects in the range, excluding merges
  local all_commits=""
  all_commits=$(git log --no-merges --pretty=format:"%s" "$range" 2>/dev/null || true)

  local features=""
  local bugfixes=""

  if [ -n "$all_commits" ]; then
    # Bug fixes: messages with fix/bug/hotfix/patch (case-insensitive)
    bugfixes=$(printf '%s\n' "$all_commits" | grep -Ei 'fix|bug|hotfix|patch' || true)
    # Features: the rest
    features=$(printf '%s\n' "$all_commits" | grep -Evi 'fix|bug|hotfix|patch' || true)
  fi

  # Features
  echo "- **${display_tag}** — 📅 ${display_date}  "
  echo "  - **Summary**"
  if [ -n "$message" ]; then
    echo "    - ${message}"
  else
    echo "    - (add summary)"
  fi

  if [ -n "$features" ]; then
    echo "  - **Features**"
    printf '%s\n' "$features" | sed 's/^/    - /'
  fi

  if [ -n "$bugfixes" ]; then
    echo "  - **Bug fixes**"
    printf '%s\n' "$bugfixes" | sed 's/^/    - /'
  fi

  echo
  echo "---"
  echo
}

# --- Main logic ---

if [ -z "$FILE" ]; then
  # Just print to stdout
  generate_block_for_next_tag "$next_display_tag" "$MESSAGE" "$prev_tag"
else
  # Prepend to file
  tmpfile="$(mktemp)"
  {
    generate_block_for_next_tag "$next_display_tag" "$MESSAGE" "$prev_tag"
    if [ -s "$FILE" ]; then
      echo
      cat "$FILE"
    elif [ -f "$FILE" ]; then
      :
    fi
  } > "$tmpfile"
  mv "$tmpfile" "$FILE"
fi
