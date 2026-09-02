// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Local shape of the `html_artifact` chat part emitted by the html_artifact
// runtime middleware (the `render_html_artifact` tool artifact).
//
// The backend `UiPart` union is OPEN (capability packages extend it at pod boot),
// so this build carries a hand-written narrowing type instead of a generated one —
// the same pattern WritableDocumentPartData / PptPreviewPartData use. It narrows
// the RAW part a renderer receives via `as unknown as HtmlArtifactPartData`.

/** Backend capability id (`manifest.id`) — the side-panel open-request key. */
export const CAPABILITY_ID = "html_artifact";

/** One static HTML/CSS artifact snapshot, as carried on an `html_artifact` part. */
export interface HtmlArtifactPartData {
  type: "html_artifact";
  /** Stable id of the artifact (one per artifact in the session; reused on revise). */
  artifact_id: string;
  /** Human title shown on the card, the artifact switcher, and the pane header. */
  title: string;
  /** The HTML markup (a full document or a bare fragment). */
  html: string;
  /** The CSS, kept separate for the CSS tab; composed into the Preview + download. */
  css: string;
  /** Per-content hash: the freshness key that drives the "latest wins" merge and
   *  the Preview remount (a re-render with the same markup keeps the same value). */
  version: string;
}
