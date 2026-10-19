## 1. Graceful stop

- [ ] 1.1 Add graceful shutdown to `serve` and the cleanup loop; verify with a test that an in-flight upload completes after SIGTERM and new connections are refused
- [ ] 1.2 Add `terminationGracePeriodSeconds` to the manager deployment in the chart (default transfer deadline + 30 s), regenerate schema; verify `test_manager_chart.py` and `make check-chart-values`

## 2. Role edges

- [ ] 2.1 Validate role subjects before locking on space and platform role routes; verify a malformed subject returns 422 with no tuple or guard change (integration test)
- [ ] 2.2 Emit the revocation audit only for a held role; verify a double revocation yields one `authz.relation.revoked` event and two 204s

## 3. Diagnostics

- [ ] 3.1 Log object-store failure causes server-side with operation and error kind; verify a provider failure test asserts the log fields and the absence of keys/credentials
- [ ] 3.2 Replace `import_setup_error` string matching with typed setup errors; verify the existing CLI import tests and one per error type

## 4. Close-out

- [ ] 4.1 Update arc42 (08 operations, 03 security/matrix) to the current behaviour only, and the migration note for the new chart value; verify `docs.py check` and `make migration-check`
- [ ] 4.2 Independent review, fixes re-reviewed; `make code-quality`, `make test`, `make test-integration` green; archive this change
