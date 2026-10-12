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

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import TextArea from "@shared/atoms/TextArea/TextArea";
import { CharacterLimitNotice } from "@shared/atoms/CharacterLimitNotice/CharacterLimitNotice";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { countUnicodeCodePoints } from "@core/utils/chatInput";
import type { RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";
import { hitlRendererForTool } from "@rework/features/capabilities/hitlRendererRegistry";
import styles from "./HitlPrompt.module.css";

/** Where each grouped question stands, shown as the icon of its tab. */
export type HitlQuestionState = "waiting" | "answered" | "skipped";

const QUESTION_STATE_ICON = {
  waiting: "radio_button_unchecked",
  answered: "check_circle",
  skipped: "do_not_disturb_on",
} as const;

interface HitlPromptProps {
  event: RuntimeAwaitingHumanEvent;
  siblingQuestions?: RuntimeAwaitingHumanEvent[];
  onSelectQuestion?: (event: RuntimeAwaitingHumanEvent) => void;
  busy?: boolean;
  stagedAnswer?: { answer: string | boolean | undefined; freeText?: string; skipped: boolean };
  canSendAll?: boolean;
  /** Per-tab state, in `siblingQuestions` order. */
  questionStates?: HitlQuestionState[];
  onStageAnswer?: (answer: string | boolean | undefined, freeText?: string, skipped?: boolean) => void;
  onSendAll?: () => void;
  onSkipAll?: () => void;
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

// Number shown before a choice: the key that picks it.
function ChoiceBadge({ label }: { label: string }) {
  return (
    <span className={styles.choiceBadge} aria-hidden="true">
      {label}
    </span>
  );
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
  questionStates = [],
  onStageAnswer,
  onSendAll,
  onSkipAll,
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
  const questionTabsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const tabs = questionTabsRef.current;
    if (!tabs) return;
    const scrollWithWheel = (wheel: WheelEvent) => {
      if (wheel.ctrlKey || wheel.shiftKey || Math.abs(wheel.deltaX) >= Math.abs(wheel.deltaY)) return;
      const maxScroll = tabs.scrollWidth - tabs.clientWidth;
      if (maxScroll <= 0) return;
      const unit =
        wheel.deltaMode === WheelEvent.DOM_DELTA_LINE
          ? 16
          : wheel.deltaMode === WheelEvent.DOM_DELTA_PAGE
            ? tabs.clientWidth
            : 1;
      const next = Math.max(0, Math.min(maxScroll, tabs.scrollLeft + wheel.deltaY * unit));
      if (next === tabs.scrollLeft) return;
      tabs.scrollLeft = next;
      wheel.preventDefault();
    };
    tabs.addEventListener("wheel", scrollWithWheel, { passive: false });
    return () => tabs.removeEventListener("wheel", scrollWithWheel);
  }, [hasQuestionTabs]);
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
  // In a grouped card a choice replaces any typed "Other" answer, so the field is cleared.
  const chooseChoice = (id: string) => {
    if (collectingAnswers) {
      if (freeText) setFreeText("");
      answerQuestion(id);
    } else answerQuestion(id, freeText.trim() ? freeText : undefined);
  };
  const cardRef = useRef<HTMLDivElement>(null);
  const choices = !readonly ? (payload.choices ?? []) : [];
  const approveForConversation =
    payload.stage === "tool_approval" &&
    (payload.pending_calls?.length ?? 0) > 0 &&
    payload.pending_calls?.every((call) => call.tool_name) &&
    choices.some((choice) => choice.id === "proceed");
  const keyActions = useRef<{ choose: (index: number) => void; send: () => void; skip: () => void }>(null);
  keyActions.current = {
    choose: (index) => {
      if (index < choices.length) {
        if (!isOverLimit) chooseChoice(choices[index].id);
      } else if (index === choices.length && approveForConversation) onAnswer("proceed", undefined, false, true);
    },
    send: () => {
      if (collectingAnswers && canSendAll) onSendAll?.();
    },
    skip: () => {
      if (isAgentQuestion) skipQuestion();
    },
  };
  // Number keys pick a choice, Enter sends, Escape skips. Keys never act from a field or
  // from inside an open drawer or dialog; focus left on any other button still counts.
  useEffect(() => {
    if (readonly || busy) return;
    const overlay = 'aside[data-open="true"], [role="dialog"], [aria-modal="true"]';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat || event.isComposing) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const active = document.activeElement as HTMLElement | null;
      // A field disabled while it had focus (the held composer) can keep it in some browsers.
      const disabled = (active as HTMLTextAreaElement | null)?.disabled === true;
      const onPage = !active || active === document.body || disabled;
      const inField =
        !disabled && !!active?.matches('input, textarea, select, [contenteditable=""], [contenteditable="true"]');
      if (inField || active?.closest(overlay)) return;
      const actions = keyActions.current;
      if (!actions) return;
      if (/^[1-9]$/.test(event.key)) {
        event.preventDefault();
        actions.choose(Number(event.key) - 1);
      } else if (event.key === "Enter" && onPage) {
        // On a focused button, Enter keeps activating that button.
        event.preventDefault();
        actions.send();
      } else if (event.key === "Escape") {
        // An open drawer or dialog owns Escape: closing it must not also skip the question.
        if (document.querySelector(overlay)) return;
        event.preventDefault();
        actions.skip();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [readonly, busy]);
  const setFreeText = (value: string) => {
    if (onFreeTextChange) onFreeTextChange(value);
    else setLocalFreeText(value);
  };

  // Grouped questions: a typed answer counts once validated, and skipping is the last choice.
  // Once this exact text is validated, the button becomes a success check; editing brings it back.
  const textValidated =
    !!freeText.trim() &&
    !!stagedAnswer &&
    !stagedAnswer.skipped &&
    stagedAnswer.answer === undefined &&
    stagedAnswer.freeText === freeText;
  const validateButton = textValidated ? (
    <span
      className={`${styles.successCheck} ${styles.validated}`}
      role="img"
      aria-label={t("chatbot.hitlAnswerValidated")}
    >
      <Icon category="outlined" type="check_circle" />
    </span>
  ) : (
    <IconButton
      color="primary"
      variant="filled"
      size="small"
      icon={{ category: "outlined", type: "check" }}
      aria-label={t("chatbot.validateHitlAnswer")}
      title={t("chatbot.validateHitlAnswer")}
      disabled={!freeText.trim() || isOverLimit || busy}
      onClick={() => answerQuestion(undefined, freeText)}
    />
  );
  const skipChoice = (
    <Button
      className={[styles.choice, styles.skipChoice, stagedAnswer?.skipped && styles.selectedChoice]
        .filter(Boolean)
        .join(" ")}
      color="primary"
      variant="outlined"
      size="small"
      disabled={busy}
      aria-pressed={!!stagedAnswer?.skipped}
      aria-keyshortcuts="Escape"
      onClick={skipQuestion}
    >
      <kbd className={styles.keyHint} aria-hidden="true">
        ESC
      </kbd>
      {t("chatbot.skipHitlQuestion")}
    </Button>
  );

  return (
    <div
      ref={cardRef}
      className={`${styles.card} ${!readonly ? styles.active : ""} ${isAgentQuestion && !readonly ? styles.skippable : ""}`}
      role="group"
      aria-label={t("chatbot.hitlWaitingAria")}
    >
      {hasQuestionTabs && (
        <div ref={questionTabsRef} className={styles.questionTabs}>
          <ButtonGroup
            variant="tabs"
            size="2xs"
            color="primary"
            aria-label={t("chatbot.hitlQuestionTabsAria")}
            selectedIndex={Math.max(0, selectedQuestionIndex)}
            onSelectedIndexChange={(index) => onSelectQuestion?.(siblingQuestions[index])}
            items={siblingQuestions.map((question, index) => {
              const state = questionStates[index] ?? "waiting";
              return {
                label: questionTabLabel(question, index, t("chatbot.hitlQuestionTabFallback")),
                title: question.payload.title || question.payload.question,
                icon: {
                  category: "outlined",
                  type: QUESTION_STATE_ICON[state],
                  accessibleName: t(`chatbot.hitlQuestionState.${state}`),
                },
                ...{ "data-hitl-state": state },
              };
            })}
          />
        </div>
      )}
      {((payload.title && !hasQuestionTabs) || payload.question) && (
        <div className={styles.header}>
          {payload.title && !hasQuestionTabs && <p className={styles.title}>{payload.title}</p>}
          {payload.question && (
            <div className={styles.question}>
              <MarkdownRenderer text={payload.question} />
            </div>
          )}
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
          {payload.choices.map((c, index) => {
            const selected =
              collectingAnswers && stagedAnswer?.answer === c.id && !stagedAnswer.skipped && !freeText.trim();
            return (
              <Button
                key={c.id}
                className={[
                  styles.choice,
                  payload.stage === "tool_approval" && c.id === "proceed" && styles.acceptChoice,
                  payload.stage === "tool_approval" && c.id === "cancel" && styles.refuseChoice,
                  selected && styles.selectedChoice,
                ]
                  .filter(Boolean)
                  .join(" ")}
                color="primary"
                variant="outlined"
                size={isAgentQuestion ? "small" : "medium"}
                disabled={isOverLimit || busy}
                aria-pressed={collectingAnswers ? selected : undefined}
                aria-keyshortcuts={index < 9 ? String(index + 1) : undefined}
                onClick={() => chooseChoice(c.id)}
              >
                {index < 9 && <ChoiceBadge label={String(index + 1)} />}
                {c.description ? (
                  <span className={styles.choiceContent}>
                    <span>{c.label}</span>
                    <span className={styles.choiceDescription}>{c.description}</span>
                  </span>
                ) : (
                  c.label
                )}
                {selected && (
                  <span className={`${styles.successCheck} ${styles.choiceCheck}`} aria-hidden="true">
                    <Icon category="outlined" type="check_circle" />
                  </span>
                )}
              </Button>
            );
          })}
          {hasChoiceTextRow && (
            <label className={`${styles.otherChoice} ${textValidated ? styles.otherValidated : ""}`}>
              <span className={styles.otherChoiceIcon}>
                <Icon category="outlined" type="edit" />
              </span>
              <span className={styles.otherChoiceLabel}>{t("chatbot.hitlOtherAnswerPlaceholder")}</span>
              <input
                type="text"
                value={freeText}
                placeholder={t("chatbot.hitlOtherAnswerHint")}
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
              {collectingAnswers && freeText.trim() && validateButton}
            </label>
          )}
          {collectingAnswers && skipChoice}
          {approveForConversation && (
            <Button
              className={styles.choice}
              color="primary"
              variant="outlined"
              size="medium"
              disabled={busy}
              aria-keyshortcuts={payload.choices.length < 9 ? String(payload.choices.length + 1) : undefined}
              onClick={() => onAnswer("proceed", undefined, false, true)}
            >
              {payload.choices.length < 9 && <ChoiceBadge label={String(payload.choices.length + 1)} />}
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
          {collectingAnswers && <div className={styles.validateRow}>{validateButton}</div>}
          {collectingAnswers && <div className={styles.choices}>{skipChoice}</div>}
        </div>
      )}

      {!readonly && (payload.free_text || isAgentQuestion) && (
        // Secondary actions on the left, the logical main action last.
        <div className={styles.actions}>
          {collectingAnswers && (
            <Button color="on-surface-retreat" variant="text" size="small" disabled={busy} onClick={onSkipAll}>
              {t("chatbot.skipAllHitlQuestions")}
            </Button>
          )}
          {isAgentQuestion && !collectingAnswers && (
            <Button
              color="on-surface-retreat"
              variant="text"
              size="small"
              disabled={busy}
              aria-keyshortcuts="Escape"
              onClick={skipQuestion}
            >
              {t("chatbot.skipHitlQuestion")}
              <kbd className={styles.keyHint} aria-hidden="true">
                ESC
              </kbd>
            </Button>
          )}
          {payload.free_text && !collectingAnswers && (
            <Button
              color="primary"
              variant="filled"
              size="small"
              disabled={!freeText.trim() || isOverLimit || busy}
              onClick={() => answerQuestion(undefined, freeText)}
            >
              {t("chatbot.sendHitlAnswer")}
            </Button>
          )}
          {collectingAnswers && (
            <Button color="primary" variant="filled" size="small" disabled={!canSendAll || busy} onClick={onSendAll}>
              {t("chatbot.sendAllHitlAnswers")}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
