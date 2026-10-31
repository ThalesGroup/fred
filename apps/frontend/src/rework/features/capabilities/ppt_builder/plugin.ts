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

import type { CapabilityUiPlugin } from "../types";
import { PptPreviewPane } from "../ppt_filler/PptPreviewPane";
import { useHasPptPreview } from "../ppt_filler/useSessionPptPreview";
import { PptBuilderConfigForm } from "./PptBuilderConfigForm";
import { PptBuilderPlatformPanel } from "./PptBuilderPlatformPanel";

export const pptBuilderCapability: CapabilityUiPlugin = {
  id: "ppt_builder",
  // The deck arrives as ppt_filler's `ppt_preview` part, drawn by that plugin. The
  // same pane is declared here for when this one is active alone (offered once).
  configWidgets: { ppt_builder_template: PptBuilderConfigForm },
  // The platform default template, set in Admin > Features.
  platformPanel: PptBuilderPlatformPanel,
  sidePanels: {
    ppt_preview_pane: {
      Component: PptPreviewPane,
      icon: "slideshow",
      useHasContent: useHasPptPreview,
      ownsHeader: true,
    },
  },
};
