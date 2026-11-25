#!/usr/bin/env bash
# Local Linux Docker recipe; no Fred service or cluster is changed.
set -euo pipefail
umask 077
image=otel/opentelemetry-collector-contrib:0.165.0@sha256:e40d61f10c9a617cca1ffd1be4d7e2b3a4b0f0001798ff07e58cabe82e618cea
config_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
action=${1:-}
[[ $# -ge 2 && -n $2 ]] || { echo "Usage: $0 start|stop|flush|retrieve TRACE_DIR [COPY_TO]" >&2; exit 2; }
command -v docker >/dev/null
command -v python3 >/dev/null
trace_dir=$(realpath -m -- "$2")
trace_file=$trace_dir/traces.otlp.jsonl
cid_file=$trace_dir/.collector.cid

check_owner() {
  local owner
  owner=$(docker inspect --format '{{ index .Config.Labels "fred.otel.trace-dir" }}' "$(cat "$cid_file")")
  [[ $owner == "$trace_dir" ]] || { echo 'Collector ownership mismatch' >&2; exit 1; }
}

case "$action" in
  start)
    [[ ! -e $trace_file && ! -e $cid_file ]] || { echo 'Use a fresh TRACE_DIR; existing traces are never overwritten.' >&2; exit 1; }
    mkdir -p -m 700 -- "$trace_dir"
    python3 - "$trace_dir" <<'PY'
import os, stat, sys
p = os.stat(sys.argv[1])
if p.st_uid != os.getuid() or stat.S_IMODE(p.st_mode) & 0o077:
    raise SystemExit('TRACE_DIR must belong to you and have mode 0700 (chmod 700 it explicitly).')
PY
    port=${FRED_OTEL_PORT:-4318}
    python3 - "$port" <<'PY'
import socket, sys
port = int(sys.argv[1])
if not 1024 <= port <= 65535:
    raise SystemExit('FRED_OTEL_PORT must be between 1024 and 65535')
with socket.socket() as sock:
    sock.bind(('127.0.0.1', port))
PY
    export FRED_OTEL_LISTEN_ENDPOINT=127.0.0.1:$port
    export FRED_BENCH_TRACE_FILE=/traces/traces.otlp.jsonl
    configs=(--config=/config/otel-collector.yaml)
    envs=(-e FRED_OTEL_LISTEN_ENDPOINT -e FRED_BENCH_TRACE_FILE)
    if [[ -n ${FRED_LANGFUSE_OTLP_ENDPOINT:-} ]]; then
      : "${FRED_LANGFUSE_AUTHORIZATION:?Set the complete Basic authorization header}"
      configs+=(--config=/config/otel-collector-langfuse.yaml)
      envs+=(-e FRED_LANGFUSE_OTLP_ENDPOINT -e FRED_LANGFUSE_AUTHORIZATION)
    fi
    # Validate the exact merged configuration before creating the output.
    docker run --rm --network none -v "$config_dir:/config:ro" "${envs[@]}" "$image" validate "${configs[@]}"
    (set -o noclobber; : > "$trace_file")
    started=false
    cleanup_start() {
      if [[ $started == false && -s $cid_file ]]; then
        docker rm -f "$(cat "$cid_file")" >/dev/null 2>&1 || true
        rm -f -- "$cid_file"
      fi
    }
    trap cleanup_start EXIT
    docker run -d --cidfile "$cid_file" --label "fred.otel.trace-dir=$trace_dir" \
      --network host --user "$(id -u):$(id -g)" --read-only --cap-drop ALL \
      --security-opt no-new-privileges --memory 256m --cpus 1 --pids-limit 128 \
      --log-driver none -v "$config_dir:/config:ro" -v "$trace_dir:/traces:rw" \
      "${envs[@]}" "$image" "${configs[@]}" >/dev/null
    python3 - "$port" <<'PY'
import socket, sys, time
for _ in range(50):
    try:
        with socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=.1):
            break
    except OSError:
        time.sleep(.1)
else:
    raise SystemExit('Collector did not start within 5 seconds')
PY
    [[ $(docker inspect --format '{{.State.Running}}' "$(cat "$cid_file")") == true ]]
    started=true
    echo "Collector ready: http://127.0.0.1:$port/v1/traces -> $trace_file"
    ;;
  stop|flush)
    # There is no receiver API to flush upstream SDKs. Flush those FIRST. A
    # graceful Collector stop drains its batches and closes the file buffer.
    if [[ -f $cid_file ]]; then
      check_owner
      cid=$(cat "$cid_file")
      docker stop --time 15 "$cid" >/dev/null
      code=$(docker inspect --format '{{.State.ExitCode}}' "$cid")
      docker rm "$cid" >/dev/null
      rm -- "$cid_file"
      [[ $code == 0 ]] || { echo "Collector exit $code: complete flush is NOT established" >&2; exit 1; }
    fi
    [[ -f $trace_file ]] || { echo 'No trace file in TRACE_DIR' >&2; exit 1; }
    echo "Collector stopped; file closed: $trace_file"
    ;;
  retrieve)
    [[ ! -e $cid_file ]] || { echo 'Flush/stop before retrieving a complete file' >&2; exit 1; }
    [[ -f $trace_file ]] || { echo 'No trace file in TRACE_DIR' >&2; exit 1; }
    if [[ -n ${3:-} ]]; then
      python3 - "$trace_file" "$3" <<'PY'
import os, shutil, sys
with open(sys.argv[1], 'rb') as source:
    fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as target:
        shutil.copyfileobj(source, target)
PY
      echo "$3"
    else
      echo "$trace_file"
    fi
    ;;
  *) echo "Unknown action: $action" >&2; exit 2 ;;
esac
