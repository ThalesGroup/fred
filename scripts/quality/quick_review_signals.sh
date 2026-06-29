#!/usr/bin/env bash
# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -u
set -o pipefail

BASE_REF="${1:-origin/swift}"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT" || exit 1

section() {
  printf '\n## %s\n' "$1"
}

run_or_note() {
  local description="$1"
  shift
  printf '\n# %s\n' "$description"
  "$@" || printf 'Signal unavailable or command failed: %s\n' "$description"
}

if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
  printf 'ERROR: base ref not found: %s\n' "$BASE_REF" >&2
  printf 'Pass an explicit valid base ref, usually origin/swift for this repository.\n' >&2
  exit 2
fi

RANGE="$BASE_REF...HEAD"
status_code=0

mapfile -t branch_files < <(git diff --name-only "$RANGE" 2>/dev/null || true)
mapfile -t worktree_files < <(
  {
    git diff --name-only 2>/dev/null || true
    git diff --cached --name-only 2>/dev/null || true
    git ls-files --others --exclude-standard 2>/dev/null || true
  } | awk 'NF && !seen[$0]++'
)
mapfile -t touched_files < <(
  {
    printf '%s\n' "${branch_files[@]}"
    printf '%s\n' "${worktree_files[@]}"
  } | awk 'NF && !seen[$0]++'
)

section "Review Target"
printf 'Repository: %s\n' "$ROOT"
printf 'Branch: %s\n' "$(git branch --show-current)"
printf 'HEAD: %s\n' "$(git rev-parse HEAD)"
printf 'Base: %s\n' "$BASE_REF"
printf 'Range: %s\n' "$RANGE"
git merge-base "$BASE_REF" HEAD >/dev/null 2>&1 \
  && printf 'Merge base: %s\n' "$(git merge-base "$BASE_REF" HEAD)"

section "Working Tree"
git status --short --untracked-files=all

section "Branch Diff Files"
if ((${#branch_files[@]} == 0)); then
  printf 'No committed branch diff against %s.\n' "$BASE_REF"
else
  printf '%s\n' "${branch_files[@]}"
fi

section "Local Worktree Files"
if ((${#worktree_files[@]} == 0)); then
  printf 'No local staged, unstaged, or untracked files.\n'
else
  printf '%s\n' "${worktree_files[@]}"
fi

section "Diff Stats"
run_or_note "branch diff stat" git diff --stat "$RANGE"
run_or_note "local worktree diff stat" git diff --stat

section "Whitespace Check"
if git diff --check "$RANGE" && git diff --check; then
  printf 'OK: no whitespace errors detected in branch or local diffs.\n'
else
  printf 'FAIL: whitespace errors detected by git diff --check.\n'
  status_code=1
fi

section "Generated Or Locked Files Touched"
printf '%s\n' "${touched_files[@]}" \
  | rg -n '(^|/)(openapi\.json|.*OpenApi\.ts|package-lock\.json|uv\.lock|configuration\.schema\.json|values\.schema\.json)$' \
  || printf 'No generated or lock files detected in touched paths.\n'

section "Potential Missing Apache Headers"
missing_header=0
for path in "${touched_files[@]}"; do
  [[ -f "$path" ]] || continue
  case "$path" in
    *.py|*.ts|*.tsx|*.js|*.jsx|*.sh|*.css|*.scss)
      ;;
    *)
      continue
      ;;
  esac
  case "$path" in
    */__pycache__/*|*/node_modules/*|*/.venv/*|*/dist/*|*/build/*|*.generated.*|*OpenApi.ts)
      continue
      ;;
  esac
  if ! sed -n '1,20p' "$path" | rg -q 'Licensed under the Apache License'; then
    printf '%s\n' "$path"
    missing_header=1
  fi
done
if ((missing_header == 0)); then
  printf 'No missing Apache-2.0 headers detected in touched source-like files.\n'
fi

section "TODO/FIXME In Touched Files"
if ((${#touched_files[@]} == 0)); then
  printf 'No touched files to scan.\n'
else
  todo_files=()
  for path in "${touched_files[@]}"; do
    [[ "$path" == "scripts/quality/quick_review_signals.sh" ]] && continue
    todo_files+=("$path")
  done
  if ((${#todo_files[@]} == 0)); then
    printf 'No touched files to scan after script self-exclusion.\n'
  else
    rg -n 'TODO|FIXME|XXX|HACK' "${todo_files[@]}" 2>/dev/null \
      || printf 'No TODO/FIXME signals found in touched files.\n'
  fi
fi

section "Docs And Tracking Files Touched"
printf '%s\n' "${touched_files[@]}" \
  | rg -n '(^docs/swift/(rfc|backlog|data|tracks|platform)/|^docs/swift/(STATUS|WORKPLAN|PMO-BOARD|README)\.md$|CLAUDE\.md$|AGENTS\.md$)' \
  || printf 'No docs, tracking, or assistant-governance files detected in touched paths.\n'

section "Temporary Swift-Specific Residue Check: Control-Plane Self-Test Harness Files"
git ls-files 'apps/control-plane-backend/**' \
  | rg -n '(^|/)(self_test|knowledge_flow_client)' \
  || printf 'No control-plane backend self-test harness files found.\n'

section "Rework Hand-Rolled Fetches Against Generated-Client Prefixes"
# Flags raw fetch("/<prefix>/...") calls under apps/frontend/src/rework where the
# matching backend already has a generated RTK Query client (knowledgeFlowOpenApi.ts,
# controlPlaneOpenApi.ts, etc.). Each hit is a candidate to replace with the generated
# query/mutation so auth, token refresh, 401 retry and caching stay centralized in
# createDynamicBaseQuery instead of drifting per call site.
# Known-legitimate exceptions the reviewer should confirm, not auto-flag: SSE endpoints
# (Accept: text/event-stream, streamed response.body) and blob/file downloads, which
# RTK Query cannot model and are intentionally hand-rolled.
rework_fetch_glob=(--glob '*.ts' --glob '*.tsx')
rework_fetch_pattern='fetch\(\s*[\x22\x27\x60]/(knowledge-flow|control-plane|agentic|evaluation|pod)/'
if [[ -d apps/frontend/src/rework ]]; then
  rg -n "${rework_fetch_glob[@]}" "$rework_fetch_pattern" apps/frontend/src/rework \
    || printf 'No hand-rolled backend fetches detected under apps/frontend/src/rework.\n'
else
  printf 'Rework directory not present; skipping hand-rolled fetch scan.\n'
fi

section "Reviewer Reminder"
printf '%s\n' \
  'This script prints signals only. It does not replace the semantic review in:' \
  'docs/swift/platform/QUALITY_REVIEW_PROTOCOL.md'

exit "$status_code"
