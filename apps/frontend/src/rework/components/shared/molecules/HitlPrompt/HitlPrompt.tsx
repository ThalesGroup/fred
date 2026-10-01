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
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextArea from "@shared/atoms/TextArea/TextArea";
import { CharacterLimitNotice } from "@shared/atoms/CharacterLimitNotice/CharacterLimitNotice";
import { countUnicodeCodePoints } from "@core/utils/chatInput";
import type { RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";
import { hitlRendererForTool } from "@rework/features/capabilities/hitlRendererRegistry";
import styles from "./HitlPrompt.module.css";

interface HitlPromptProps {
  event: RuntimeAwaitingHumanEvent;
  onAnswer: (
    answer: string | boolean | undefined,
    freeText?: string,
    skipped?: boolean,
    rememberApproval?: boolean,
  ) => void;
  readonly?: boolean;
  maxChatInputChars?: number;
  freeTextValue?: string;
  onFreeTextChange?: (value: string) => void;
}

export function HitlPrompt({
  event,
  onAnswer,
  readonly = false,
  maxChatInputChars,
  freeTextValue,
  onFreeTextChange,
}: HitlPromptProps) {
  const { t } = useTranslation();
  const payload = event.payload;
  const isAgentQuestion = payload.stage === "agent_question";
  const [localFreeText, setLocalFreeText] = useState("");
  const freeText = freeTextValue ?? localFreeText;
  const characterInfoId = useId();
  const characterCount = countUnicodeCodePoints(freeText);
  const isOverLimit = maxChatInputChars !== undefined && characterCount > maxChatInputChars;
  const skipQuestion = () => onAnswer(undefined, undefined, true);
  const setFreeText = (value: string) => {
    if (onFreeTextChange) onFreeTextChange(value);
    else setLocalFreeText(value);
  };

  return (
    <div
      className={`${styles.card} ${!readonly ? styles.active : ""} ${isAgentQuestion && !readonly ? styles.skippable : ""}`}
      role="group"
      aria-label={t("chatbot.hitlWaitingAria")}
    >
      {isAgentQuestion && !readonly && (
        <IconButton
          className={styles.skipClose}
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "close" }}
          aria-label={t("chatbot.skipHitlQuestionAria")}
          title={t("chatbot.skipHitlQuestionAria")}
          onClick={skipQuestion}
        />
      )}
      {payload.title && <p className={styles.title}>{payload.title}</p>}
      {payload.question && <p className={styles.question}>{payload.question}</p>}

      {/* What the gate carries is a tool name and 1 200 characters of argument
          preview — enough to say WHICH call, never enough to judge it. A
          capability whose approval needs real context contributes a renderer
          keyed by tool name; everything else shows nothing extra, as before. */}
      {(payload.pending_calls ?? []).map((call) => {
        const Renderer = hitlRendererForTool(call.tool_name);
        return Renderer ? <Renderer key={call.tool_call_id || call.tool_name} call={call} /> : null;
      })}

      {/* Read-only prompts hide choices; answered agent questions show their
          result under the matching tool line instead. */}
      {!readonly && payload.choices && payload.choices.length > 0 && (
        <div className={styles.choices}>
          {payload.choices.map((c) => {
            return (
              <Button
                key={c.id}
                className={c.description ? styles.choiceWithDescription : undefined}
                color="primary"
                variant="outlined"
                size="medium"
                disabled={isOverLimit}
                onClick={() => onAnswer(c.id, freeText.trim() ? freeText : undefined)}
              >
                {c.description ? (
                  <span className={styles.choiceContent}>
                    <span>{c.label}</span>
                    <span className={styles.choiceDescription}>{c.description}</span>
                  </span>
                ) : (
                  c.label
                )}
              </Button>
            );
          })}
          {payload.stage === "tool_approval" &&
            (payload.pending_calls?.length ?? 0) > 0 &&
            payload.pending_calls?.every((call) => call.tool_name) &&
            payload.choices.some((choice) => choice.id === "proceed") && (
              <Button
                color="primary"
                variant="outlined"
                size="medium"
                onClick={() => onAnswer("proceed", undefined, false, true)}
              >
                {t("chatbot.approveForConversation")}
              </Button>
            )}
        </div>
      )}

      {payload.free_text && !readonly && (
        <div className={styles.freeText}>
          <TextArea
            label={t("chatbot.hitlFreeTextLabel")}
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && freeText.trim() && !isOverLimit) {
                e.preventDefault();
                onAnswer(undefined, freeText);
              }
            }}
            rows={2}
            aria-invalid={isOverLimit || undefined}
            aria-describedby={maxChatInputChars !== undefined ? characterInfoId : undefined}
          />
          <CharacterLimitNotice id={characterInfoId} count={characterCount} limit={maxChatInputChars} />
        </div>
      )}

      {!readonly && (payload.free_text || isAgentQuestion) && (
        <div className={styles.actions}>
          {payload.free_text && (
            <Button
              color="primary"
              variant="filled"
              size="small"
              disabled={!freeText.trim() || isOverLimit}
              onClick={() => onAnswer(undefined, freeText)}
            >
              {t("chatbot.sendHitlAnswer")}
            </Button>
          )}
          {isAgentQuestion && (
            <Button color="on-surface-retreat" variant="text" size="small" onClick={skipQuestion}>
              {t("chatbot.skipHitlQuestion")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
