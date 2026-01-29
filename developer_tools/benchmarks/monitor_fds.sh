#!/usr/bin/env bash
# Monitor FDs, sockets, and per-port socket counts for the agentic uvicorn process.
# Auto-detects PID of uvicorn agentic_backend.main:create_app.

INTERVAL=${INTERVAL:-1}
SERVER_PORT=${SERVER_PORT:-8000}

if [ -n "$1" ]; then
  PID="$1"
else
  PATTERN="uvicorn agentic_backend.main:create_app"
  PID=$(ps -eo pid,args | grep "$PATTERN" | grep -v grep | awk 'NR==1{print $1}')
fi

if [ -z "$PID" ]; then
  echo "PID not found. Pass PID as arg or ensure process matches pattern." >&2
  exit 1
fi

echo "Monitoring PID=$PID (interval ${INTERVAL}s, server_port=$SERVER_PORT)"

while true; do
  now=$(date +%H:%M:%S)
  if [ ! -d "/proc/$PID" ]; then
    echo "$now PID $PID exited"
    exit 0
  fi
  fd_total=$(ls /proc/$PID/fd 2>/dev/null | wc -l)
  fd_sock=$(ls -l /proc/$PID/fd 2>/dev/null | grep socket | wc -l)

  # Count inbound vs outbound sockets (any state) by comparing local port to SERVER_PORT.
  read in_s out_s <<<$(netstat -tnp 2>/dev/null | awk -v pid="$PID" -v sport="$SERVER_PORT" '
    $7 ~ (pid "/") && $1 ~ /^tcp/ && $6 == "ESTABLISHED" {
      n = split($4, a, ":"); lport = a[n];
      if (lport == sport) incnt++;
      else outcnt++;
    }
    END { printf "%d %d", incnt+0, outcnt+0 }
  ')

  # State summary (all states) for this PID.
  states=$(netstat -tanp 2>/dev/null | awk -v pid="$PID" '
    $7 ~ (pid "/") && $1 ~ /^tcp/ { s[$6]++ }
    END {
      first=1;
      for (st in s) {
        if (!first) printf " ";
        printf "%s:%d", st, s[st];
        first=0;
      }
    }
  ')

  echo "$now fds=$fd_total sockets=$fd_sock in=$in_s out=$out_s states=[$states]"
  sleep "$INTERVAL"
done
