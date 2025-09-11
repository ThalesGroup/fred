#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/i18n-audit.sh path/to/translation.en.json [code_dir]
# Example:
#   ./scripts/i18n-audit.sh src/locales/en/translation.json .

if ! command -v rg >/dev/null 2>&1; then echo "Error: ripgrep (rg) is required." >&2; exit 1; fi
if ! command -v jq >/dev/null 2>&1; then echo "Error: jq is required." >&2; exit 1; fi

LOCALE_FILE="${1:-}"; CODE_DIR="${2:-.}"
[[ -z "${LOCALE_FILE}" ]] && { echo "Usage: $0 path/to/translation.en.json [code_dir]" >&2; exit 1; }
[[ ! -f "${LOCALE_FILE}" ]] && { echo "Error: locale file not found: ${LOCALE_FILE}" >&2; exit 1; }

TMP_USED_KEYS="$(mktemp)"; TMP_DEF_KEYS="$(mktemp)"
cleanup(){ rm -f "$TMP_USED_KEYS" "$TMP_DEF_KEYS"; }; trap cleanup EXIT

# Collect USED keys from code (.js and .tsx). Suppress filenames with --no-filename.
rg --no-heading --no-filename -o -N \
  -g '!node_modules/**' -g '!dist/**' -g '!build/**' \
  -g '**/*.js' -g '**/*.tsx' \
  -P "(?:(?:\\bi18n\\.)?t\\(\\s*[\"'])\\K[^\"']+" \
  "$CODE_DIR" \
  | sort -u > "$TMP_USED_KEYS"

# OPTIONAL: drop obvious placeholders like a single '?' line
# grep -v -x '\?' -v -x '' -v '^\\s*$' "$TMP_USED_KEYS" | sponge "$TMP_USED_KEYS"  # requires moreutils
# or without sponge:
# tmp2="$(mktemp)"; grep -v -x '\?' "$TMP_USED_KEYS" > "$tmp2"; mv "$tmp2" "$TMP_USED_KEYS"

# Collect DEFINED keys (all dotted string paths)
jq -r '
  paths(scalars) as $p
  | select(getpath($p) | type == "string")
  | $p | map(tostring) | join(".")
' "${LOCALE_FILE}" | sort -u > "${TMP_DEF_KEYS}"

echo "=== i18n audit ==="
echo "Locale file: ${LOCALE_FILE}"
echo "Code dir   : ${CODE_DIR}"
echo
USED_COUNT=$(wc -l < "${TMP_USED_KEYS}" | tr -d ' ')
DEF_COUNT=$(wc -l < "${TMP_DEF_KEYS}" | tr -d ' ')
echo "Used keys found in code : ${USED_COUNT}"
echo "Defined keys in JSON    : ${DEF_COUNT}"
echo

echo "---- Missing keys (used in code but NOT defined) ----"
comm -23 "${TMP_USED_KEYS}" "${TMP_DEF_KEYS}" || true
echo

echo "---- Unused keys (defined but NOT used in code) ----"
comm -13 "${TMP_USED_KEYS}" "${TMP_DEF_KEYS}" || true
echo

MISSING_COUNT=$(comm -23 "${TMP_USED_KEYS}" "${TMP_DEF_KEYS}" | wc -l | tr -d ' ')
(( MISSING_COUNT > 0 )) && exit 2 || exit 0
