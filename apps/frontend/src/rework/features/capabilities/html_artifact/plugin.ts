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

import { useHtmlArtifactFiles } from "./useHtmlArtifactFiles";
import type { CapabilityUiPlugin } from "../types";
import { CAPABILITY_ID } from "./types";
import { HtmlArtifactCardRenderer } from "./HtmlArtifactCardRenderer";
import { HtmlArtifactPane } from "./HtmlArtifactPane";
import { useHasHtmlArtifacts } from "./useHasHtmlArtifacts";

export const htmlArtifactCapability: CapabilityUiPlugin = {
  id: CAPABILITY_ID,
  useConversationFiles: useHtmlArtifactFiles,
  // Keyed by the backend chat part's `type` discriminator (#1977).
  partRenderers: { html_artifact: HtmlArtifactCardRenderer },
  partIdentities: { html_artifact: (part) => (typeof part.artifact_id === "string" ? part.artifact_id : undefined) },
  // Keyed by the backend manifest's SidePanelSpec.widget.
  sidePanels: {
    html_artifact_pane: {
      Component: HtmlArtifactPane,
      icon: "web",
      useHasContent: useHasHtmlArtifacts,
      ownsHeader: true,
    },
  },
};
