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

import { useConversationFiles, conversationFileUrl } from "../../conversationFiles";
import { useSelector } from "react-redux";
import { useOpenSessionId } from "../useOpenSessionId";
import { selectCurrentPreview, selectPptPreviewSessionId } from "./pptPreviewSlice";
import type { PptPreviewPartData } from "./types";

export function useSessionPptPreview(): PptPreviewPartData | null {
  const sessionId = useOpenSessionId();
  const current = useSelector(selectCurrentPreview);
  const previewSessionId = useSelector(selectPptPreviewSessionId);
  const catalog = useConversationFiles();
  const selected = sessionId !== "" && previewSessionId === sessionId ? current : null;
  const file =
    catalog.files.find((item) => item.document_id === selected?.preview_id) ??
    catalog.files.find(
      (item) =>
        item.mime === "application/vnd.openxmlformats-officedocument.presentationml.presentation" &&
        item.preview_content_id,
    );
  if (!file?.preview_content_id) return null;
  return {
    type: "ppt_preview",
    preview_id: file.document_id,
    title: file.name,
    file_name: file.name,
    version: file.preview_content_id,
    pdf_download_url: conversationFileUrl(catalog.spaceId, catalog.sessionId, file.document_id, true),
    pptx_download_url: conversationFileUrl(catalog.spaceId, catalog.sessionId, file.document_id),
    capability_id: selected?.capability_id,
    summary: selected?.version === file.preview_content_id ? selected.summary : undefined,
  };
}

/** Launcher visibility for the ppt_filler side panel - see `CapabilitySidePanelSpec`. */
export function useHasPptPreview(): boolean {
  return useSessionPptPreview() !== null;
}
