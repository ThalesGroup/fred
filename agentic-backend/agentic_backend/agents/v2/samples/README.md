# v2 Samples

This folder is for **authoring samples**.

Use it when you want a clean starting point for a new business agent, without
mixing with:

- `demos/`: runtime or product demonstrations
- `candidate/`: exploratory agents that may evolve into production agents
- `production/`: agents currently intended for real usage

## Current sample

- `tutorial_tools/agent.py`
  - minimal ReAct definition
  - tiny Python tools (add numbers, slugify text, utc timestamp)
  - no default registration in `definition_refs.py`

## Promotion path (sample -> real agent)

1. Copy sample into `v2/candidate/<agent_name>/`.
2. Move prompt to markdown resources.
3. Split tools into `tools/` modules.
4. Add tests.
5. Promote to `v2/production/<agent_name>/` when stabilized.
6. Register stable `definition_ref` only when ready for catalog usage.
