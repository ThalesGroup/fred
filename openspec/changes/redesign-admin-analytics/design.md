## Decisions

1. **One preset per tab section**, each returning the current and the previous
   period, so the page makes a few reads per tab and the export reuses the
   same functions. Presets the page no longer reads are deleted.
2. **`team_ids` replaces `team_id`.** Observers (`can_observe_platform`) may
   pass any non-personal teams; anyone else needs `can_read_analytics`
   (`team_admin` only) on every listed team. A preset whose data has no team
   answers 400 to a team scope; platform-only fields are `null` there.
3. **No `platform_admin_only`.** Observers see every tab, Technical included.
4. **Calendar buckets** `hour|day|week|month` in the request `tz` (default
   `Europe/Paris`); a bucket too fine for the period is coarsened.
5. **Visitor** = human `api.request_latency_ms`; **active user** =
   `agent.turn_completed`. **New user** = first-ever event in the period;
   cohorts and next-month return reuse it.
6. **People with access** = users the access rule admits plus the whitelist
   (all known users when access is not restricted); for a team, its current
   members. Cached 10 min per pod.
7. **Euros**: `usd_per_eur` (default 1.12) next to the model prices in
   `model_impact_factors.yaml`; prices stay in USD.
8. **Export** rendered server-side with openpyxl; fr/en texts in one Python
   module, a test keeps them aligned with the i18n keys.
9. **Rolling periods**: "3 months" and "12 months" start the same day and
   time 3 or 12 months earlier.
10. **Capability usage** aggregates `dims.capability_id` on tool KPIs; calls
    without it are not counted.
11. **Web research** is hidden everywhere when the capability is enabled
    nowhere.
12. **User filter** is a stateless `user_filter` JSON query parameter
    (at most 2 000 characters, 8 conditions, access-rule operators), observers
    only, resolved once per request (60 s pod cache), refused above 50 000
    matching users. No minimum group size (owner decision).
13. **No indicator without a data source** (no satisfaction card).

## Risks / Trade-offs

- New-user and cohort reads aggregate over all users: paged by 1 000, checked
  locally with 5 000 users.
- A narrow user filter can show one person's activity; only observers can set it.
