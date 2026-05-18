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

import type { AwaitingHumanEvent, ChatMessage, VectorSearchHit } from "../../../../../slices/agentic/agenticOpenApi";
import { HitlPrompt } from "@shared/molecules/HitlPrompt/HitlPrompt.tsx";
import { UserTurn } from "@shared/organisms/UserTurn/UserTurn";
import { AssistantTurn } from "@shared/organisms/AssistantTurn/AssistantTurn";
import { ChatMessagesArea } from "@shared/organisms/ChatMessagesArea/ChatMessagesArea";

// Local view model — same shape produced by toConversationMessages in ManagedChatPage.
// Kept here so ConversationThread owns the rendering contract without importing page internals.
export interface ThreadMessage {
  id: string;
  role: "user" | "assistant" | "hitl_request" | "hitl_response";
  text: string;
  isStreaming: boolean;
  traceMessages: ChatMessage[];
  sources: VectorSearchHit[];
  hitlChoices?: Array<{ id: string; label: string }>;
  hitlTitle?: string | null;
}

interface ConversationThreadProps {
  messages: ThreadMessage[];
  pendingHitl: AwaitingHumanEvent | null;
  isLoading: boolean;
  isStreaming: boolean;
  scrollVersion: number;
  onHitlAnswer: (answer: string | boolean, freeText?: string) => void;
}

export function ConversationThread({
  messages,
  pendingHitl,
  isLoading,
  isStreaming,
  scrollVersion,
  onHitlAnswer,
}: ConversationThreadProps) {
  return (
    <ChatMessagesArea
      isEmpty={messages.length === 0 && !isStreaming}
      isLoading={isLoading}
      scrollVersion={scrollVersion}
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
            isStreaming={msg.isStreaming}
          />
        );
      })}
      {pendingHitl && <HitlPrompt event={pendingHitl} onAnswer={onHitlAnswer} />}
    </ChatMessagesArea>
  );
}
