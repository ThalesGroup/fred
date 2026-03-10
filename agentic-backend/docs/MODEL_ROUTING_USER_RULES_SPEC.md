# Model Routing User Rules Spec

This document is a user-facing specification for model routing rules.
It is intentionally simple and example-first.

For technical internals, see:
- [MODEL_ROUTING_PATTERN.md](/home/dimi/run/reference/fred/agentic-backend/docs/MODEL_ROUTING_PATTERN.md)

## Goal

Allow a user to say:
- "For my team, all ReAct agents use model X for routing and model Y for planning."
- "For one Graph operation, use model Z."

without forcing users to configure each agent one by one.

## Core Concepts

- `profile_id`: a named model profile from `models_catalog.yaml`.
- `rule`: maps a context (`match`) to one `target_profile_id`.
- `match`: filtering criteria (`team_id`, `agent_id`, `purpose`, `operation`, etc).

### Crystal-clear model selection dimensions

A rule can filter on 3 different axes. They are close, but not the same:

- `capability`: **what kind of model client is needed**
  - examples: `chat`, `embedding`, `image`, `language`
  - this is technical compatibility (model family)
- `purpose`: **why the model is called (business intent)**
  - examples: `chat`, `analysis`, `classification`
  - this is business intent within one capability
- `operation`: **where in the runtime flow the call happens**
  - examples: `routing`, `planning`, `json_validation_fc`
  - this is phase/node-level routing

No-overlap rule of thumb:
- change `capability` when model *family* changes
- change `purpose` when *intent* changes
- change `operation` when *step/phase* changes

Examples:
- ReAct routing: `capability=chat`, `purpose=chat`, `operation=routing`
- ReAct planning: `capability=chat`, `purpose=chat`, `operation=planning`
- Graph JSON validation (function calling): `capability=chat`, `purpose=chat`, `operation=json_validation_fc`

Important:
- If a `match` field is absent, it means "any value" (wildcard).
- All provided `match` fields are combined with logical AND.
- Recommendation: always set `purpose` explicitly in rules (usually `chat` for chat-model routing), to avoid accidental cross-purpose matches.

### Canonical rule shape (recommended field order)

```yaml
- rule_id: ui.chat.rule.001
  capability: chat
  target_profile_id: chat.ollama.mistral
  match:
    purpose: chat
    team_id: team-a
    agent_id: internal.react_profile.r1
    operation: routing
```

## Reference Scenario

Team `team-a` contains:
- ReAct agent `R1`
- ReAct agent `R2`
- Graph agent `G1`

### Requirement A (team-wide ReAct phases)

For all ReAct agents of `team-a`:
- use `chat.ollama.mistral` for `routing`
- use `default.chat.openai.prod` for `planning`

Rules:

```yaml
rules:
  - rule_id: ui.chat.rule.001
    capability: chat
    target_profile_id: chat.ollama.mistral
    match:
      purpose: chat
      team_id: team-a
      operation: routing

  - rule_id: ui.chat.rule.002
    capability: chat
    target_profile_id: default.chat.openai.prod
    match:
      purpose: chat
      team_id: team-a
      operation: planning
```

Expected behavior:
- `R1` and `R2` match these rules.
- `G1` does not match these phase rules unless it explicitly emits the same operation labels.

### Requirement B (one Graph operation override)

For Graph agent `G1`, on JSON validation with function calling:
- operation label: `json_validation_fc`
- use model profile: `chat.azure_apim.gpt4o`

Rule:

```yaml
rules:
  - rule_id: ui.chat.rule.003
    capability: chat
    target_profile_id: chat.azure_apim.gpt4o
    match:
      purpose: chat
      team_id: team-a
      agent_id: internal.graph.g1
      operation: json_validation_fc
```

Expected behavior:
- Only `G1` on `json_validation_fc` uses `chat.azure_apim.gpt4o`.
- Other operations still use default/rule-based resolution.

## Matching Convention (User View)

Use this mental model:

1. Define model profiles once (`profiles` section).
2. Add team-wide rules first.
3. Add agent-specific rules only when needed.
4. Add operation-specific rules only when needed.

This gives progressive control:
- broad control (team)
- then precise control (agent)
- then phase-level control (operation)

## About `rule_id`

`rule_id` is a technical unique identifier.

Recommendation:
- Keep it stable and simple (`ui.chat.rule.001`, `ui.chat.rule.002`, etc).
- Do not encode business meaning in `rule_id` (team/agent already live in `match`).

## About `priority`

`priority` is not part of the rule format.

Rule resolution is deterministic with:
1. match specificity (more `match` fields wins)
2. declaration order in `rules` (first wins on tie)

## UI Mapping Recommendation

UI can expose only:
- Scope: personal or team
- Team
- Phase (`routing`, `planning`, or custom graph operation)
- Model profile
- Optional: agent selector

UI should hide:
- `target_profile_id` wording (show `model_profile_id` label)

Backend storage can keep canonical schema:
- `target_profile_id`
