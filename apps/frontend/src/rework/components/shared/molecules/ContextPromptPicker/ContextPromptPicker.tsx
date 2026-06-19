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

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import type { ContextPromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { PROMPT_CATEGORY_MAP } from "../../../../config/promptCategories";
import styles from "./ContextPromptPicker.module.css";

type Scope = ContextPromptSummary["scope"];

interface ContextPromptPickerProps {
  prompts: ContextPromptSummary[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}

const SCOPE_ORDER: Scope[] = ["personal", "team", "default"];

/**
 * Pure full-set toggle: remove an already-selected id, otherwise append it at the
 * end. Selection order is preserved (it drives `position` and concatenation order).
 * Exported for unit testing the selection logic without a DOM.
 */
export function nextContextPromptSelection(selectedIds: string[], id: string): string[] {
  return selectedIds.includes(id) ? selectedIds.filter((existing) => existing !== id) : [...selectedIds, id];
}

function ScoreStars({ score }: { score: number }) {
  const filled = Math.max(0, Math.min(5, Math.round(score)));
  return (
    <span className={styles.stars} aria-hidden>
      {Array.from({ length: 5 }, (_, i) => (
        <Icon key={i} category="outlined" type="star" filled={i < filled} />
      ))}
    </span>
  );
}

/**
 * Multi-select picker for chat-context prompts, grouped by scope
 * (personal / team / default) with a session-count-ordered list per group
 * (RFC Part 3 §19). Selection is a full ordered set; toggling appends on add and
 * drops on remove, preserving order.
 */
export function ContextPromptPicker({ prompts, selectedIds, onChange }: ContextPromptPickerProps) {
  const { t } = useTranslation();
  const selected = useMemo(() => new Set(selectedIds), [selectedIds]);

  const groups = useMemo(() => {
    const byScope: Record<Scope, ContextPromptSummary[]> = { personal: [], team: [], default: [] };
    for (const prompt of prompts) byScope[prompt.scope].push(prompt);
    return byScope;
  }, [prompts]);

  const toggle = (id: string) => {
    if (selected.has(id)) {
      onChange(selectedIds.filter((existing) => existing !== id));
    } else {
      onChange([...selectedIds, id]);
    }
  };

  if (prompts.length === 0) {
    return <p className={styles.empty}>{t("chatbot.contextPrompts.empty")}</p>;
  }

  return (
    <div className={styles.picker} role="listbox" aria-multiselectable aria-label={t("chatbot.contextPrompts.title")}>
      {SCOPE_ORDER.map((scope) => {
        const items = groups[scope];
        if (items.length === 0) return null;
        return (
          <div key={scope} className={styles.group}>
            <div className={styles.groupLabel}>{t(`chatbot.contextPrompts.scope.${scope}`)}</div>
            {items.map((prompt) => {
              const catDef = prompt.category ? PROMPT_CATEGORY_MAP[prompt.category] : null;
              const isSelected = selected.has(prompt.id);
              return (
                <button
                  key={prompt.id}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className={styles.row}
                  data-selected={isSelected}
                  onClick={() => toggle(prompt.id)}
                >
                  <span
                    className={styles.icon}
                    style={catDef ? { backgroundColor: catDef.pillBg, color: catDef.pillFg } : undefined}
                    aria-hidden
                  >
                    <Icon category="outlined" type={catDef ? catDef.icon : "edit_note"} />
                  </span>
                  <span className={styles.text}>
                    <span className={styles.name}>{prompt.name}</span>
                    {prompt.description && <span className={styles.description}>{prompt.description}</span>}
                    <span className={styles.meta}>
                      {prompt.score != null && <ScoreStars score={prompt.score} />}
                      <span className={styles.uses}>
                        {t("chatbot.contextPrompts.uses", { count: prompt.session_count })}
                      </span>
                    </span>
                  </span>
                  <span className={styles.check} aria-hidden>
                    <Icon category="outlined" type={isSelected ? "check_box" : "check_box_outline_blank"} />
                  </span>
                </button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
