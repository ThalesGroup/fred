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
// (CAPAB-01 #1976, RFC §3.3). Extracted from the former bespoke `SearchConfig`
// molecule's library/document picker row. `params.bound_library_ids` (when
// non-null) forces the picker read-only, exactly as the retired
// `EffectiveChatOptions.bound_library_ids` did — the composer keeps sending
// the effective library scope to the pod via
// `buildComposerRuntimeContext`/`RuntimeContext`, not `turn_options`.

import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { DocumentLibraryScopePicker } from "@shared/molecules/DocumentLibraryScopePicker/DocumentLibraryScopePicker";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import { usePickerMenuMaxHeight } from "@shared/molecules/MenuPopover/usePickerMenuMaxHeight";
import type { CapabilityChatTurnControlProps } from "../types";
import styles from "./DocumentScopeControl.module.css";

const PICKER_DESKTOP_MAX_HEIGHT_PX = 640;

export interface DocumentScopeControlParams {
  libraries: boolean;
  documents: boolean;
  bound_library_ids: string[] | null;
}

export function DocumentScopeControl({
  params: rawParams,
  composer,
  open,
  onToggleOpen,
}: CapabilityChatTurnControlProps) {
  const { t } = useTranslation();
  const wrapRef = useRef<HTMLDivElement>(null);
  const style = usePickerMenuMaxHeight(open, wrapRef, PICKER_DESKTOP_MAX_HEIGHT_PX);

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
    <div ref={wrapRef} className={styles.rowWrap}>
      <MenuPopoverItem
        icon={{ category: "outlined", type: "description" }}
        label={title}
        value={label}
        trailingIcon="chevron_right"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={onToggleOpen}
      />

      {open && (
        <div className={styles.pickerMenu} role="dialog" aria-label={title} style={style}>
          <div className={styles.pickerMenuBody}>
            <DocumentLibraryScopePicker
              teamId={composer.teamId}
              selectedTagIds={effectiveLibraryIds}
              onChange={composer.onSelectedLibraryIdsChange}
              selectedDocumentUids={showDocuments ? composer.selectedDocumentUids : undefined}
              onDocumentsChange={showDocuments ? composer.onSelectedDocumentUidsChange : undefined}
              disableLibrarySelection={hasBoundLibraries}
            />
          </div>
        </div>
      )}
    </div>
  );
}
