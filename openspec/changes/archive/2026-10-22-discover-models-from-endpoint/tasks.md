## 1. Discovery and routing

- [x] 1.1 Extend `ModelCatalog` with the optional OpenAI-compatible source, discovery-only defaults and static compatibility; verify focused catalog validation tests.
- [x] 1.2 Implement bounded authenticated `GET /models` discovery, response validation, optional id filtering and deterministic profile/capability identities; verify mocked HTTP cases for valid, empty, duplicate, malformed, timeout and credential-safe errors.
- [x] 1.3 Resolve the combined catalog once for the discovery pod at startup and serve the same inventory from `/agents/models-catalog`; verify startup and projection tests, including no new model advertised before restart and unchanged static catalog behavior.

## 2. Admin projection

- [x] 2.1 Carry optional display name, context window and input/output limits from the pod response through control-plane model capability and enablement schemas; verify aggregation and absent-metadata tests.
- [x] 2.2 Regenerate frontend API types and show optional metadata in the existing admin Models table; verify focused component tests for full and id-only responses, and confirm existing activation controls still work.
- [x] 2.3 Verify an ungranted discovered model is denied, an admin grant allows use, and a removed model follows the existing drift error without fallback; use focused runtime/control-plane integration tests.

## 3. Documentation and close-out

- [x] 3.1 Document endpoint shape, chat-only source requirement, credentials, default selection, refresh on pod restart and metadata limits in the operator guide, Helm values example and affected runtime/product contracts; verify examples against schema validation.
- [x] 3.2 Run relevant module checks and one root `make code-quality` near PR completion; record exact results in the PR.
- [x] 3.3 Review the full diff against `swift` with the branch audit procedure and an independent read-only reviewer; record findings and dispositions in the draft PR.
- [x] 3.4 Reconcile the change artifacts with the implementation, sync the model-routing spec and archive the change after verification; verify `openspec validate --strict` passes.
