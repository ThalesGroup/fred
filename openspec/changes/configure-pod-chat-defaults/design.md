## Context

The YAML catalog advertises an effective chat default. The admin platform binding stores a provider/name/settings tuple and takes absolute precedence. Managed turns already obtain a trusted control-plane binding on each turn. See proposal.md for the product motivation.

## Goals / Non-Goals

**Goals:** Persistent default and manual fallback overrides per configured runtime ID, pod-specific admin selectors, and consistent routing in the runtime and composer.

**Non-Goals:** Changing direct template runs, changing the existing global binding, or making a discovered profile the YAML deployment fallback.

## Decisions

1. Store `runtime_id -> (chat_profile_id, fallback_profile_id)` separately from the platform binding. The existing binding has global, absolute-override semantics and cannot naturally hold pod-scoped policy. The original PR revision creates the pod table on fresh installs. Because the same revision ID was already applied in development before the pod table replaced the removed global fallback table, a conditional follow-up Alembic revision repairs already-stamped databases and removes that obsolete table.
2. Validate a new selection against the selected pod's live catalog and the model's current platform-wide activation. Expose enabled configured pods and their YAML default through an admin read endpoint. A missing pod cannot accept a new selection, but saved overrides remain visible for repair. A YAML or saved choice that is no longer activated remains visible as the effective setting without becoming a selectable candidate.
3. Add the saved profile ID to the trusted per-turn managed binding. The runtime uses it only when that profile remains in the pod's current chat catalog. Otherwise it uses the YAML effective default. This preserves user, instance, team and pod-agent override precedence. The composer applies the same rule for its displayed effective model.
4. Show "Agent pods" first, with selectors containing only platform-enabled models per runtime ID; the fallback is also manual-only. The default starts at the effective YAML value, shows a saved override when present, and returns to YAML on reset. Keep the global forced binding in "Platform" as a manual provider/name/settings form. It still wins over all profile choices. Remove the unused global fallback from this fresh feature.

## Risks / Trade-offs

- [A discovered model disappears] -> Use the pod's manual fallback, or its manual YAML default when no fallback override exists; keep the saved default visible to administrators for repair.
- [A pod is temporarily unreachable] -> Show its configured runtime ID with an unavailable state; do not erase its override or infer absence.
- [Older control planes or runtimes coexist briefly] -> The new binding field is optional and defaults to `None`.

## Migration Plan

Add the pod-default table to this PR's original Alembic revision and repair already-stamped interim databases with a conditional follow-up revision. An empty table preserves every deployment's current YAML default and global binding. Rolling back the feature removes admin overrides without changing catalog YAML.
