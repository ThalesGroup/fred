# Local code graph

Graphify indexes source symbols and their relationships locally. The pinned `graphifyy` CLI runs through `uvx`, so `uv` is the only prerequisite. The first run downloads the package. Generated files stay in `graphify-out/` and are ignored by Git.

From the repository root, build a code-only graph without an API key:

```sh
scripts/graphify extract . --code-only --no-cluster --max-workers 4
scripts/graphify cluster-only . --no-label
```

Query a specific module or symbol before opening source files:

```sh
scripts/graphify query "RuntimeServices" --budget 500
scripts/graphify explain "RuntimeServices"
scripts/graphify path "RuntimeServices" "AgentRuntime" --undirected
```

Open `graphify-out/graph.html` for a visual overview. After adding, removing, or renaming source files, or changing imports or module structure, run `scripts/graphify update .`. If an intentional deletion makes Graphify reject the smaller graph, inspect the warning and rerun with `scripts/graphify update . --force`. Do not edit generated graph files directly.

Read the cited source before editing or relying on a relationship: graph results can be ambiguous, and broad queries may be truncated. The graph covers code only; use the required platform docs for architecture and runtime placement.

Graphify also provides a [general Codex skill](https://github.com/Graphify-Labs/graphify#install). Fred includes a smaller project skill at `.agents/skills/fred-repo-map/` for the code-only refresh workflow above. The general skill covers additional content types and is optional here.
