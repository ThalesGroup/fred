## 1. Daily quotas

- [x] 1.1 Add `max_searches_per_user_per_day` and `max_fetches_per_user_per_day` (optional, `None` = no quota) and the `quota_exceeded` error code; regenerate config schemas and Helm values.
- [x] 1.2 Count the user's rows for the operation since UTC midnight in the activity store and refuse over the limit before dispatch.
- [x] 1.3 Return `daily_quota` (`limit`, `remaining`) in results when the operation has a cap and show it in the trace detail.
- [x] 1.4 Add the model instruction and the en/fr labels; document the settings in the operator guide.
- [x] 1.5 Tests: limit reached refuses the next request without dispatch, the other operation is unaffected, no limit means no refusal, refused rows do not count.

## Evidence

2026-10-08: runtime web-research suites 62 passed (quota reached refuses before dispatch, the other operation and another user unaffected, refused rows not counted, remaining count 1 then 0; no cap never refuses and carries no quota); capability 6 and control-plane preset tests pass; frontend trace tests 33 passed (remaining quota shown only when capped). `make code-quality` passes on fred-sdk, fred-runtime (5 pre-existing warnings), the capability, fred-agents and the frontend; `make check-config-files` and `helm lint` pass after schema regeneration. Not exercised in the live UI.
