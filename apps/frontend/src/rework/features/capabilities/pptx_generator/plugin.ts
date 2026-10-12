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

// pptx_generator UI plugin, registered in ../index.ts: the `pptx_generated` chat
// part, the PDF preview side pane, and the optional brand-template upload widget.

import type { CapabilityUiPlugin } from "../types";
import { PptxGeneratedCardRenderer } from "./PptxGeneratedCardRenderer";
import { PptxGeneratorConfigForm } from "./PptxGeneratorConfigForm";
import { PptxPreviewPane } from "./PptxPreviewPane";
import { useHasPptxPreview } from "./useSessionPptxPreview";

export const pptxGeneratorCapability: CapabilityUiPlugin = {
  id: "pptx_generator",
  // Keyed by the backend chat part's `type`; distinct from ppt_filler's
  // `ppt_preview` to avoid a chat-part registry collision.
  partRenderers: { pptx_generated: PptxGeneratedCardRenderer },
  // Keyed by the backend manifest's `template_key` FieldSpec's `ui.widget`
  // (capability.py). Unlike ppt_filler's mandatory template, there is no
  // analyze/preview step — just the upload control.
  configWidgets: { pptx_generator_template: PptxGeneratorConfigForm },
  // Keyed by the backend manifest's SidePanelSpec.widget. `co_present`, distinct
  // from ppt_filler's `slideshow` icon.
  sidePanels: {
    pptx_preview_pane: {
      Component: PptxPreviewPane,
      icon: "co_present",
      useHasContent: useHasPptxPreview,
      ownsHeader: true,
    },
  },
};
