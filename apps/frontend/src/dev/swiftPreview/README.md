# Swift UI preview during the Weaver migration

From `apps/frontend`, run `make swift-preview`, then open
<http://localhost:5174/swift-preview.html>. The regular development UI exposes
links under **Portage Weaver** (`/weaver/features`). This is a separate Vite
server, not a backend or a deployment mode. It has no backend proxy. The root
HTML is not a production build entry; its bootstrap refuses other modes.

The original Swift components stay at their original paths to keep upcoming
Swift merges manageable. The gallery mounts them with an independent Redux
store and a fixed fictional team. Production routes show the pending feature
notice and never mount these original screens. Existing manager documents,
imports, folder management and processing keep their Control Plane path.

Before any UI/API module loads, this window replaces `fetch` with an explicit
fixture dispatcher. Unknown URLs/methods return 501 and never fall through to
HTTP. The HTML CSP also blocks XHR, EventSource, WebSocket, frames and forms.
No real sign-in or backend configuration is loaded. Reload resets fixture state.
The separate origin isolates local storage and Redux caches from the regular UI.

## Current preview coverage

| Screen             | Available now                                                    | Next small increment                                          |
| ------------------ | ---------------------------------------------------------------- | ------------------------------------------------------------- |
| Corpus audit       | Anomaly table and simulated repair with confirmation             | Read actual anomalies, then separately authorize repair       |
| Global activity    | Pending/running/failed/succeeded tasks and acknowledgement       | Map scoped Weaver operations, then cancellation               |
| Knowledge Bases    | One source, instance cards, configuration form                   | Actual source catalog, then save/configuration                |
| KB documents       | Read-only fictional library                                      | Bind the instance to a Control Plane folder                   |
| Documents          | Folder browsing, failed/ready rows, rename and labels            | Port each action independently, then ZIP/replacement/rollups  |
| Diagnostics        | Original families and controls                                   | One real scenario at a time; execution is not simulated       |
| Platform migration | Fictional counters and original import/export controls           | Define scope; import/export/reset are not simulated           |
| Dictation          | Original composer, local microphone, constant fake transcription | Actual transcription contract; audio is never sent in preview |

Unmodelled actions visibly fail; a preview is not an end-to-end acceptance test.
This is deliberately a small fixture set, not a second backend. Expand fixtures
only for the journey being revisited. Do not weaken real permissions or replace
backend responses with fixtures in the normal application.

## A porting lot

1. Revisit one journey and its error states in this gallery.
2. Identify its actual Weaver route and generated types; resolve absent backend
   semantics explicitly before adding new frontend abstractions.
3. Switch that caller to the real slice, preserving the screen and permission
   gates. For shared document components, retain the Swift branch for previews
   until its associated journey has been ported.
4. Validate scope, success, failure, refresh and cancellation where relevant.
   The developer runs tests and accepts the real journey from the normal UI.
5. Replace the pending route with the actual screen, remove its fixture/catalog
   entry and record the lot in the migration note. No blanket “ported” flag.
