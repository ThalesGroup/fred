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

// The html_artifact capability's UI plugin (#2478, AGENT-CAPABILITY-RFC §9) — one
// object, registered once in ../index.ts. Mirrors the backend `html_artifact`
// capability: the `html_artifact` chat part (the card) and the read-only tabbed
// viewer side pane (Preview / HTML / CSS). No config widget, no chat control.
// No sessionProbe in v1: the card auto-opens live renders; a replayed conversation
// offers the pane through the launcher (useHasContent) instead of auto-opening.

import type { CapabilityUiPlugin } from "../types";
import { CAPABILITY_ID } from "./types";
import { HtmlArtifactCardRenderer } from "./HtmlArtifactCardRenderer";
import { HtmlArtifactPane } from "./HtmlArtifactPane";
import { useHasHtmlArtifacts } from "./useHasHtmlArtifacts";

export const htmlArtifactCapability: CapabilityUiPlugin = {
  id: CAPABILITY_ID,
  // Keyed by the backend chat part's `type` discriminator (#1977).
  partRenderers: { html_artifact: HtmlArtifactCardRenderer },
  // Keyed by the backend manifest's SidePanelSpec.widget. `code` is the glyph the
  // whole html_artifact surface uses — card, Open button, pane header, launcher.
  sidePanels: {
    html_artifact_pane: {
      Component: HtmlArtifactPane,
      icon: "code",
      useHasContent: useHasHtmlArtifacts,
      ownsHeader: true,
    },
  },
};
