# Preserved Swift contract

`knowledgeFlowOpenApi.ts` is the **unaltered generated file** recovered from
`0be3b3669^:apps/frontend/src/slices/knowledgeFlow/knowledgeFlowOpenApi.ts`.
Do not edit it manually. The canonical Weaver generator still writes to
`../knowledgeFlow/knowledgeFlowOpenApi.ts` (v2). Its drift check stays authoritative.

The separate reducer `legacyKnowledgeFlowApi` permits preserved Swift callers to
compile without pretending these routes exist in Weaver. Its transport refuses
every request in the regular app. Only the isolated development preview store,
started in `swift-preview` mode, can use the explicit fixtures.

When merging Swift, preserve caller locations and redirect their old imports to
this directory. Refresh this snapshot only from a regenerated Swift client when
its contract actually changes. Do not expand it with handmade types to satisfy a
Weaver feature. Port each caller to the actual owning backend's generated client,
then remove that feature's fixture and update the porting catalog.
