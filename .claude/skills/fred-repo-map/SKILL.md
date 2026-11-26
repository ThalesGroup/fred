---
name: fred-repo-map
description: Refresh and verify Fred's committed Graphify code graph when source symbols, calls, imports, modules, or architecture change.
---

# Fred repository map

Run from the Fred repository root, where `scripts/graphify` is available.

- If `graphify-out/graph.json` is absent, build it with the code-only commands in `docs/swift/platform/REPO_MAP.md`.
- After code changes that affect symbols or relationships, run `scripts/graphify update .` and stage `graphify-out/graph.json` with the source change. Graphify regenerates the graph; do not edit it by hand.
- If `update` refuses a smaller graph after intentional source removal, inspect the warning and changed files before rerunning `scripts/graphify update . --force`.
- Check that a new or changed symbol appears with `scripts/graphify query "<symbol or module>" --budget 500` or `scripts/graphify explain "<symbol>"`.

The local index covers code. Keep architecture documentation current through the repository's normal documentation workflow.
