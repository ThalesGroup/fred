## Context

Every dispatched request already writes one row (`user_id`, `operation`, `created_at`, `error_code`) in `runtime_web_research_activity` before any network access.

## Decisions

1. **Count the activity rows.** After the request's own row is inserted, count the user's rows for that operation since UTC midnight, excluding rows refused by the quota. More than the limit refuses the request. Inserting before counting means concurrent requests can never exceed the limit; at worst a concurrent burst is refused slightly early.
2. **Refusals stay visible.** The refused request is recorded as failed with `quota_exceeded`, so it appears in the activity log, the Prometheus failure counter and the admin Analytics reasons, without counting against the quota.
3. **Two independent, optional limits.** `max_searches_per_user_per_day` (billed) and `max_fetches_per_user_per_day`, each `None` by default. No per-team or per-role override.
4. **Remaining quota in the result.** The count is already known, so a result carries `daily_quota` (`limit`, `remaining`) when its operation has a cap. The trace detail shows it and the model can save its searches. No endpoint or permanent UI counter.
5. **UTC calendar day.** Simple to explain ("try again tomorrow"); the reset time is midnight UTC.

## Risks / Trade-offs

- Erasing a user's activity also resets their quota for the day.
- Rows count whatever their outcome: a blocked or failed request consumes quota, since it was dispatched.
