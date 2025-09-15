#!/usr/bin/env bash
# Fred — Batch Vector Search Runner
# Why this shape:
# - One script to compare retrieval policies consistently over the SAME questions.
# - Stable filenames (timestamp + slug) so you can diff/evaluate later.
# - Minimal deps: curl (jq optional for pretty JSON).
#
# Usage examples:
#   ./run_vector_searches.sh --hybrid
#   ./run_vector_searches.sh --semantic --top-k 5
#   ./run_vector_searches.sh --strict --tags 111aaa,222bbb
#   ./run_vector_searches.sh --hybrid --endpoint http://localhost:8111/knowledge-flow/v1/vector/search
#
# Flags:
#   --hybrid | --semantic | --strict  (required: choose exactly one)
#   --top-k N                         (default: 3)
#   --endpoint URL                    (default: http://localhost:8111/knowledge-flow/v1/vector/search)
#   --tags id1,id2,...                (optional: document_library_tags_ids)

set -euo pipefail

# ---------- Defaults ----------
POLICY=""
TOP_K=3
ENDPOINT="http://localhost:8111/knowledge-flow/v1/vector/search"
TAGS_CSV=""

# ---------- Parse args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --hybrid)   POLICY="hybrid"; shift ;;
    --semantic) POLICY="semantic"; shift ;;
    --strict)   POLICY="strict"; shift ;;
    --top-k)    TOP_K="${2:-}"; shift 2 ;;
    --endpoint) ENDPOINT="${2:-}"; shift 2 ;;
    --tags)     TAGS_CSV="${2:-}"; shift 2 ;;
    -h|--help)
      grep '^# ' "$0" | sed 's/^# //'
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$POLICY" ]]; then
  echo "Error: choose one of --hybrid | --semantic | --strict" >&2
  exit 1
fi

# ---------- Tags → JSON array ----------
TAGS_JSON="[]"
if [[ -n "$TAGS_CSV" ]]; then
  IFS=',' read -r -a TAG_ARR <<< "$TAGS_CSV"
  TAGS_JSON="["
  for i in "${!TAG_ARR[@]}"; do
    id="${TAG_ARR[$i]}"
    [[ $i -gt 0 ]] && TAGS_JSON+=","
    TAGS_JSON+="\"$id\""
  done
  TAGS_JSON+="]"
fi

# ---------- Question set (natural queries) ----------
QUESTIONS=(
  "Who are Sen and Nussbaum?"
  "How do Sen and Nussbaum define the Capability Approach in human development?"
  "Why is the Capability Approach considered different from Maslow’s hierarchy of needs?"
  "In what ways has the Capability Approach been applied to social policy so far?"
  "How can homelessness be interpreted through the lens of Nussbaum’s central capabilities?"
  "Has the Capability Approach been integrated into agent-based modeling or computational methods?"
  "What benchmark did the authors design to evaluate LLMs’ policymaking capabilities?"
  "Which cities were used in the study’s policy decision scenarios?"
  "What are the challenges of operationalizing the Capability Approach in practice?"
)

# ---------- Helpers ----------
slugify() {
  # Lowercase, replace non-alnum with '-', squeeze dashes, trim.
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/-+/-/g; s/^-|-$//g'
}

timestamp() { date +%Y%m%d-%H%M%S; }

# Output dir: results/<ts>-<policy>/
TS="$(timestamp)"
OUTDIR="results/${TS}-${POLICY}"
mkdir -p "$OUTDIR"

# ---------- Run ----------
echo "Running ${#QUESTIONS[@]} queries with policy=$POLICY, top_k=$TOP_K"
echo "Endpoint: $ENDPOINT"
echo "Tags: $TAGS_JSON"
echo "Output dir: $OUTDIR"
echo

for idx in "${!QUESTIONS[@]}"; do
  q="${QUESTIONS[$idx]}"
  n=$((idx+1))
  slug="$(slugify "$q")"
  outfile="${OUTDIR}/$(printf '%02d' "$n")_${slug}.json"

  # Build JSON body (avoid shell quoting pitfalls with printf)
  BODY=$(printf '{\n  "question": "%s",\n  "top_k": %d,\n  "document_library_tags_ids": %s,\n  "search_policy": "%s"\n}\n' \
    "${q//\"/\\\"}" "$TOP_K" "$TAGS_JSON" "$POLICY")

  echo "[$(printf '%02d' "$n")/${#QUESTIONS[@]}] $q"
  if command -v jq >/dev/null 2>&1; then
    curl -sS -X POST "$ENDPOINT" \
      -H 'accept: application/json' \
      -H 'Content-Type: application/json' \
      -d "$BODY" | jq '.' > "$outfile"
  else
    curl -sS -X POST "$ENDPOINT" \
      -H 'accept: application/json' \
      -H 'Content-Type: application/json' \
      -d "$BODY" > "$outfile"
  fi

  echo "  -> saved: $outfile"
done

echo
echo "Done. Results in: $OUTDIR"
