## 1. Configuration

- [x] 1.1 Add `KnowledgeBasePublisher {client_id, prefix}` and `KnowledgeBasesConfig.publishers` (default empty) with a validator refusing a duplicate or covering prefix; verify unit tests for the default, a valid list, a duplicate and an overlap
- [x] 1.2 Regenerate the Control Plane configuration schema and the fred chart values schema; verify `make check-config-schema-drift` in apps/control-plane-backend and `make check-chart-schema-drift` pass

## 2. Gate

- [x] 2.1 In `publish_definition`, after the service-identity check, refuse an unregistered client and a request prefix other than the registered one, with a message naming the client and `knowledge_bases.publishers`; verify tests for each spec scenario (unlisted, default, outside prefix, claimed prefix differs, registered, person's token)
- [x] 2.2 Verify the existing Knowledge Base tests (`test_knowledge_base_enablement.py` and the publication tests) pass with their publishers registered

## 3. Configurations and docs

- [x] 3.1 List `kb-fred.samples` / `fred.samples` in `config/configuration_prod.yaml` and `deploy/k3d/values.yaml`, and `local-dev` / `fred.samples` in `config/configuration.yaml`; document the setting in the fred chart's `values.yaml`; verify `make check-config-files` and `make check-chart-values`
- [x] 3.2 Update `docs/swift/design/KNOWLEDGE-BASE.md` (§3 prefix ownership, §4 the Publication gate) and the publication row of `authz-endpoint-matrix.yaml`; verify no doc still says the first publication claims a prefix
- [x] 3.3 Add the migration note (`impact: minor`, operations: list the clients before upgrading, review stored definitions) and run `make migration-check`

## 4. Close-out

- [ ] 4.1 Record verification evidence, open the PR linking #3104
