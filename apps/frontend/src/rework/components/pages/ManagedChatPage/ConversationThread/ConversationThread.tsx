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

// Page-local composition of organisms for ManagedChatPage.
// Lives under pages/ so it may import from shared/organisms freely.

import { memo, type ReactNode, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import type { RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";
import type { ThreadMessage } from "@rework/types/thread";
import { HitlPrompt } from "@shared/molecules/HitlPrompt/HitlPrompt.tsx";
import { UserTurn } from "@shared/organisms/UserTurn/UserTurn";
import { AssistantTurn } from "@shared/organisms/AssistantTurn/AssistantTurn";
import { ChatMessagesArea } from "@shared/organisms/ChatMessagesArea/ChatMessagesArea";
import { hitlResponseKey } from "../toThreadMessages";

interface ConversationThreadProps {
  messages: ThreadMessage[];
  pendingHitl: RuntimeAwaitingHumanEvent | null;
  isLoading: boolean;
  isStreaming: boolean;
  emptyState?: ReactNode;
  scrollContainerRef: RefObject<HTMLDivElement>;
  onHitlAnswer: (answer: string | boolean | undefined, freeText?: string) => void;
  maxChatInputChars?: number;
  hitlFreeText: string;
  onHitlFreeTextChange: (value: string) => void;
}

// Memoized: ManagedChatPage re-renders on every composer keystroke (the input
// state lives above this tree). Without this boundary, every historical
// message — including its full markdown re-parse — re-rendered on every
// character typed, with cost scaling with conversation length (#2221).
export const ConversationThread = memo(function ConversationThread({
  messages,
  pendingHitl,
  isLoading,
  isStreaming,
  emptyState,
  scrollContainerRef,
  onHitlAnswer,
  maxChatInputChars,
  hitlFreeText,
  onHitlFreeTextChange,
}: ConversationThreadProps) {
  const { t } = useTranslation();
  const turnKey = messages.filter((m) => m.role === "user").length;
  // The pending tool call(s) this HITL prompt gates, if the runtime reported
  // any (see build_tool_approval_request's HumanInputRequest.pending_calls —
  // #2177: one prompt can batch several calls at once) — lets the trace row
  // for each of those tools render "awaiting confirmation" instead of
  // "running" while the prompt below is still unanswered.
  const pendingToolCallIds =
    pendingHitl?.payload.pending_calls?.map((c) => c.tool_call_id).filter((id): id is string => !!id) ?? null;

  return (
    <ChatMessagesArea
      isEmpty={messages.length === 0 && !isStreaming}
      isLoading={isLoading}
      emptyState={emptyState}
      scrollContainerRef={scrollContainerRef}
      turnKey={turnKey}
    >
      {messages.map((msg) => {
        if (msg.role === "user" || msg.role === "hitl_response") {
          // hitl_response's `text` is the raw persisted choice_id ("proceed" /
          // "cancel") — the backend never localizes it (see hitlResponseKey's
          // docstring) — so translate it here; an unrecognized id falls back
          // to showing the raw text rather than nothing.
          const key = msg.role === "hitl_response" ? hitlResponseKey(msg.text) : null;
          return <UserTurn key={msg.id} text={key ? t(key) : msg.text} />;
        }
        if (msg.role === "hitl_request") {
          const frozenEvent: RuntimeAwaitingHumanEvent = {
            session_id: "",
            exchange_id: msg.id,
            payload: { question: msg.text, choices: msg.hitlChoices, title: msg.hitlTitle },
          };
          return <HitlPrompt key={msg.id} event={frozenEvent} onAnswer={() => {}} readonly />;
        }
        return (
          <AssistantTurn
            key={msg.id}
            text={msg.text}
            traceMessages={msg.traceMessages}
            sources={msg.sources}
            uiParts={msg.uiParts}
            tokenUsage={msg.tokenUsage}
            isStreaming={msg.isStreaming}
            pendingToolCallIds={pendingToolCallIds}
          />
        );
      })}
      {pendingHitl && (
        <HitlPrompt
          event={pendingHitl}
          onAnswer={onHitlAnswer}
          maxChatInputChars={maxChatInputChars}
          freeTextValue={hitlFreeText}
          onFreeTextChange={onHitlFreeTextChange}
        />
      )}
    </ChatMessagesArea>
  );
});
