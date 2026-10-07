## Why

Every Knowledge Base writes the same plumbing before it can touch its library:
import `PodConfiguration` from a submodule the package does not export, reload
the YAML on every run, repeat the run's `library_id`, and hard-code
`source_tag="fred"` — a Knowledge Flow deployment value an author can neither
choose nor know. All three samples carry their own copy of it. During a run
the SDK already holds every one of these values.

## What Changes

- `DocumentPublisher.for_run(context)` returns a publisher bound to the run's
  library, built from the configuration the pod already loaded. Outside a
  worker it loads the configuration once and reuses it.
- A pod with no `knowledge_base.knowledge_flow_url` (one that keeps its own
  store) gets a named error from `for_run` instead of calls to an empty URL.
- `source_tag` becomes optional on `DocumentPublisher`. When omitted, the SDK
  does not send it and Knowledge Flow applies its own default document source,
  so the platform keeps the decision.
- `PodConfiguration` stays out of the authoring package: it carries the
  workflow engine's deployment keys, which that package deliberately never
  exposes. With `for_run` a handler no longer needs it; a pod that extends its
  configuration keeps importing it from `fred_sdk.knowledge_base.configuration`.
- `FieldSpec`, `UIHints` and `TuningValue` are re-exported from
  `fred_sdk.knowledge_base`, so a Knowledge Base needs one package; the shared
  `fred_sdk.contracts.models` path keeps working.
- The constructor keeps working unchanged; nothing breaks.
- Samples, the SDK README and the Knowledge Base blog post use `for_run`.

## Capabilities

### New Capabilities
- `knowledge-base-document-access`: how a Knowledge Base handler obtains a
  client for its run's library, and which values it must not have to supply.

### Modified Capabilities
<!-- none -->

## Impact

- `libs/fred-sdk/fred_sdk/knowledge_base/` — `documents.py`, `configuration.py`,
  `entrypoints.py`, `__init__.py` (the new error); tests.
- `libs/fred-sdk/README.md`; `fred-samples/knowledge-bases/*`,
  `webdav-knowledge-base`, and the `fred-website` Knowledge Base post.
- Knowledge Flow is unchanged: it already defaults `source_tag` server-side.
