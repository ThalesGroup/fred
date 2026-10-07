## 1. SDK

- [x] 1.1 Bind the loaded configuration in the entrypoint and add the cached accessor used outside a worker; verify a test that two `for_run` calls load the configuration once and that a bound configuration is used without loading
- [x] 1.2 Add `DocumentPublisher.for_run(context)` with the named error for a pod without a Knowledge Flow URL; verify tests for the library id and for the error raised before any request
- [x] 1.3 Make `source_tag` optional and omit it when absent; verify tests on the form fields sent with and without it
- [x] 1.4 Export the new error from `fred_sdk.knowledge_base` (not `PodConfiguration`, see D4); verify the full `fred-sdk` suite, including the engine-terms guard, ruff and basedpyright

## 2. Users of the SDK

- [x] 2.1 Use `for_run` in the SDK README and the three `fred-samples` Knowledge Bases and `webdav-knowledge-base`; verify each sample's test suite against the branch SDK
- [x] 2.2 Update both examples of the Knowledge Base blog post, re-run their type check and smoke test, and rebuild the site with drafts
- [x] 2.3 Run `openspec validate simplify-knowledge-base-document-access --strict`
