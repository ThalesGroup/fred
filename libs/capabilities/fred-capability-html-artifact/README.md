# fred-capability-html-artifact

A Fred agent capability (`html_artifact`) that lets an agent produce a **static
HTML/CSS artifact** rendered live in a **sandboxed viewer beside the chat** —
the "artifact" experience, scoped to static markup (no JavaScript) for v1.

Design: `docs/swift/rfc/HTML-ARTIFACT-CAPABILITY-RFC.md` (issue #2478).

## What it ships

- **Tool** `render_html_artifact(title, html, css, artifact_id?)` — HTML and CSS
  kept separate (for the viewer's tabs). Combined size is capped at 256 KB.
- **Chat part** `HtmlArtifactPart` (`type="html_artifact"`) carrying the markup
  **inline** — no owned table, no router, no migration (v1 is read-only; chat
  `ui_parts` persist across reload).
- **Prompt fragment** steering the model to call the tool (static only) instead of
  pasting code into the chat.
- **Side panel** `html_artifact_pane` (frontend): read-only tabs **Preview**
  (sandboxed `<iframe srcdoc>`) / **HTML** / **CSS** + download.

`execution_models=("react",)`: the prompt overlay is a `wrap_model_call` hook, so
the tool is carried by the capability's middleware (mirrors `writable_document`).

## Registration

Installing this package IS the registration — the `fred.capabilities` entry point
in `pyproject.toml` points the fred-agents pod at `HtmlArtifactCapability`. It is
wired into the pod as an editable path dependency of `apps/fred-agents`.

## Security

The markup is untrusted LLM output; the backend carries only inert strings. Safe
rendering is a frontend concern (RFC §4.7): the Preview iframe uses `sandbox`
**without** `allow-scripts`/`allow-same-origin` and a restrictive CSP, so no
script runs and no network egress is possible.

## Dev

```
make code-quality   # ruff + format + type-check
make test           # offline unit tests
```
