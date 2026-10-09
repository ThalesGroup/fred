## Why

Part of #2980 / draft PR #2983. Operators need to cap how much web research one person can use per day, separately for billed searches and for page reads, while keeping the option of no cap.

## What Changes

- Two optional deployment settings: `max_searches_per_user_per_day` and `max_fetches_per_user_per_day`. Unset (default) means no quota.
- The day is the UTC calendar day. Requests are counted from the existing restricted activity table: no new table, migration or service.
- When a quota applies, each result carries the remaining count for today, shown in the trace detail and visible to the model.
- Over the quota, the tool returns `quota_exceeded` before any network access, with a model instruction and a localized label.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-research`: optional per-user daily quotas for searches and page reads.

## Impact

SDK deployment config and error codes, runtime adapter and activity store (one count query), capability error guidance, frontend labels, Helm values and regenerated schemas, operator guide. No API, migration or UI flow change.
