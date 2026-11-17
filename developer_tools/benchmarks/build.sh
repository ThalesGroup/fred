#!/bin/sh
# Build inside this checkout only. No installation, connection or deployment.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
GOTOOLCHAIN="${GOTOOLCHAIN:-go1.24.0}" go build -o bench .
printf 'Built: %s/bench\nStart here: ./bench\n' "$PWD"
