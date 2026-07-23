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

// The writable_document capability's UI plugin (#1905, AGENT-CAPABILITY-RFC §9) —
// one object, registered once in ../index.ts. Mirrors the backend
// `writable_document` capability: the `writable_document` chat part (the card) and
// the collaborative Markdown editor side pane. No config widget, no chat control.

import type { CapabilityUiPlugin } from "../types";
import { WritableDocumentAutoOpenProbe } from "./WritableDocumentAutoOpenProbe";
import { WritableDocumentCardRenderer } from "./WritableDocumentCardRenderer";
import { WritableDocumentPane } from "./WritableDocumentPane";

export const writableDocumentCapability: CapabilityUiPlugin = {
  id: "writable_document",
  // Keyed by the backend chat part's `type` discriminator (#1977).
  partRenderers: { writable_document: WritableDocumentCardRenderer },
  // Keyed by the backend manifest's SidePanelSpec.widget (#1979).
  sidePanels: { writable_document_pane: WritableDocumentPane },
  // A conversation that already holds documents re-opens straight in the editor.
  sessionProbes: [WritableDocumentAutoOpenProbe],
};
