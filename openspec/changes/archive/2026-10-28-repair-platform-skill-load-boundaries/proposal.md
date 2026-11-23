## Why

The complete skills acceptance review reproduced duplicate load accounting during
native context recovery and an eligibility bypass through capability filesystem
aliases. These break the already approved invocation and truthful-load contracts.
The UI replay also exposed a composer history crash when a selected skill was
disabled before sending, and an agent-only skill's loaded instructions could
not be previewed.

## What Changes

- Observe one native pin once across retries of the same model request.
- Check resolved skill targets as well as requested paths in capability reads.
- Keep composer history identities aligned with edited or restored documents,
  and permit authorized previews of agent-only skills without making them
  selectable by users.
- Reproduce both failures before fixing them and rerun the full skills acceptance
  matrix, including the UI, traces and independent review.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `platform-agent-skills`: clarify retry accounting and resolved-target
  eligibility scenarios under the existing requirements.

## Impact

Runtime native skill policy and preview resolution, the Deep conversation
filesystem port, composer history and focused regression tests. No API schema,
database, model configuration or dependency
changes. The user's existing approval of these contracts and request to iterate
until acceptance authorize these corrections. The body and method of grill-me
remain unchanged.
