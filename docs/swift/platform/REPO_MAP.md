# Local code graph

Graphify indexes source symbols and their relationships locally. The pinned `graphifyy` CLI runs through `uvx`, so `uv` is the only prerequisite. `graphify-out/graph.json` is committed with the source and is available in each checkout. The report, HTML view, caches and other generated files stay local. `.graphifyignore` excludes tests from this source map to keep the committed file manageable. The first CLI run downloads the package.

Query a specific module or symbol before opening source files:

```sh
scripts/graphify query "RuntimeServices" --budget 500
scripts/graphify explain "RuntimeServices"
scripts/graphify path "RuntimeServices" "AgentRuntime" --undirected
```

After source changes that affect symbols, calls, imports or module structure, refresh and stage the graph with the source change:

```sh
scripts/graphify update .
git add graphify-out/graph.json
```

If an intentional deletion makes Graphify reject the smaller graph, inspect the warning and rerun with `scripts/graphify update . --force`. Do not edit the JSON by hand. If the graph is missing or cannot be read, rebuild it from the repository root without an API key:

```sh
scripts/graphify extract . --code-only --no-cluster --max-workers 4
scripts/graphify cluster-only . --no-label
```

The `.gitattributes` entry uses Graphify's merge driver for concurrent graph changes. Register the driver once in each clone:

```sh
git config merge.graphify.name "Graphify graph merge"
git config merge.graphify.driver 'scripts/graphify merge-driver %O %A %B'
```

Without this local setting, a graph merge may conflict; rebuild the graph from source after resolving the code merge and stage it. Open the locally generated `graphify-out/graph.html` for a visual overview. Read the cited source before editing or relying on a relationship: graph results can be ambiguous, and broad queries may be truncated. The graph covers code only; use the required platform docs for architecture and runtime placement.

Graphify also provides a [general Codex skill](https://github.com/Graphify-Labs/graphify#install). Fred includes a smaller project skill at `.agents/skills/fred-repo-map/` for the code-only refresh workflow above. The general skill covers additional content types and is optional here.
