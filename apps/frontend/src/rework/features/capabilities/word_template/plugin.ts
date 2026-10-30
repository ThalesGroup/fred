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

// The word_template capability's UI plugin - one object, registered once in
// ../index.ts. Mirrors the backend manifest: the `word_template_library`
// config widget and the `word_template_pane` side panel (editor + PDF preview
// + .docx download), plus `onChatAttachment` to keep the .docx files attached
// in the chat (the agent may build the document on one; their pictures are
// extracted server-side) and the images attached in the chat (the agent may
// place them). No chat part, no chat control.

import { lazy } from "react";
import type { CapabilityUiPlugin } from "../types";
import { captureWordAttachment, forgetWordAttachment } from "./sessionAttachments";
import { captureImageAttachment, forgetImageAttachment, isPlaceableImage } from "./sessionImages";
import { useHasWordTemplateDocument } from "./useWordTemplatePreview";
import { WordTemplateLibraryForm } from "./WordTemplateLibraryForm";

// Split out: the pane pulls MDXEditor, the lexical graph and react-pdf, none of
// which belong in the chunk every chat page loads. The host renders panels
// inside a Suspense boundary.
const WordTemplatePane = lazy(async () => ({
  default: (await import("./WordTemplatePane")).WordTemplatePane,
}));

export const wordTemplateCapability: CapabilityUiPlugin = {
  id: "word_template",
  // Keyed by the backend FieldSpec's `ui.widget`.
  configWidgets: { word_template_library: WordTemplateLibraryForm },
  // Keyed by the backend manifest's SidePanelSpec.widget. The launcher shows
  // once the open conversation has a document; the pane renders its own title
  // band and close button.
  sidePanels: {
    word_template_pane: {
      Component: WordTemplatePane,
      icon: "description",
      useHasContent: useHasWordTemplateDocument,
      ownsHeader: true,
    },
  },
  // Each .docx and each PNG/JPEG/GIF attached in the chat is copied to the
  // capability, and forgotten when the user removes it from the chat.
  onChatAttachment: async (file, context) => {
    if (isPlaceableImage(file)) {
      const image = await captureImageAttachment(file, context);
      return image ? () => forgetImageAttachment(context, image.image_id) : undefined;
    }
    const kept = await captureWordAttachment(file, context);
    return kept ? () => forgetWordAttachment(context, kept.attachment_id) : undefined;
  },
};
