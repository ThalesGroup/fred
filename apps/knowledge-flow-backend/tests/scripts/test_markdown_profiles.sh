#!/usr/bin/env bash
set -euo pipefail

# Recursively test PDF/DOCX/PPTX markdown conversion against a running KF API.
#
# Strategy:
# - For each file and each requested profile (fast/medium/rich):
#   1) POST /upload-process-documents with metadata_json.profile
#   2) Parse document_uid from NDJSON stream
#   3) GET /markdown/{document_uid}
#   4) Save markdown under output/profile/<relative-path>.md
#
# Notes:
# - This script is designed to evaluate markdown quality only.
# - It expects KF to be configured with no-op output processors for tested suffixes
#   (see config/configuration_test.yaml), so no embeddings/vectorization are required.
# - summary.tsv includes per-run diagnostics:
#   upload_http, markdown_http, stage, upload_ms, markdown_ms, total_ms.

BASE_URL="http://localhost:8111/knowledge-flow/v1"
INPUT_DIR=""
OUTPUT_DIR="./target/markdown-profile-tests"
PROFILES="fast,medium,rich"
AUTH_BEARER="${AUTH_BEARER:-}"
TIMEOUT_SECONDS=600
KEEP_RAW=0
RUN_ID="${RUN_ID:-$(date +%Y%m%d%H%M%S)}"

if [[ -t 1 ]]; then
  C_RED=$'\033[31m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'
  C_BOLD=$'\033[1m'
  C_RESET=$'\033[0m'
else
  C_RED=""
  C_GREEN=""
  C_YELLOW=""
  C_BLUE=""
  C_BOLD=""
  C_RESET=""
fi

usage() {
  cat <<EOF
Usage:
  $(basename "$0") --input-dir <folder> [options]

Required:
  --input-dir <path>           Root folder scanned recursively for .pdf/.docx/.pptx

Options:
  --base-url <url>             KF base URL (default: ${BASE_URL})
  --output-dir <path>          Output folder for markdown files (default: ${OUTPUT_DIR})
  --profiles <csv>             Profiles to test: fast,medium,rich (default: ${PROFILES})
  --auth-bearer <token>        Optional bearer token
  --timeout <seconds>          Curl max time per request (default: ${TIMEOUT_SECONDS})
  --keep-raw                   Keep raw NDJSON/JSON responses under <output>/_raw
  -h, --help                   Show this help

Examples:
  $(basename "$0") --input-dir ./fixtures
  $(basename "$0") --input-dir ./fixtures --profiles fast,rich --output-dir ./target/md-tests
  $(basename "$0") --input-dir ./fixtures --auth-bearer "\$TOKEN"
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "${C_RED}[ERROR]${C_RESET} Missing required command: $cmd" >&2
    exit 2
  fi
}

trim() {
  local s="$1"
  # shellcheck disable=SC2001
  s="$(echo "$s" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  echo "$s"
}

now_ms() {
  python3 - <<'PY'
import time
print(time.time_ns() // 1_000_000)
PY
}

append_summary() {
  local summary_file="$1"
  local profile="$2"
  local status="$3"
  local file="$4"
  local document_uid="$5"
  local chars="$6"
  local upload_http="$7"
  local markdown_http="$8"
  local stage="$9"
  local upload_ms="${10}"
  local markdown_ms="${11}"
  local total_ms="${12}"
  local error="${13}"
  printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
    "${RUN_ID}" \
    "${profile}" \
    "${status}" \
    "${file}" \
    "${document_uid}" \
    "${chars}" \
    "${upload_http}" \
    "${markdown_http}" \
    "${stage}" \
    "${upload_ms}" \
    "${markdown_ms}" \
    "${total_ms}" \
    "${error}" >> "${summary_file}"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --input-dir)
        if [[ $# -lt 2 ]]; then
          echo "${C_RED}[ERROR]${C_RESET} Missing value for --input-dir" >&2
          usage
          exit 2
        fi
        INPUT_DIR="$2"
        shift 2
        ;;
      --base-url)
        if [[ $# -lt 2 ]]; then
          echo "${C_RED}[ERROR]${C_RESET} Missing value for --base-url" >&2
          usage
          exit 2
        fi
        BASE_URL="$2"
        shift 2
        ;;
      --output-dir)
        if [[ $# -lt 2 ]]; then
          echo "${C_RED}[ERROR]${C_RESET} Missing value for --output-dir" >&2
          usage
          exit 2
        fi
        OUTPUT_DIR="$2"
        shift 2
        ;;
      --profiles)
        if [[ $# -lt 2 ]]; then
          echo "${C_RED}[ERROR]${C_RESET} Missing value for --profiles" >&2
          usage
          exit 2
        fi
        PROFILES="$2"
        shift 2
        ;;
      --auth-bearer)
        if [[ $# -lt 2 ]]; then
          echo "${C_RED}[ERROR]${C_RESET} Missing value for --auth-bearer" >&2
          usage
          exit 2
        fi
        AUTH_BEARER="$2"
        shift 2
        ;;
      --timeout)
        if [[ $# -lt 2 ]]; then
          echo "${C_RED}[ERROR]${C_RESET} Missing value for --timeout" >&2
          usage
          exit 2
        fi
        TIMEOUT_SECONDS="$2"
        shift 2
        ;;
      --keep-raw)
        KEEP_RAW=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "${C_RED}[ERROR]${C_RESET} Unknown argument: $1" >&2
        usage
        exit 2
        ;;
    esac
  done
}

json_profile_payload() {
  local profile="$1"
  python3 - "$profile" <<'PY'
import json
import sys

profile = sys.argv[1]
payload = {
    "tags": [],
    "source_tag": "fred",
    "profile": profile,
}
print(json.dumps(payload, ensure_ascii=False))
PY
}

parse_upload_stream() {
  local ndjson_file="$1"
  python3 - "$ndjson_file" <<'PY'
import json
import sys

path = sys.argv[1]
doc_uid = ""
done_status = ""
errors = []

with open(path, "r", encoding="utf-8", errors="replace") as f:
    for raw in f:
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue

        status = str(obj.get("status", "")).lower()
        step = str(obj.get("step", ""))
        uid = obj.get("document_uid")
        if isinstance(uid, str) and uid:
            doc_uid = uid

        if status in {"failed", "error"}:
            err = obj.get("error")
            if err:
                errors.append(str(err))
            else:
                errors.append(line)

        if step == "done":
            done_status = status

if done_status in {"success", "finished"} and doc_uid:
    print("ok\t" + doc_uid + "\t")
    sys.exit(0)

if doc_uid and not errors:
    # Sometimes stream may end without explicit final status.
    print("ok\t" + doc_uid + "\t")
    sys.exit(0)

message = errors[-1] if errors else "No document_uid found in upload stream"
print("error\t\t" + message)
sys.exit(1)
PY
}

extract_markdown_content() {
  local json_file="$1"
  local out_file="$2"
  python3 - "$json_file" "$out_file" <<'PY'
import json
import sys
from pathlib import Path

json_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
raw = json_path.read_text(encoding="utf-8", errors="replace")

try:
    payload = json.loads(raw)
except Exception as exc:
    raise SystemExit(f"Invalid JSON response: {exc}")

content = payload.get("content")
if not isinstance(content, str):
    raise SystemExit("Missing 'content' field in markdown response.")

out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(content, encoding="utf-8")
print(len(content))
PY
}

build_upload_name() {
  local profile="$1"
  local rel_path="$2"
  python3 - "$profile" "$rel_path" "$RUN_ID" <<'PY'
import hashlib
import pathlib
import re
import sys

profile = sys.argv[1]
rel_path = sys.argv[2]
run_id = sys.argv[3]

p = pathlib.Path(rel_path)
ext = p.suffix or ""
stem = p.stem or "file"
safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "file"
digest = hashlib.sha1(rel_path.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
print(f"{safe_stem}__{profile}__{run_id}__{digest}{ext}")
PY
}

print_file_result() {
  local status="$1"
  local profile="$2"
  local rel_path="$3"
  local extra="$4"

  if [[ "$status" == "ok" ]]; then
    echo "${C_GREEN}[OK]${C_RESET} [${C_BOLD}${profile}${C_RESET}] ${rel_path} ${extra}"
  else
    echo "${C_RED}[FAIL]${C_RESET} [${C_BOLD}${profile}${C_RESET}] ${rel_path} ${extra}"
  fi
}

run_one() {
  local profile="$1"
  local file_path="$2"
  local rel_path="$3"
  local summary_file="$4"

  local upload_resp
  local markdown_resp
  upload_resp="$(mktemp)"
  markdown_resp="$(mktemp)"

  local metadata_json
  metadata_json="$(json_profile_payload "$profile")"
  local upload_name
  upload_name="$(build_upload_name "$profile" "$rel_path")"

  local http_code=""
  local http_code_md=""
  local auth_args=()
  local t_start t_upload_start t_upload_end t_markdown_start t_markdown_end t_end
  local upload_ms=0
  local markdown_ms=0
  local total_ms=0
  t_start="$(now_ms)"
  if [[ -n "$AUTH_BEARER" ]]; then
    auth_args=(-H "Authorization: Bearer ${AUTH_BEARER}")
  fi

  t_upload_start="$(now_ms)"
  if ! http_code="$(curl -sS --max-time "${TIMEOUT_SECONDS}" \
    -w "%{http_code}" \
    -o "${upload_resp}" \
    -X POST "${BASE_URL}/upload-process-documents" \
    "${auth_args[@]}" \
    -F "files=@${file_path};filename=${upload_name}" \
    -F "metadata_json=${metadata_json}")"; then
    t_upload_end="$(now_ms)"
    upload_ms=$(( t_upload_end - t_upload_start ))
    total_ms=$(( t_upload_end - t_start ))
    print_file_result "error" "$profile" "$rel_path" "(upload curl failed)"
    append_summary "${summary_file}" "${profile}" "error" "${rel_path}" "" "0" "" "" "upload_curl" "${upload_ms}" "0" "${total_ms}" "upload curl failed"
    if [[ "$KEEP_RAW" -eq 1 ]]; then
      local raw_path_curl="${OUTPUT_DIR}/_raw/${profile}/${rel_path}.upload.ndjson"
      mkdir -p "$(dirname "$raw_path_curl")"
      cp "${upload_resp}" "${raw_path_curl}" || true
    fi
    rm -f "${upload_resp}" "${markdown_resp}"
    return 1
  fi
  t_upload_end="$(now_ms)"
  upload_ms=$(( t_upload_end - t_upload_start ))

  if [[ ! "$http_code" =~ ^2 ]]; then
    local body
    body="$(cat "${upload_resp}")"
    total_ms=$(( t_upload_end - t_start ))
    print_file_result "error" "$profile" "$rel_path" "(upload HTTP ${http_code})"
    append_summary "${summary_file}" "${profile}" "error" "${rel_path}" "" "0" "${http_code}" "" "upload_http" "${upload_ms}" "0" "${total_ms}" "upload http ${http_code}: ${body}"
    if [[ "$KEEP_RAW" -eq 1 ]]; then
      local raw_path="${OUTPUT_DIR}/_raw/${profile}/${rel_path}.upload.ndjson"
      mkdir -p "$(dirname "$raw_path")"
      cp "${upload_resp}" "${raw_path}"
    fi
    rm -f "${upload_resp}" "${markdown_resp}"
    return 1
  fi

  local parse_line
  if ! parse_line="$(parse_upload_stream "${upload_resp}")"; then
    local parse_err
    parse_err="$(echo "${parse_line}" | awk -F'\t' '{print $3}')"
    t_end="$(now_ms)"
    total_ms=$(( t_end - t_start ))
    print_file_result "error" "$profile" "$rel_path" "(upload stream parse failed)"
    append_summary "${summary_file}" "${profile}" "error" "${rel_path}" "" "0" "${http_code}" "" "upload_stream_parse" "${upload_ms}" "0" "${total_ms}" "${parse_err}"
    if [[ "$KEEP_RAW" -eq 1 ]]; then
      local raw_path2="${OUTPUT_DIR}/_raw/${profile}/${rel_path}.upload.ndjson"
      mkdir -p "$(dirname "$raw_path2")"
      cp "${upload_resp}" "${raw_path2}"
    fi
    rm -f "${upload_resp}" "${markdown_resp}"
    return 1
  fi

  local run_status doc_uid parse_msg
  run_status="$(echo "${parse_line}" | awk -F'\t' '{print $1}')"
  doc_uid="$(echo "${parse_line}" | awk -F'\t' '{print $2}')"
  parse_msg="$(echo "${parse_line}" | awk -F'\t' '{print $3}')"

  if [[ "${run_status}" != "ok" || -z "${doc_uid}" ]]; then
    t_end="$(now_ms)"
    total_ms=$(( t_end - t_start ))
    print_file_result "error" "$profile" "$rel_path" "(${parse_msg})"
    append_summary "${summary_file}" "${profile}" "error" "${rel_path}" "${doc_uid}" "0" "${http_code}" "" "upload_stream_status" "${upload_ms}" "0" "${total_ms}" "${parse_msg}"
    rm -f "${upload_resp}" "${markdown_resp}"
    return 1
  fi

  t_markdown_start="$(now_ms)"
  if ! http_code_md="$(curl -sS --max-time "${TIMEOUT_SECONDS}" \
    -w "%{http_code}" \
    -o "${markdown_resp}" \
    "${auth_args[@]}" \
    "${BASE_URL}/markdown/${doc_uid}")"; then
    t_markdown_end="$(now_ms)"
    markdown_ms=$(( t_markdown_end - t_markdown_start ))
    total_ms=$(( t_markdown_end - t_start ))
    print_file_result "error" "$profile" "$rel_path" "(markdown curl failed)"
    append_summary "${summary_file}" "${profile}" "error" "${rel_path}" "${doc_uid}" "0" "${http_code}" "" "markdown_curl" "${upload_ms}" "${markdown_ms}" "${total_ms}" "markdown curl failed"
    if [[ "$KEEP_RAW" -eq 1 ]]; then
      local raw_path3_curl="${OUTPUT_DIR}/_raw/${profile}/${rel_path}.markdown.json"
      mkdir -p "$(dirname "$raw_path3_curl")"
      cp "${markdown_resp}" "${raw_path3_curl}" || true
    fi
    rm -f "${upload_resp}" "${markdown_resp}"
    return 1
  fi
  t_markdown_end="$(now_ms)"
  markdown_ms=$(( t_markdown_end - t_markdown_start ))

  if [[ ! "$http_code_md" =~ ^2 ]]; then
    local md_body
    md_body="$(cat "${markdown_resp}")"
    total_ms=$(( t_markdown_end - t_start ))
    print_file_result "error" "$profile" "$rel_path" "(markdown HTTP ${http_code_md})"
    append_summary "${summary_file}" "${profile}" "error" "${rel_path}" "${doc_uid}" "0" "${http_code}" "${http_code_md}" "markdown_http" "${upload_ms}" "${markdown_ms}" "${total_ms}" "markdown http ${http_code_md}: ${md_body}"
    if [[ "$KEEP_RAW" -eq 1 ]]; then
      local raw_path3="${OUTPUT_DIR}/_raw/${profile}/${rel_path}.markdown.json"
      mkdir -p "$(dirname "$raw_path3")"
      cp "${markdown_resp}" "${raw_path3}"
    fi
    rm -f "${upload_resp}" "${markdown_resp}"
    return 1
  fi

  local out_file chars
  out_file="${OUTPUT_DIR}/${profile}/${rel_path}.md"
  if ! chars="$(extract_markdown_content "${markdown_resp}" "${out_file}")"; then
    local extract_error
    extract_error="$(cat "${markdown_resp}")"
    t_end="$(now_ms)"
    total_ms=$(( t_end - t_start ))
    print_file_result "error" "$profile" "$rel_path" "(invalid markdown payload)"
    append_summary "${summary_file}" "${profile}" "error" "${rel_path}" "${doc_uid}" "0" "${http_code}" "${http_code_md}" "markdown_extract" "${upload_ms}" "${markdown_ms}" "${total_ms}" "invalid markdown payload: ${extract_error}"
    rm -f "${upload_resp}" "${markdown_resp}"
    return 1
  fi

  if [[ "$KEEP_RAW" -eq 1 ]]; then
    local raw_stream_path raw_md_path
    raw_stream_path="${OUTPUT_DIR}/_raw/${profile}/${rel_path}.upload.ndjson"
    raw_md_path="${OUTPUT_DIR}/_raw/${profile}/${rel_path}.markdown.json"
    mkdir -p "$(dirname "${raw_stream_path}")"
    cp "${upload_resp}" "${raw_stream_path}"
    cp "${markdown_resp}" "${raw_md_path}"
  fi

  t_end="$(now_ms)"
  total_ms=$(( t_end - t_start ))
  print_file_result "ok" "$profile" "$rel_path" "(uid=${doc_uid}, chars=${chars}, total_ms=${total_ms})"
  append_summary "${summary_file}" "${profile}" "ok" "${rel_path}" "${doc_uid}" "${chars}" "${http_code}" "${http_code_md}" "done" "${upload_ms}" "${markdown_ms}" "${total_ms}" ""
  rm -f "${upload_resp}" "${markdown_resp}"
  return 0
}

main() {
  parse_args "$@"

  require_cmd curl
  require_cmd find
  require_cmd python3

  if [[ -z "${INPUT_DIR}" ]]; then
    echo "${C_RED}[ERROR]${C_RESET} --input-dir is required." >&2
    usage
    exit 2
  fi

  if [[ ! -d "${INPUT_DIR}" ]]; then
    echo "${C_RED}[ERROR]${C_RESET} Input directory does not exist: ${INPUT_DIR}" >&2
    exit 2
  fi

  INPUT_DIR="$(cd "${INPUT_DIR}" && pwd)"
  mkdir -p "${OUTPUT_DIR}"
  OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd)"
  local summary_file="${OUTPUT_DIR}/summary.tsv"
  echo -e "run_id\tprofile\tstatus\tfile\tdocument_uid\tchars\tupload_http\tmarkdown_http\tstage\tupload_ms\tmarkdown_ms\ttotal_ms\terror" > "${summary_file}"

  local -a profile_list
  IFS=',' read -r -a profile_list <<< "${PROFILES}"

  local -a normalized_profiles=()
  local p
  for p in "${profile_list[@]}"; do
    p="$(trim "${p,,}")"
    case "$p" in
      fast|medium|rich) normalized_profiles+=("$p") ;;
      *)
        echo "${C_RED}[ERROR]${C_RESET} Unsupported profile: '$p' (allowed: fast, medium, rich)" >&2
        exit 2
        ;;
    esac
  done

  if [[ "${#normalized_profiles[@]}" -eq 0 ]]; then
    echo "${C_RED}[ERROR]${C_RESET} No valid profiles provided." >&2
    exit 2
  fi

  local -a files=()
  while IFS= read -r -d '' f; do
    files+=("$f")
  done < <(
    find "${INPUT_DIR}" -type f \
      \( -iname "*.pdf" -o -iname "*.docx" -o -iname "*.pptx" \) \
      -print0 | sort -z
  )

  if [[ "${#files[@]}" -eq 0 ]]; then
    echo "${C_YELLOW}[WARN]${C_RESET} No .pdf/.docx/.pptx files found under: ${INPUT_DIR}"
    exit 0
  fi

  echo "${C_BLUE}[INFO]${C_RESET} Base URL: ${BASE_URL}"
  echo "${C_BLUE}[INFO]${C_RESET} Input dir: ${INPUT_DIR}"
  echo "${C_BLUE}[INFO]${C_RESET} Output dir: ${OUTPUT_DIR}"
  echo "${C_BLUE}[INFO]${C_RESET} Profiles: ${normalized_profiles[*]}"
  echo "${C_BLUE}[INFO]${C_RESET} Files found: ${#files[@]}"
  echo

  declare -A total_map=()
  declare -A ok_map=()
  declare -A fail_map=()

  local profile file rel_path
  for profile in "${normalized_profiles[@]}"; do
    total_map["$profile"]=0
    ok_map["$profile"]=0
    fail_map["$profile"]=0
    echo "${C_BOLD}=== Profile: ${profile} ===${C_RESET}"
    for file in "${files[@]}"; do
      rel_path="${file#${INPUT_DIR}/}"
      total_map["$profile"]=$(( total_map["$profile"] + 1 ))
      if run_one "$profile" "$file" "$rel_path" "${summary_file}"; then
        ok_map["$profile"]=$(( ok_map["$profile"] + 1 ))
      else
        fail_map["$profile"]=$(( fail_map["$profile"] + 1 ))
      fi
    done
    echo
  done

  echo "${C_BOLD}=== Summary ===${C_RESET}"
  local grand_total=0
  local grand_ok=0
  local grand_fail=0
  for profile in "${normalized_profiles[@]}"; do
    local t o f
    t="${total_map[$profile]}"
    o="${ok_map[$profile]}"
    f="${fail_map[$profile]}"
    grand_total=$(( grand_total + t ))
    grand_ok=$(( grand_ok + o ))
    grand_fail=$(( grand_fail + f ))
    if [[ "$f" -eq 0 ]]; then
      echo "${C_GREEN}[OK]${C_RESET} ${profile}: ${o}/${t} passed"
    else
      echo "${C_RED}[FAIL]${C_RESET} ${profile}: ${o}/${t} passed, ${f} failed"
    fi
  done
  echo "Total: ${grand_ok}/${grand_total} passed, ${grand_fail} failed"
  echo "Markdown outputs: ${OUTPUT_DIR}"
  echo "Summary TSV: ${summary_file}"

  if [[ "${grand_fail}" -gt 0 ]]; then
    exit 1
  fi
}

main "$@"
