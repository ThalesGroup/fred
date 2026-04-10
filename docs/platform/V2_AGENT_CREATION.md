# V2 Agent Creation

When creating a v2 agent — whether via the API or as a static catalog entry — there are exactly **two choices**.

---

## Choice 1 — React profile (configurable, user-editable)

Use this when the agent's behaviour should be tunable by the user via the UI: system prompt, tools, chat options.

The agent is backed by `BasicReActDefinition`. A `profile_id` seeds it with a pre-built starting configuration (role, prompt, tools). Omitting `profile_id` creates a blank assistant.

**API (POST `/agents/create`)**:
```json
{
  "name": "My IT Assistant",
  "profile_id": "custodian"
}
```

**Static catalog (`agents_catalog.yaml`)**:
```yaml
- id: "Custodian"
  name: "Custodian"
  type: "agent"
  definition_ref: "v2.react.basic"
  tuning:
    react_profile_id: "custodian"
```

Available profiles are listed by `GET /agents/react-profiles`.

---

## Choice 2 — Definition ref (fixed-behaviour, operator-controlled)

Use this when the agent's behaviour is wired in code and should not be user-editable. The operator deploys it by stable ref; the ref maps to a concrete `AgentDefinition` subclass.

**API (POST `/agents/create`)**:
```json
{
  "name": "Spot",
  "definition_ref": "v2.react.prometheus_expert"
}
```

**Static catalog (`agents_catalog.yaml`)**:
```yaml
- id: "Spot"
  name: "Spot"
  type: "agent"
  definition_ref: "v2.react.prometheus_expert"
```

All known refs live in `agentic_backend/agents/v2/definition_refs.py`. To add one, register the ref → class path there.

---

## Decision guide

| I want to… | Use |
|---|---|
| Let users customise the agent prompt and tools | React profile (`profile_id`) |
| Ship a fixed specialist agent (Prometheus, RAG expert…) | Definition ref (`definition_ref`) |
| Seed a user-editable agent with sensible defaults | React profile with `profile_id` |

---

## What `class_path` is

`class_path` is the **v1 field** for `AgentFlow`-based agents (Rico, Archie, Tessa…). It is still stored on the `Agent` model for backward compatibility with v1 agents already in the database, but it is **not accepted** by the v2 create endpoint. New agents must use `definition_ref` or `profile_id`.
