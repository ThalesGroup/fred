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

import { useTranslation } from "react-i18next";
import ButtonGroupItem from "@shared/atoms/ButtonGroup/ButtonGroupItem/ButtonGroupItem";
import Icon from "@shared/atoms/Icon/Icon";
import { useListAllTagsKnowledgeFlowV1TagsGetQuery } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { SearchPolicyName } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { EffectiveChatOptions } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AgentOptionsPanel.module.css";

type RagScope = "corpus_only" | "hybrid" | "general_only";

interface AgentOptionsPanelProps {
  teamId: string;
  selectedLibraryIds: string[];
  onLibraryChange: (ids: string[]) => void;
  searchPolicy: SearchPolicyName;
  onSearchPolicyChange: (p: SearchPolicyName) => void;
  ragScope: RagScope;
  onRagScopeChange: (s: RagScope) => void;
  // When non-empty the agent is hard-bound to these library IDs — picker is read-only.
  boundLibraryIds?: string[];
  /** Resolved from ExecutionPreparation. Null = not yet received; show all sections as safe default. */
  options?: EffectiveChatOptions | null;
}

const SEARCH_POLICIES: { value: SearchPolicyName; label: string }[] = [
  { value: "strict", label: "Strict" },
  { value: "hybrid", label: "Hybrid" },
  { value: "semantic", label: "Semantic" },
];

const RAG_SCOPES: { value: RagScope; label: string }[] = [
  { value: "corpus_only", label: "Corpus" },
  { value: "hybrid", label: "Hybrid" },
  { value: "general_only", label: "General" },
];

export function AgentOptionsPanel({
  teamId,
  selectedLibraryIds,
  onLibraryChange,
  searchPolicy,
  onSearchPolicyChange,
  ragScope,
  onRagScopeChange,
  boundLibraryIds = [],
  options = null,
}: AgentOptionsPanelProps) {
  const { t } = useTranslation();

  // When options is null (not yet received) show everything as a safe default.
  const showLibraries = options == null || options.libraries_selection !== false;
  const showSearchPolicy = options == null || options.search_policy_selection !== false;
  const showRagScope = options == null || options.rag_scope_selection !== false;
  const showSearchSection = showSearchPolicy || showRagScope;

  const { data: allTags = [], isLoading } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "document", ownerFilter: "team", teamId },
    { skip: !showLibraries },
  );

  const isBound = boundLibraryIds.length > 0;

  const handleLibraryToggle = (id: string, checked: boolean) => {
    if (checked) {
      onLibraryChange([...selectedLibraryIds, id]);
    } else {
      onLibraryChange(selectedLibraryIds.filter((lid) => lid !== id));
    }
  };

  const selectedCount = isBound ? boundLibraryIds.length : selectedLibraryIds.length;
  const librarySectionLabel =
    selectedCount > 0
      ? `${t("chat.options.libraries", "Libraries")} (${selectedCount})`
      : t("chat.options.libraries", "Libraries");

  return (
    <div className={styles.panel}>
      {/* ── Libraries ── */}
      {showLibraries && (
        <section className={styles.section}>
          <h3 className={styles.sectionLabel}>{librarySectionLabel}</h3>

          {isLoading && <p className={styles.emptyNote}>{t("chat.options.loadingLibraries", "Loading…")}</p>}

          {!isLoading && allTags.length === 0 && (
            <p className={styles.emptyNote}>{t("chat.options.noLibraries", "No document libraries available.")}</p>
          )}

          {!isLoading && allTags.length > 0 && isBound && (
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
          )}

          {!isLoading && allTags.length > 0 && !isBound && (
            <ul className={styles.libraryList}>
              {allTags.map((tag) => {
                const checked = selectedLibraryIds.includes(tag.id);
                return (
                  <li key={tag.id} className={styles.libraryItem}>
                    <label className={styles.libraryCheckboxLabel}>
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
        </section>
      )}

      {showLibraries && showSearchSection && <div className={styles.divider} />}

      {/* ── Search options ── */}
      {showSearchSection && (
        <section className={styles.section}>
          <h3 className={styles.sectionLabel}>{t("chat.options.search", "Search options")}</h3>

          {showSearchPolicy && (
            <div className={styles.optionRow}>
              <span className={styles.optionRowLabel}>{t("chat.options.policy", "Policy")}</span>
              <div className={styles.pillGroup}>
                {SEARCH_POLICIES.map((opt) => (
                  <ButtonGroupItem
                    key={opt.value}
                    label={opt.label}
                    size="xs"
                    color="secondary"
                    selected={searchPolicy === opt.value}
                    onClick={() => onSearchPolicyChange(opt.value)}
                  />
                ))}
              </div>
            </div>
          )}

          {showRagScope && (
            <div className={styles.optionRow}>
              <span className={styles.optionRowLabel}>{t("chat.options.scope", "Scope")}</span>
              <div className={styles.pillGroup}>
                {RAG_SCOPES.map((opt) => (
                  <ButtonGroupItem
                    key={opt.value}
                    label={opt.label}
                    size="xs"
                    color="secondary"
                    selected={ragScope === opt.value}
                    onClick={() => onRagScopeChange(opt.value)}
                  />
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
