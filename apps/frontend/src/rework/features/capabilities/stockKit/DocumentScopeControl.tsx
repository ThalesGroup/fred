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

// Stock chat-turn control for the MCP capability's `document_scope` widget
// (CAPAB-01 #1976, RFC §3.3). The row is now just a launcher: clicking it opens
// the right-side document-scope panel (#2259) and closes the tune popover — the
// picker used to expand inline here as an anchored popover, but a full-height
// side panel gives the resource tree far more room. The panel's open state and
// the actual `DocumentLibraryScopePicker` live at the page level
// (`ManagedChatPage` + `DocumentScopePanel`); this row only computes the
// current-selection summary shown as its value and signals the page to open.
// `params.bound_library_ids` (when non-null) still means the library scope is
// pinned read-only — surfaced by the panel, not here.

import { useTranslation } from "react-i18next";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import type { CapabilityChatTurnControlProps } from "../types";

export interface DocumentScopeControlParams {
  libraries: boolean;
  documents: boolean;
  bound_library_ids: string[] | null;
}

export function DocumentScopeControl({ params: rawParams, composer, onRequestClose }: CapabilityChatTurnControlProps) {
  const { t } = useTranslation();

  // Narrow the generic descriptor params to this widget's shape (mirrors the
  // part-renderer registry's `part as unknown as LinkPart` convention).
  const params = rawParams as unknown as DocumentScopeControlParams;
  const showLibraries = params.libraries === true;
  const showDocuments = params.documents === true;
  if (!showLibraries && !showDocuments) return null;

  const boundLibraryIds = params.bound_library_ids ?? [];
  const hasBoundLibraries = boundLibraryIds.length > 0;
  const effectiveLibraryIds = hasBoundLibraries ? boundLibraryIds : composer.selectedLibraryIds;

  const title = showDocuments
    ? t("chatbot.composerSettings.documentPickerTitle")
    : t("agentTuning.fields.chat_options_libraries_selection.title");

  const label = (() => {
    const { selectedDocumentUids } = composer;
    if (effectiveLibraryIds.length > 0 && selectedDocumentUids.length > 0) {
      return `${t("chatbot.composerSettings.librariesCount", { count: effectiveLibraryIds.length })}, ${t(
        "chatbot.composerSettings.documentsCount",
        { count: selectedDocumentUids.length },
      )}`;
    }
    if (selectedDocumentUids.length > 0) {
      return t("chatbot.composerSettings.documentsCount", { count: selectedDocumentUids.length });
    }
    if (effectiveLibraryIds.length > 0) {
      return t("chatbot.composerSettings.librariesCount", { count: effectiveLibraryIds.length });
    }
    return t("chatbot.composerSettings.noDocumentsSelected");
  })();

  return (
    <MenuPopoverItem
      icon={{ category: "outlined", type: "description" }}
      label={title}
      value={label}
      aria-haspopup="dialog"
      onClick={() => {
        composer.onOpenDocumentScopePanel?.();
        onRequestClose?.();
      }}
    />
  );
}
