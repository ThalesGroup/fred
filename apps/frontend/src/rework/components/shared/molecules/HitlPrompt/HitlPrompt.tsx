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
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextArea from "@shared/atoms/TextArea/TextArea";
import { CharacterLimitNotice } from "@shared/atoms/CharacterLimitNotice/CharacterLimitNotice";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { countUnicodeCodePoints } from "@core/utils/chatInput";
import type { RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";
import { hitlRendererForTool } from "@rework/features/capabilities/hitlRendererRegistry";
import styles from "./HitlPrompt.module.css";

interface HitlPromptProps {
  event: RuntimeAwaitingHumanEvent;
  siblingQuestions?: RuntimeAwaitingHumanEvent[];
  onSelectQuestion?: (event: RuntimeAwaitingHumanEvent) => void;
  busy?: boolean;
  stagedAnswer?: { answer: string | boolean | undefined; freeText?: string; skipped: boolean };
  canSendAll?: boolean;
  onStageAnswer?: (answer: string | boolean | undefined, freeText?: string, skipped?: boolean) => void;
  onSendAll?: () => void;
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

function questionTabLabel(event: RuntimeAwaitingHumanEvent, index: number, fallback: string): string {
  const title = event.payload.title?.trim();
  if (!title) return `${fallback} ${index + 1}`;
  return title;
}

export function HitlPrompt({
  event,
  siblingQuestions = [],
  onSelectQuestion,
  busy = false,
  stagedAnswer,
  canSendAll = false,
  onStageAnswer,
  onSendAll,
  onAnswer,
  readonly = false,
  maxChatInputChars,
  freeTextValue,
  onFreeTextChange,
}: HitlPromptProps) {
  const { t } = useTranslation();
  const payload = event.payload;
  const isAgentQuestion = payload.stage === "agent_question";
  const hasQuestionTabs = !readonly && isAgentQuestion && siblingQuestions.length > 1;
  const collectingAnswers = hasQuestionTabs && onStageAnswer !== undefined;
  const selectedQuestionIndex = siblingQuestions.findIndex((question) =>
    question.payload.occurrence_id
      ? question.payload.occurrence_id === event.payload.occurrence_id
      : question.payload.interrupt_id === event.payload.interrupt_id,
  );
  const hasChoiceTextRow = isAgentQuestion && payload.free_text && (payload.choices?.length ?? 0) > 0;
  const [localFreeText, setLocalFreeText] = useState("");
  const freeText = freeTextValue ?? localFreeText;
  const characterInfoId = useId();
  const characterCount = countUnicodeCodePoints(freeText);
  const isOverLimit = maxChatInputChars !== undefined && characterCount > maxChatInputChars;
  const answerQuestion = (answer: string | boolean | undefined, text?: string, skipped = false) => {
    if (busy) return;
    if (collectingAnswers) onStageAnswer(answer, text, skipped);
    else if (skipped) onAnswer(answer, text, true);
    else onAnswer(answer, text);
  };
  const skipQuestion = () => answerQuestion(undefined, undefined, true);
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
      {hasQuestionTabs && (
        <div className={styles.questionTabs}>
          <ButtonGroup
            variant="tabs"
            size="small"
            color="primary"
            aria-label={t("chatbot.hitlQuestionTabsAria")}
            selectedIndex={Math.max(0, selectedQuestionIndex)}
            onSelectedIndexChange={(index) => onSelectQuestion?.(siblingQuestions[index])}
            items={siblingQuestions.map((question, index) => ({
              label: questionTabLabel(question, index, t("chatbot.hitlQuestionTabFallback")),
              title: question.payload.title || question.payload.question,
            }))}
          />
        </div>
      )}
      {isAgentQuestion && !readonly && (
        <IconButton
          className={styles.skipClose}
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "close" }}
          aria-label={t("chatbot.skipHitlQuestionAria")}
          title={t("chatbot.skipHitlQuestionAria")}
          onClick={skipQuestion}
          disabled={busy}
        />
      )}
      {payload.title && !hasQuestionTabs && <p className={styles.title}>{payload.title}</p>}
      {payload.question && (
        <div className={styles.question}>
          <MarkdownRenderer text={payload.question} />
        </div>
      )}

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
                className={[
                  c.description && styles.choiceWithDescription,
                  collectingAnswers && stagedAnswer?.answer === c.id && !stagedAnswer.skipped && styles.selectedChoice,
                ]
                  .filter(Boolean)
                  .join(" ")}
                color="primary"
                variant="outlined"
                size="medium"
                disabled={isOverLimit || busy}
                aria-pressed={collectingAnswers ? stagedAnswer?.answer === c.id && !stagedAnswer.skipped : undefined}
                onClick={() => answerQuestion(c.id, freeText.trim() ? freeText : undefined)}
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
          {hasChoiceTextRow && (
            <label className={styles.otherChoice}>
              <span className={styles.otherChoiceLabel}>{t("chatbot.hitlOtherAnswerPlaceholder")}</span>
              <input
                type="text"
                value={freeText}
                disabled={busy}
                onChange={(e) => setFreeText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.nativeEvent.isComposing && freeText.trim() && !isOverLimit && !busy) {
                    e.preventDefault();
                    answerQuestion(undefined, freeText);
                  }
                }}
                aria-invalid={isOverLimit || undefined}
                aria-describedby={maxChatInputChars !== undefined ? characterInfoId : undefined}
              />
            </label>
          )}
          {payload.stage === "tool_approval" &&
            (payload.pending_calls?.length ?? 0) > 0 &&
            payload.pending_calls?.every((call) => call.tool_name) &&
            payload.choices.some((choice) => choice.id === "proceed") && (
              <Button
                color="primary"
                variant="outlined"
                size="medium"
                disabled={busy}
                onClick={() => onAnswer("proceed", undefined, false, true)}
              >
                {t("chatbot.approveForConversation")}
              </Button>
            )}
        </div>
      )}

      {hasChoiceTextRow && !readonly && (
        <CharacterLimitNotice id={characterInfoId} count={characterCount} limit={maxChatInputChars} />
      )}

      {payload.free_text && !readonly && !hasChoiceTextRow && (
        <div className={styles.freeText}>
          <TextArea
            label={t("chatbot.hitlFreeTextLabel")}
            value={freeText}
            disabled={busy}
            onChange={(e) => setFreeText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && freeText.trim() && !isOverLimit && !busy) {
                e.preventDefault();
                answerQuestion(undefined, freeText);
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
              disabled={!freeText.trim() || isOverLimit || busy}
              onClick={() => answerQuestion(undefined, freeText)}
            >
              {t(collectingAnswers ? "chatbot.nextHitlQuestion" : "chatbot.sendHitlAnswer")}
            </Button>
          )}
          {collectingAnswers && (
            <Button color="primary" variant="filled" size="small" disabled={!canSendAll || busy} onClick={onSendAll}>
              {t("chatbot.sendAllHitlAnswers")}
            </Button>
          )}
          {isAgentQuestion && (
            <Button color="on-surface-retreat" variant="text" size="small" disabled={busy} onClick={skipQuestion}>
              {t("chatbot.skipHitlQuestion")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
