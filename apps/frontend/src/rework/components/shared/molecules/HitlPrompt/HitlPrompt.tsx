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

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextArea from "@shared/atoms/TextArea/TextArea";
import { countUnicodeCodePoints } from "@core/utils/chatInput";
import type { ButtonVariant, ColorTheme } from "@shared/utils/Type.ts";
import type { RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";
import styles from "./HitlPrompt.module.css";

interface HitlPromptProps {
  event: RuntimeAwaitingHumanEvent;
  onAnswer: (answer: string | boolean | undefined, freeText?: string) => void;
  readonly?: boolean;
  maxChatInputChars?: number;
  freeTextValue?: string;
  onFreeTextChange?: (value: string) => void;
}

/**
 * Visual treatment for one HITL choice button. The tool-approval gate
 * (`build_tool_approval_request`, the only HITL prompt in the system today)
 * always uses the stable ids "proceed"/"cancel" — never localized, unlike
 * `label` — so a semantic success/error pairing keys off them directly:
 * Accept reads as a positive (success) action, Reject as a destructive
 * (error) one. A future bespoke Graph-authored question with different
 * choice ids falls back to the previous default/non-default styling.
 */
function choiceButtonStyle(choice: { id: string; default?: boolean }): {
  color: ColorTheme;
  variant: ButtonVariant;
} {
  if (choice.id === "proceed") return { color: "success", variant: "filled" };
  if (choice.id === "cancel") return { color: "error", variant: "filled" };
  return {
    color: choice.default ? "primary" : "on-surface-retreat",
    variant: choice.default ? "filled" : "text",
  };
}

export function HitlPrompt({
  event,
  onAnswer,
  readonly = false,
  maxChatInputChars,
  freeTextValue,
  onFreeTextChange,
}: HitlPromptProps) {
  const { t, i18n } = useTranslation();
  const payload = event.payload;
  const [localFreeText, setLocalFreeText] = useState("");
  const freeText = freeTextValue ?? localFreeText;
  const characterInfoId = useId();
  const characterCount = countUnicodeCodePoints(freeText);
  const isOverLimit = maxChatInputChars !== undefined && characterCount > maxChatInputChars;
  const setFreeText = (value: string) => {
    if (onFreeTextChange) onFreeTextChange(value);
    else setLocalFreeText(value);
  };

  return (
    <div
      className={`${styles.card} ${!readonly ? styles.active : ""}`}
      role="group"
      aria-label={t("chatbot.hitlWaitingAria")}
    >
      {payload.title && <p className={styles.title}>{payload.title}</p>}
      {payload.question && <p className={styles.question}>{payload.question}</p>}

      {/* Answered questions hide their choices — the answer is already written into the
          chat as the turn right after this card, so a disabled button row would be redundant. */}
      {!readonly && payload.choices && payload.choices.length > 0 && (
        <div className={styles.choices}>
          {payload.choices.map((c) => {
            const { color, variant } = choiceButtonStyle(c);
            return (
              <Button
                key={c.id}
                color={color}
                variant={variant}
                size="small"
                style={{ order: c.default ? 2 : 1 }}
                onClick={() => onAnswer(c.id)}
              >
                {c.label}
              </Button>
            );
          })}
        </div>
      )}

      {payload.free_text && !readonly && (
        <div className={styles.freeText}>
          <TextArea
            label={t("chatbot.hitlFreeTextLabel")}
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            rows={2}
            aria-invalid={isOverLimit || undefined}
            aria-describedby={maxChatInputChars !== undefined ? characterInfoId : undefined}
          />
          {maxChatInputChars !== undefined && (
            <div
              id={characterInfoId}
              className={`${styles.characterInfo} ${isOverLimit ? styles.characterInfoError : ""}`}
              aria-live="polite"
            >
              <span>
                {isOverLimit
                  ? t("chatbot.errors.chatInputTooLong", {
                      limit: maxChatInputChars.toLocaleString(i18n.language),
                    })
                  : null}
              </span>
              <span className={styles.characterCount}>
                {t("chatbot.characterCounter", {
                  count: characterCount,
                  limit: maxChatInputChars.toLocaleString(i18n.language),
                })}
              </span>
            </div>
          )}
          <Button
            color="primary"
            variant="filled"
            size="small"
            disabled={!freeText.trim() || isOverLimit}
            onClick={() => onAnswer(undefined, freeText)}
          >
            {t("chatbot.sendHitlAnswer")}
          </Button>
        </div>
      )}
    </div>
  );
}
