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

import type { ReactNode, RefObject } from "react";
import type { AwaitingHumanEvent } from "../../../../../slices/agentic/agenticOpenApi";
import type { ThreadMessage } from "@rework/types/thread";
import { HitlPrompt } from "@shared/molecules/HitlPrompt/HitlPrompt.tsx";
import { UserTurn } from "@shared/organisms/UserTurn/UserTurn";
import { AssistantTurn } from "@shared/organisms/AssistantTurn/AssistantTurn";
import { ChatMessagesArea } from "@shared/organisms/ChatMessagesArea/ChatMessagesArea";

interface ConversationThreadProps {
  messages: ThreadMessage[];
  pendingHitl: AwaitingHumanEvent | null;
  isLoading: boolean;
  isStreaming: boolean;
  emptyState?: ReactNode;
  scrollContainerRef: RefObject<HTMLDivElement>;
  onHitlAnswer: (answer: string | boolean, freeText?: string) => void;
}

export function ConversationThread({
  messages,
  pendingHitl,
  isLoading,
  isStreaming,
  emptyState,
  scrollContainerRef,
  onHitlAnswer,
}: ConversationThreadProps) {
  const turnKey = messages.filter((m) => m.role === "user").length;

  return (
    <ChatMessagesArea
      isEmpty={messages.length === 0 && !isStreaming}
      isLoading={isLoading}
      emptyState={emptyState}
      scrollContainerRef={scrollContainerRef}
      turnKey={turnKey}
      isStreaming={isStreaming}
    >
      {messages.map((msg) => {
        if (msg.role === "user" || msg.role === "hitl_response") {
          return <UserTurn key={msg.id} text={msg.text} />;
        }
        if (msg.role === "hitl_request") {
          const frozenEvent: AwaitingHumanEvent = {
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
            tokenUsage={msg.tokenUsage}
            isStreaming={msg.isStreaming}
          />
        );
      })}
      {pendingHitl && <HitlPrompt event={pendingHitl} onAnswer={onHitlAnswer} />}
    </ChatMessagesArea>
  );
}
