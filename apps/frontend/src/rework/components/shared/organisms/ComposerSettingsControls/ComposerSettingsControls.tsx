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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { SettingChip } from "@shared/atoms/SettingChip/SettingChip";
import ButtonGroupItem from "@shared/atoms/ButtonGroup/ButtonGroupItem/ButtonGroupItem";
import Icon from "@shared/atoms/Icon/Icon";
import { useListAllTagsKnowledgeFlowV1TagsGetQuery } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { SearchPolicyName } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { EffectiveChatOptions } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  buildLibrarySelectionKey,
  parseLibrarySelectionKey,
  reconcileSelectedDocumentUids,
  resolveDocumentScopeState,
} from "./documentSelection";
import { useLibraryDocuments } from "./useLibraryDocuments";
import styles from "./ComposerSettingsControls.module.css";

type RagScope = "corpus_only" | "hybrid" | "general_only";
type OpenPopover = "policy" | "scope" | "libraries" | "documents" | null;

interface ComposerSettingsControlsProps {
  teamId: string;
  selectedLibraryIds: string[];
  onLibraryChange: (ids: string[]) => void;
  selectedDocumentUids: string[];
  onDocumentChange: (uids: string[]) => void;
  searchPolicy: SearchPolicyName;
  onSearchPolicyChange: (p: SearchPolicyName) => void;
  ragScope: RagScope;
  onRagScopeChange: (s: RagScope) => void;
  boundLibraryIds?: string[];
  options?: EffectiveChatOptions | null;
  stacked?: boolean;
  onAttach?: () => void;
}

export function ComposerSettingsControls({
  teamId,
  selectedLibraryIds,
  onLibraryChange,
  selectedDocumentUids,
  onDocumentChange,
  searchPolicy,
  onSearchPolicyChange,
  ragScope,
  onRagScopeChange,
  boundLibraryIds = [],
  options = null,
  stacked = false,
  onAttach,
}: ComposerSettingsControlsProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<OpenPopover>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const showLibraries = options?.libraries_selection === true;
  const showDocuments = options?.documents_selection === true;
  const showSearchPolicy = options?.search_policy_selection === true;
  const showRagScope = options?.rag_scope_selection === true;
  const showAttachFiles = options?.attach_files === true && onAttach != null;

  const isBound = boundLibraryIds.length > 0;
  const effectiveLibraryIds = isBound ? boundLibraryIds : selectedLibraryIds;
  const { hasDocumentScope, showSelectLibraryFirst, showDocumentConfigurationWarning } = resolveDocumentScopeState({
    showLibraries,
    showDocuments,
    effectiveLibraryIds,
  });
  const documentLibraryKey = showDocuments && hasDocumentScope ? buildLibrarySelectionKey(effectiveLibraryIds) : "";
  const documentLibraryIds = parseLibrarySelectionKey(documentLibraryKey);

  const { data: allTags = [], isLoading } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "document", ownerFilter: "team", teamId },
    { skip: !showLibraries && !showDocuments },
  );
  const { documents, isLoading: isLoadingDocuments, error: documentsError } = useLibraryDocuments(documentLibraryIds);

  // Labels resolved after t() is available
  const SEARCH_POLICIES: { value: SearchPolicyName; label: string }[] = [
    { value: "strict", label: t("search.strict") },
    { value: "hybrid", label: t("search.hybrid") },
    { value: "semantic", label: t("search.semantic") },
  ];

  const RAG_SCOPES: { value: RagScope; label: string }[] = [
    { value: "corpus_only", label: t("chatbot.composerSettings.scopeCorpus") },
    { value: "hybrid", label: t("chatbot.composerSettings.scopeCorpusAndWeb") },
    { value: "general_only", label: t("chatbot.composerSettings.scopeGeneral") },
  ];

  useEffect(() => {
    if (!open) return;
    const onMouse = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(null);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    document.addEventListener("mousedown", onMouse);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouse);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const toggle = (id: OpenPopover) => setOpen((prev) => (prev === id ? null : id));

  const policyLabel = SEARCH_POLICIES.find((p) => p.value === searchPolicy)?.label ?? searchPolicy;
  const scopeLabel = RAG_SCOPES.find((s) => s.value === ragScope)?.label ?? ragScope;

  const libraryCount = isBound ? boundLibraryIds.length : selectedLibraryIds.length;
  const libraryLabel =
    libraryCount > 0
      ? t("chatbot.composerSettings.librariesCount", { count: libraryCount })
      : t("chatbot.composerSettings.librariesTitle");
  const documentLabel =
    selectedDocumentUids.length > 0
      ? t("chatbot.composerSettings.documentsCount", { count: selectedDocumentUids.length })
      : t("chatbot.composerSettings.documentsTitle");

  useEffect(() => {
    if (effectiveLibraryIds.length === 0 && selectedDocumentUids.length > 0) {
      onDocumentChange([]);
    }
  }, [effectiveLibraryIds, onDocumentChange, selectedDocumentUids]);

  useEffect(() => {
    if (isLoadingDocuments || documentsError || selectedDocumentUids.length === 0) return;
    const nextSelected = reconcileSelectedDocumentUids(
      selectedDocumentUids,
      documents.map((document) => document.identity.document_uid),
    );
    if (nextSelected.length !== selectedDocumentUids.length) {
      onDocumentChange(nextSelected);
    }
  }, [documents, documentsError, isLoadingDocuments, onDocumentChange, selectedDocumentUids]);

  const handleLibraryToggle = (id: string, checked: boolean) => {
    if (checked) {
      onLibraryChange([...selectedLibraryIds, id]);
    } else {
      onLibraryChange(selectedLibraryIds.filter((lid) => lid !== id));
    }
  };

  const handleDocumentToggle = (uid: string, checked: boolean) => {
    if (checked) {
      onDocumentChange([...selectedDocumentUids, uid]);
    } else {
      onDocumentChange(selectedDocumentUids.filter((selectedUid) => selectedUid !== uid));
    }
  };

  return (
    <div className={styles.controls} data-stacked={stacked} ref={wrapperRef}>
      {showSearchPolicy && (
        <div className={styles.chipSlot}>
          <SettingChip
            label={policyLabel}
            open={open === "policy"}
            onClick={() => toggle("policy")}
            aria-label={`${t("chatbot.composerSettings.searchPolicyTitle")}: ${policyLabel}`}
          />
          {open === "policy" && (
            <div className={styles.popover} role="dialog" aria-label={t("chatbot.composerSettings.searchPolicyTitle")}>
              <p className={styles.popoverLabel}>{t("chatbot.composerSettings.searchPolicyTitle")}</p>
              <div className={styles.pillGroup} role="group">
                {SEARCH_POLICIES.map((opt) => (
                  <ButtonGroupItem
                    key={opt.value}
                    label={opt.label}
                    size="xs"
                    color="secondary"
                    selected={searchPolicy === opt.value}
                    onClick={() => {
                      onSearchPolicyChange(opt.value);
                      setOpen(null);
                    }}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {showRagScope && (
        <div className={styles.chipSlot}>
          <SettingChip
            label={scopeLabel}
            open={open === "scope"}
            onClick={() => toggle("scope")}
            aria-label={`${t("chatbot.composerSettings.scopeTitle")}: ${scopeLabel}`}
          />
          {open === "scope" && (
            <div className={styles.popover} role="dialog" aria-label={t("chatbot.composerSettings.scopeTitle")}>
              <p className={styles.popoverLabel}>{t("chatbot.composerSettings.scopeTitle")}</p>
              <div className={styles.pillGroup} role="group">
                {RAG_SCOPES.map((opt) => (
                  <ButtonGroupItem
                    key={opt.value}
                    label={opt.label}
                    size="xs"
                    color="secondary"
                    selected={ragScope === opt.value}
                    onClick={() => {
                      onRagScopeChange(opt.value);
                      setOpen(null);
                    }}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {showLibraries && (
        <div className={styles.chipSlot}>
          <SettingChip
            label={libraryLabel}
            open={open === "libraries"}
            icon={isBound ? { category: "outlined", type: "lock" } : undefined}
            onClick={() => toggle("libraries")}
            aria-label={
              isBound
                ? `${t("chatbot.composerSettings.boundLibrariesTitle")}: ${libraryLabel}`
                : `${t("chatbot.composerSettings.librariesTitle")}: ${libraryLabel}`
            }
          />
          {open === "libraries" && !isBound && (
            <div className={styles.popover} role="dialog" aria-label={t("chatbot.composerSettings.librariesTitle")}>
              <p className={styles.popoverLabel}>{t("chatbot.composerSettings.librariesTitle")}</p>
              {isLoading && <p className={styles.popoverNote}>{t("chatbot.composerSettings.loading")}</p>}
              {!isLoading && allTags.length === 0 && (
                <p className={styles.popoverNote}>{t("chatbot.composerSettings.noLibrariesAvailable")}</p>
              )}
              {!isLoading && allTags.length > 0 && (
                <ul className={styles.libraryList}>
                  {allTags.map((tag) => {
                    const checked = selectedLibraryIds.includes(tag.id);
                    return (
                      <li key={tag.id} className={styles.libraryItem}>
                        <label className={styles.libraryLabel}>
                          <input
                            type="checkbox"
                            className={styles.libraryCheckbox}
                            checked={checked}
                            onChange={(e) => handleLibraryToggle(tag.id, e.target.checked)}
                          />
                          <span className={styles.libraryName}>{tag.name}</span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
          {open === "libraries" && isBound && (
            <div
              className={styles.popover}
              role="dialog"
              aria-label={t("chatbot.composerSettings.boundLibrariesTitle")}
            >
              <p className={styles.popoverLabel}>{t("chatbot.composerSettings.boundLibrariesTitle")}</p>
              <ul className={styles.libraryList}>
                {allTags
                  .filter((tag) => boundLibraryIds.includes(tag.id))
                  .map((tag) => (
                    <li key={tag.id} className={styles.libraryItem}>
                      <span className={styles.libraryBoundIcon}>
                        <Icon category="outlined" type="lock" />
                      </span>
                      <span className={styles.libraryName}>{tag.name}</span>
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {showDocuments && (
        <div className={styles.chipSlot}>
          <SettingChip
            label={documentLabel}
            open={open === "documents"}
            onClick={() => toggle("documents")}
            aria-label={`${t("chatbot.composerSettings.documentsTitle")}: ${documentLabel}`}
          />
          {open === "documents" && (
            <div className={styles.popover} role="dialog" aria-label={t("chatbot.composerSettings.documentsTitle")}>
              <p className={styles.popoverLabel}>{t("chatbot.composerSettings.documentsTitle")}</p>
              {showDocumentConfigurationWarning && (
                <p className={styles.popoverNote}>{t("chatbot.composerSettings.documentsNoScope")}</p>
              )}
              {showSelectLibraryFirst && (
                <p className={styles.popoverNote}>{t("chatbot.composerSettings.selectLibraryFirst")}</p>
              )}
              {hasDocumentScope && isLoadingDocuments && (
                <p className={styles.popoverNote}>{t("chatbot.composerSettings.loadingDocuments")}</p>
              )}
              {hasDocumentScope && !isLoadingDocuments && documentsError && (
                <p className={styles.popoverNote}>{t("chatbot.composerSettings.documentsLoadError")}</p>
              )}
              {hasDocumentScope && !isLoadingDocuments && !documentsError && documents.length === 0 && (
                <p className={styles.popoverNote}>{t("chatbot.composerSettings.noDocumentsAvailable")}</p>
              )}
              {hasDocumentScope && !isLoadingDocuments && !documentsError && documents.length > 0 && (
                <ul className={styles.libraryList}>
                  {documents.map((document) => {
                    const documentUid = document.identity.document_uid;
                    const checked = selectedDocumentUids.includes(documentUid);
                    const label = document.identity.title || document.identity.document_name;
                    return (
                      <li key={documentUid} className={styles.libraryItem}>
                        <label className={styles.libraryLabel}>
                          <input
                            type="checkbox"
                            className={styles.libraryCheckbox}
                            checked={checked}
                            onChange={(e) => handleDocumentToggle(documentUid, e.target.checked)}
                          />
                          <span className={styles.libraryName}>{label}</span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {showAttachFiles && (
        <div className={styles.chipSlot}>
          <SettingChip
            label={t("chatbot.composerSettings.attachFile")}
            onClick={onAttach}
            aria-label={t("chatbot.composerSettings.attachFile")}
          />
        </div>
      )}
    </div>
  );
}
