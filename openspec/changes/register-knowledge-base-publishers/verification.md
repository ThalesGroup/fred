## Evidence (2026-10-14)

Proven offline, from `apps/control-plane-backend` unless stated:

- `uv run pytest tests/test_knowledge_base_enablement.py tests/test_knowledge_base_instances.py tests/test_knowledge_base_publication_identity.py tests/test_runtime_catalog_source_config.py tests/test_main.py tests/test_cli.py -q`: 307 passed.
- `uv run pytest tests/test_authz_endpoint_matrix.py -q`: 1 passed (publication row edited).
- `uv run ruff check` and `uv run ruff format --check` on `config/models.py`, `knowledge_bases/service.py`, `tests/test_knowledge_base_enablement.py`: clean. `uv run basedpyright` on the same files: 0 errors.
- `make generate-config-schema`, then `make check-config-schema-drift`: passed. Root `make check-chart-schema-drift`: passed.
- `make check-config-files`: the four `config/*.yaml` valid. Root `make check-chart-values`: valid. The `knowledge_bases` sections of `configuration.yaml` and `configuration_prod.yaml` also load through `KnowledgeBasesConfig` (validator included).
- Root `make k3d-tests`: 6 passed. `deploy/k3d/values.yaml` validated alone against the chart schema gives the same 24 errors before and after the change (it is a partial overlay); none concerns `knowledge_bases`.
- Root `make migration-check`: valid. `openspec validate register-knowledge-base-publishers --strict`: valid.

Spec scenarios, all in `tests/test_knowledge_base_enablement.py`:

| Scenario | Test |
| --- | --- |
| Unlisted client | `test_an_unlisted_client_is_refused_and_told_what_to_change` (message names client and setting, nothing stored) |
| Default configuration | `test_by_default_nobody_may_publish` |
| Declaration outside the prefix | `test_a_publisher_cannot_declare_outside_its_prefix` |
| Claimed prefix differs | `test_a_publisher_must_claim_exactly_its_registered_prefix` (a parent and a child of the registered prefix) |
| Registered publisher | `test_a_registered_publisher_is_stored_but_usable_by_no_team` |
| Overlapping prefixes | `test_overlapping_registrations_are_refused_naming_both` (overlap, duplicate for two clients, duplicate for one); `test_publishers_may_hold_neighbouring_prefixes_and_several_each` |
| Person's token for a listed client | `test_a_user_session_cannot_publish` (its `azp` is now listed) |

Existing publication tests register their publishers. The two store-binding tests
(`test_another_client_cannot_take_over_a_definition`,
`test_a_provider_namespace_belongs_to_one_client`) now list the prefix for the
second client, so they still prove the store refuses a prefix moved in
configuration.

Not proven:

- Root `make test` and `make code-quality` were not run.
- No HTTP-level test through the route; the 403 mapping is the existing
  `map_error` on `KnowledgeBaseClientMismatch`.
- The samples' client id `kb-fred.samples` is taken from the spec; not checked
  against the fred-samples deployment.
- No live publication on k3d or a deployment, and no upgrade or rollback rehearsal.

## Review follow-up

- A registered prefix now carries the publication request's own constraints (`PREFIX_PATTERN`,
  at most 256 characters), so a registration publication would refuse fails at configuration
  validation, in the Control Plane and in the chart's values schema.
  `test_a_prefix_publication_would_refuse_is_refused_at_startup` (`Fred Samples`,
  `fred..samples`, 257 characters): `tests/test_knowledge_base_enablement.py` 38 passed; schema
  drift, config files and chart values checks pass after regeneration.
