#!/bin/bash

# Stop all subprocesses when the script receives Ctrl+C
trap "echo 'Stopping...'; kill 0" SIGINT

# agentic backend
(cd agentic-backend && make run 2>&1 | sed "s/^/[AGENTIC] /") &

# knowledge-flow backend
(cd knowledge-flow-backend && make run 2>&1 | sed "s/^/[KF] /") &

# frontend
(cd frontend && make run 2>&1 | sed "s/^/[FRONTEND] /") &

# wait for all background jobs
wait
