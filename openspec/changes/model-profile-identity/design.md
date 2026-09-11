## Context

A model's identity in Fred is `model_capability_id(provider, name)` (fred-sdk). It
is the OpenFGA object id for `can_use`, the key of the platform reasoning toggle,
and the id of a `/agents/models-catalog` entry. `name` is simultaneously the wire
`model` value (`ChatOpenAI(model=cfg.name)` in fred-core), which is what forces the
two apart on gateways that reuse one wire name across several models.

## Goals / Non-Goals

**Goals**

- Let one catalog declare two identities over one wire name.
- Derive that identity in exactly one place, so the catalog projection, the
  `can_use` gate and the reasoning toggle can never disagree.

**Non-goals**

- Changing `model_capability_id` itself, or the id's shape.
- Any control-plane, OpenAPI or frontend change.
- Adopting the field in the shipped `apps/fred-agents` catalog.

## Decisions

### D1 — An optional field on the profile, not a new keying rule

`model_id` defaults to `None` and falls back to `model.name`, so every existing
catalog keeps its ids and every existing enablement decision stays valid. The
alternative — keying on `(provider, name, base_url)` — would silently renumber
every model behind a gateway on upgrade, and would make the id depend on a setting
that ops legitimately change.

### D2 — One derivation, on the profile

`ModelProfile.capability_id` is the single expression of "which model is this".
The projection uses it for the entry id and for its grouping key; the resolver
copies it onto `ModelSelection`. `build_for_chat` reads that field rather than
recomputing, which is what made the bug reachable in two independent places.

Grouping on the derived id, not on the raw `(provider, model_id or name)` pair,
matters: `model_capability_id` normalizes non-id-safe characters, so two raw
spellings can land on one id. Keying on the raw pair would emit two entries with
the same id, which control-plane's by-id union would then merge anyway — the
original bug, in a harder-to-diagnose shape.

### D3 — The platform binding keeps the old derivation

An operator binding names a provider/model directly and has no profile behind it.
Its selection carries `model_capability_id(provider, name)` — the same derivation
control-plane already applies to it, so the two ends stay consistent.

### D4 — The composer label needs no control-plane change

`resolve_effective_chat_model` finds the catalog entry whose
`model_chat_profile_ids` contains the winning profile, then reads the label,
`enabled_for_team` and `reasoning_enabled` off that entry. Once the pod stops
merging the two profiles, that lookup is already correct. Covered by a test that
pins the decision rather than a code change.

The id alone does not fix the LABEL, though: the composer prefers
`model_display_name` and falls back to the wire `name`, which the siblings share.
A profile declaring `model_id` must declare `model_display_name` too — an
authoring rule, documented in `LLM_ROUTING_FRED.md`, not a code change.

## Risks / Trade-offs

- Adopting the field renumbers those models, dropping their stored enablement and
  reasoning state. Accepted and documented as an upgrade note; scoping it to an
  opt-in field is what keeps it from happening to anyone who does nothing.
- Two profiles could declare the same `model_id` with different `model.name`s,
  merging models that differ on the wire. That is an authoring choice with the same
  shape as today's merge, and no worse.

## Migration Plan

No data or schema migration. The field is additive and optional; rollback is a
plain revert, which restores the merge for any catalog that had adopted it.

## Open Questions

None.
