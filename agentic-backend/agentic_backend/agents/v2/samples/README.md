# v2 Samples

Runnable starting points for new agent authors.

New here? Start with [`../AUTHORING.md`](../AUTHORING.md).

---

## Current samples

- [`tutorial_tools/agent.py`](tutorial_tools/agent.py)
  — minimal ReAct agent with custom Python tools (math, slugify, UTC time).
  Not registered in the catalog. Safe to copy and modify.

---

## Promotion path (sample → production)

1. Copy into `v2/candidate/<agent_name>/`.
2. Move the inline prompt to a `.md` file under `prompts/`.
3. Split tools into a `tools/` module if they grow large.
4. Add tests.
5. Move to `v2/production/<agent_name>/` when stable.
6. Register in `definition_refs.py` only when ready for catalog use.
