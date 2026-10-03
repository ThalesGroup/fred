## Context

`Check docker images` deliberately has no path filter: an image can break from outside its own directory, the missing-COPY of a local library being the case that reached a release. Selection therefore happens inside the reusable workflow, from the full PR diff, not through a workflow `paths` filter.

## Goals / Non-Goals

**Goals:**
- Skip images a change cannot reach in the three frequent cases: documentation, frontend, and the expensive knowledge-flow image.
- Keep the missing-COPY protection and complete release builds.

**Non-Goals:**
- Narrow the frontend, control-plane, fred-agents or ws-bench images beyond the documentation and frontend rules.
- Narrow the knowledge-flow Dockerfile's `COPY scripts`.
- Reuse a previous run's verification across pushes.

## Decisions

- **Static rules, guarded by tests.** Rules and the knowledge-flow `pr_inputs` live in `docker-images.json`. Tests check that every knowledge-flow `COPY` source and every transitive `[tool.uv.sources]` path dependency is covered, so the static list cannot silently drift.
- **The list protects itself.** A new local dependency is declared in a `pyproject.toml` already listed (knowledge-flow, fred-core or fred-pod), so that change rebuilds the image and a missing `COPY` still fails.
- **First matching rule wins per path; the result is the union over paths.** A path no rule claims builds every image except one whose `pr_inputs` it misses. Unknown paths thus fall back to the general case.
- **Baseline is the merge base** (`base...head`, `--no-renames`). Each push re-checks the whole PR against its target, so no unverified commit is ever a baseline; renames count on both sides. The buildx gha cache keeps an unchanged image cheap, which is why cross-push reuse is not worth its state.
- **Full build fallback:** release (`publish=true`), any non-PR run (`workflow_dispatch` on the check), or a failed diff.
