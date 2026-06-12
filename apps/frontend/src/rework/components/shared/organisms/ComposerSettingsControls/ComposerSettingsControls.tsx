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
import styles from "./ComposerSettingsControls.module.css";

type RagScope = "corpus_only" | "hybrid" | "general_only";
type OpenPopover = "policy" | "scope" | "libraries" | null;

interface ComposerSettingsControlsProps {
  teamId: string;
  selectedLibraryIds: string[];
  onLibraryChange: (ids: string[]) => void;
  searchPolicy: SearchPolicyName;
  onSearchPolicyChange: (p: SearchPolicyName) => void;
  ragScope: RagScope;
  onRagScopeChange: (s: RagScope) => void;
  boundLibraryIds?: string[];
  options?: EffectiveChatOptions | null;
  stacked?: boolean;
}

export function ComposerSettingsControls({
  teamId,
  selectedLibraryIds,
  onLibraryChange,
  searchPolicy,
  onSearchPolicyChange,
  ragScope,
  onRagScopeChange,
  boundLibraryIds = [],
  options = null,
  stacked = false,
}: ComposerSettingsControlsProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<OpenPopover>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const showLibraries = options?.libraries_selection === true;
  const showSearchPolicy = options?.search_policy_selection === true;
  const showRagScope = options?.rag_scope_selection === true;

  const isBound = boundLibraryIds.length > 0;

  const { data: allTags = [], isLoading } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "document", ownerFilter: "team", teamId },
    { skip: !showLibraries },
  );

  // Labels resolved after t() is available
  const SEARCH_POLICIES: { value: SearchPolicyName; label: string }[] = [
    { value: "strict", label: t("search.strict") },
    { value: "hybrid", label: t("search.hybrid") },
    { value: "semantic", label: t("search.semantic") },
  ];

  const RAG_SCOPES: { value: RagScope; label: string }[] = [
    { value: "corpus_only", label: t("chatbot.composerSettings.scopeCorpus", "Corpus") },
    { value: "hybrid", label: t("chatbot.composerSettings.scopeCorpusAndWeb", "Corpus + web") },
    { value: "general_only", label: t("chatbot.composerSettings.scopeGeneral", "General") },
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

  const handleLibraryToggle = (id: string, checked: boolean) => {
    if (checked) {
      onLibraryChange([...selectedLibraryIds, id]);
    } else {
      onLibraryChange(selectedLibraryIds.filter((lid) => lid !== id));
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
    </div>
  );
}
