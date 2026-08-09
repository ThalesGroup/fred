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

// Right-side push panel housing the document-scope picker (#2259). Replaces the
// former inline popover the `document_scope` tune-menu row used to expand: the
// tree now takes a full-height panel instead of a cramped anchored popover.
// Mounted at the ManagedChatPage level as a sibling of the main column so its
// `InlineDrawer layout="push"` reflows the conversation left, sharing the page's
// single-open push-drawer slot with the attachments / capability panels.

import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer";
import { DocumentLibraryScopePicker } from "@shared/molecules/DocumentLibraryScopePicker/DocumentLibraryScopePicker";
import styles from "./DocumentScopePanel.module.css";

interface DocumentScopePanelProps {
  open: boolean;
  onClose: () => void;
  teamId: string;
  showLibraries: boolean;
  showDocuments: boolean;
  /** Non-empty when the agent binds specific libraries at creation — the library
   * tree is then read-only and pinned to this set (reset returns here). */
  boundLibraryIds: string[];
  selectedLibraryIds: string[];
  onSelectedLibraryIdsChange: (ids: string[]) => void;
  selectedDocumentUids: string[];
  onSelectedDocumentUidsChange: (uids: string[]) => void;
  /** Reverts the per-turn selection to the agent's configured scope. */
  onReset: () => void;
  /** False when the current selection already equals the agent's scope (nothing to reset). */
  canReset: boolean;
}

export function DocumentScopePanel({
  open,
  onClose,
  teamId,
  showLibraries,
  showDocuments,
  boundLibraryIds,
  selectedLibraryIds,
  onSelectedLibraryIdsChange,
  selectedDocumentUids,
  onSelectedDocumentUidsChange,
  onReset,
  canReset,
}: DocumentScopePanelProps) {
  const { t } = useTranslation();

  const hasBound = boundLibraryIds.length > 0;
  // Bound scope wins the library display and can't be edited, exactly like the
  // former DocumentScopeControl row (`effectiveLibraryIds` + disable).
  const effectiveLibraryIds = hasBound ? boundLibraryIds : selectedLibraryIds;

  return (
    <InlineDrawer
      open={open}
      onClose={onClose}
      title={t("chatbot.documentScopePanel.title")}
      layout="push"
      floating
      flushBody
      resizable={{ persistKey: "document-scope-panel" }}
      headerActions={
        <Tooltip text={t("chatbot.documentScopePanel.resetTooltip")}>
          <IconButton
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "refresh" }}
            aria-label={t("chatbot.documentScopePanel.resetTooltip")}
            disabled={!canReset}
            onClick={onReset}
          />
        </Tooltip>
      }
    >
      <div className={styles.body}>
        {/* Mount the picker only while open so its tag/document queries don't
            fire for every chat that merely exposes the control. The InlineDrawer
            shell still animates; the body is briefly empty during the close
            transition, which is imperceptible. */}
        {open && (
          <DocumentLibraryScopePicker
            teamId={teamId}
            selectedTagIds={effectiveLibraryIds}
            onChange={onSelectedLibraryIdsChange}
            selectedDocumentUids={showDocuments ? selectedDocumentUids : undefined}
            onDocumentsChange={showDocuments ? onSelectedDocumentUidsChange : undefined}
            disableLibrarySelection={hasBound || !showLibraries}
          />
        )}
      </div>
    </InlineDrawer>
  );
}
