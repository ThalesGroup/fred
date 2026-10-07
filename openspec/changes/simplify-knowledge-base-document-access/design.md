## Context

See proposal.md. The worker loads `PodConfiguration` once in the entrypoint
(`_load`) and passes it to `serve`; handlers never see it. Knowledge Flow's
`POST /libraries/{id}/documents` declares `source_tag` as an optional form
field defaulting to `"fred"`, its push source.

## Goals / Non-Goals

**Goals:** one line from run context to library client; no behaviour change
for code using the constructor.

**Non-Goals:** changing the run context's wire model; a pod configuration key
for the source tag (no deployment needs one today).

## Decisions

**D1. `DocumentPublisher.for_run(context)`, a classmethod.** It reads only
`context.library_id`, so the library is visible at the call site and cannot be
mistyped. Alternatives rejected: a client inside `KnowledgeBaseRunContext`
(that model is also the Control Plane's API response; a live HTTP client does
not belong on the wire); a second handler parameter (needs signature sniffing
and changes the handler shape everyone knows); a module-level `library()`
(hidden state, the target library invisible when reading the handler).

**D2. The active configuration is bound by the entrypoint, cached otherwise.**
`_load` binds the configuration it already reads; `for_run` uses it. Outside a
worker — a script, a developer tool — the first `for_run` loads it and keeps
it. Same lifetime as the process, which is the configuration's own lifetime.
`MissingPodConfiguration` still surfaces, so samples keep their offline mode.

**D3. `source_tag` is optional and omitted when absent.** The vocabulary
belongs to Knowledge Flow's deployment (`document_sources`), which already
defaults it. Sending nothing hands the decision back to the platform. An
explicit value is still sent, for a deployment that defines another push
source.

**D4. `PodConfiguration` is not exported from the authoring package.** It was
proposed, then refused by an existing guard: the package's public names and
fields carry no workflow-engine term, and the pod configuration holds
`scheduler.temporal`. The guard is right — deployment wiring is not authoring.
`for_run` removes the only reason a handler imported it; a pod extending its
configuration (the WebDAV one adds `webdav:`) imports it from
`fred_sdk.knowledge_base.configuration`, as a deployment concern.

## Risks / Trade-offs

- [Process-wide cache misses a configuration edit] → configuration is a
  ConfigMap mounted at start; a change already means a restart.
- [Tests binding a configuration leak into each other] → a reset helper used
  by the tests' fixture.
