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
import styles from "./ContextPromptPicker.module.css";

type Scope = ContextPromptSummary["scope"];

interface ContextPromptPickerProps {
  prompts: ContextPromptSummary[];
  /** Picking a prompt inserts its content into the composer input (one-shot). */
  onSelect: (prompt: ContextPromptSummary) => void;
}

const SCOPE_ORDER: Scope[] = ["personal", "team"];

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
 * Prompt-library picker for the composer, grouped by scope (personal / team)
 * with a session-count-ordered list per group (PROMPTS.md §5). Picking a prompt
 * is a one-shot action: its content is inserted into the composer input (the
 * caller fetches the full text), so rows are plain actions, not toggles.
 */
export function ContextPromptPicker({ prompts, onSelect }: ContextPromptPickerProps) {
  const { t } = useTranslation();

  const groups = useMemo(() => {
    const byScope: Record<Scope, ContextPromptSummary[]> = { personal: [], team: [] };
    for (const prompt of prompts) byScope[prompt.scope].push(prompt);
    return byScope;
  }, [prompts]);

  if (prompts.length === 0) {
    return <p className={styles.empty}>{t("chatbot.contextPrompts.empty")}</p>;
  }

  return (
    <div className={styles.picker} role="menu" aria-label={t("chatbot.contextPrompts.title")}>
      {SCOPE_ORDER.map((scope) => {
        const items = groups[scope];
        if (items.length === 0) return null;
        return (
          <div key={scope} className={styles.group}>
            {items.map((prompt) => (
              <button
                key={prompt.id}
                type="button"
                role="menuitem"
                className={styles.row}
                onClick={() => onSelect(prompt)}
              >
                <span className={styles.text}>
                  <span className={styles.name}>{prompt.name}</span>
                  {prompt.description && <span className={styles.description}>{prompt.description}</span>}
                  {prompt.score != null && (
                    <span className={styles.meta}>
                      <ScoreStars score={prompt.score} />
                    </span>
                  )}
                </span>
              </button>
            ))}
          </div>
        );
      })}
    </div>
  );
}
