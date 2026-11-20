---
name: fred-repo-map
description: Refresh and verify Fred's local Graphify code graph after source files are added, removed, or renamed, or when imports, modules, or architecture change. Use for repository map maintenance in Fred.
---

# Fred repository map

Run from the Fred repository root, where `scripts/graphify` is available.

- If `graphify-out/graph.json` is absent, build it with the code-only commands in `docs/swift/platform/REPO_MAP.md`.
- After structural code changes, run `scripts/graphify update .`. Graphify regenerates the graph; do not edit `graphify-out/` by hand.
- If `update` refuses a smaller graph after intentional source removal, inspect the warning and changed files before rerunning `scripts/graphify update . --force`.
- Check that a new or changed symbol appears with `scripts/graphify query "<symbol or module>" --budget 500` or `scripts/graphify explain "<symbol>"`.

The local index covers code. Keep architecture documentation current through the repository's normal documentation workflow.
