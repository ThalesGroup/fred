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

// The ppt_filler capability's UI plugin (#1903, AGENT-CAPABILITY-RFC §9) — one
// object, registered once in ../index.ts. Mirrors the backend `ppt_filler`
// capability: custom agent-creation form widget (template upload + inline
// analyze), the `ppt_preview` chat part, and the PDF preview side pane.

import type { CapabilityUiPlugin } from "../types";
import { PptFillerConfigForm } from "./PptFillerConfigForm";
import { PptPreviewCardRenderer } from "./PptPreviewCardRenderer";
import { PptPreviewPane } from "./PptPreviewPane";

export const pptFillerCapability: CapabilityUiPlugin = {
  id: "ppt_filler",
  // Keyed by the backend chat part's `type` discriminator (#1977).
  partRenderers: { ppt_preview: PptPreviewCardRenderer },
  // Keyed by the backend FieldSpec's `ui.widget` (RFC §9 item 4).
  configWidgets: { ppt_filler_template: PptFillerConfigForm },
  // Keyed by the backend manifest's SidePanelSpec.widget (#1979).
  sidePanels: { ppt_preview_pane: PptPreviewPane },
};
