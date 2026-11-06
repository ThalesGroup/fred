#!/usr/bin/env bash
set -euo pipefail

# Devcontainer initialization renders the exact Node pin before Docker resolves FROM.
script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
node_version=$(cat "$script_dir/../../.nvmrc")
if [[ ! "$node_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo ".nvmrc must contain an exact Node version" >&2
  exit 1
fi
mkdir -p "$HOME/.fred" "$script_dir/../target"
sed "s/^ARG NODE_VERSION$/ARG NODE_VERSION=$node_version/" \
  "$script_dir/../Dockerfile-devcontainer" > "$script_dir/../target/Dockerfile-devcontainer"
