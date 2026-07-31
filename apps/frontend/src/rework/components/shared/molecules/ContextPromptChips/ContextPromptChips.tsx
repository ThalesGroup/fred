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

import Icon from "@shared/atoms/Icon/Icon";
import { hashColorIndex } from "@shared/utils/hashColorIndex.ts";
import { useTranslation } from "react-i18next";
import type { ContextPromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ContextPromptChips.module.css";

interface ContextPromptChipsProps {
  prompts: ContextPromptSummary[];
  onRemove: (id: string) => void;
}

/**
 * Removable pills for the chat-context prompts attached to the active session
 * (PROMPT-05 / PROMPTS.md §5). Rendered in the composer `aboveTextSlot`
 * alongside attachment chips; nothing renders when no prompt is attached.
 */
export function ContextPromptChips({ prompts, onRemove }: ContextPromptChipsProps) {
  const { t } = useTranslation();

  if (prompts.length === 0) return null;

  return (
    <div className={styles.chips} aria-label={t("chatbot.contextPrompts.ariaLabel")}>
      {prompts.map((prompt) => {
        return (
          <span key={prompt.id} className={styles.chip}>
            <span className={styles.icon} data-color={hashColorIndex(prompt.id)} aria-hidden>
              <Icon category="outlined" type="edit_note" />
            </span>
            <span className={styles.name} title={prompt.name}>
              {prompt.name}
            </span>
            <button
              type="button"
              className={styles.remove}
              onClick={() => onRemove(prompt.id)}
              aria-label={t("chatbot.contextPrompts.removeAria", { name: prompt.name })}
            >
              <Icon category="outlined" type="close" />
            </button>
          </span>
        );
      })}
    </div>
  );
}
