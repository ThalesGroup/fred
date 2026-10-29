## Why

Native Deep skill reads can return only the first 100 lines when the model
omits `limit`. Fred already recommends 1000, but its activity label presents
partial first-page reads as loaded without disclosing the incomplete window.

Tracking: https://github.com/ThalesGroup/fred/issues/3339

## What Changes

- Strengthen `NATIVE_SKILLS_SYSTEM_PROMPT`: explicitly pass `limit=1000` for
  `SKILL.md`, inspect the returned window and continue before applying it.
- Carry a backward-compatible partial-read flag in existing skill-load
  attribution and display "Skill partiellement chargé" / "Skill partially loaded"
  for incomplete native first-page reads, live and after history reload.
- Preserve native DeepAgents loading, pinning, pagination, permissions, reference
  reads and existing successful-read attribution/counting.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-agent-skills`: explicit read guidance and partial-load activity.

## Impact

Runtime skill prompt/read observation, SDK skill-load metadata and generated
runtime OpenAPI types, frontend trace labels and both locales, focused tests,
existing runtime/UX documentation and a migration note. No database, dependency,
Helm configuration or read-limit override changes. Work stays on the requested
`codex/platform-skills-evolution` branch; the local model catalog edit is excluded.
