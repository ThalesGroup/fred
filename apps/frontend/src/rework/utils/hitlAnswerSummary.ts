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

import type { ChatMessage, HitlRequestPart, HitlResponsePart, ToolCallPart } from "../../slices/runtime/runtimeOpenApi";

export interface HitlAnswerSummary {
  question: string;
  answer: string | null;
  comment: string | null;
  skipped: boolean;
  choiceId: string | null;
  choices: Array<{ id: string; label: string; description?: string | null }>;
}

export function hitlAnswerSummary(request: HitlRequestPart, response: HitlResponsePart): HitlAnswerSummary {
  const choiceId = response.choice_id;
  const choiceLabel = choiceId
    ? (response.label ?? request.choices.find((choice) => choice.id === choiceId)?.label ?? choiceId)
    : null;
  return {
    question: request.question,
    answer: choiceLabel ?? response.text ?? null,
    comment: choiceLabel ? (response.text ?? null) : null,
    skipped: response.skipped === true,
    choiceId: choiceId ?? null,
    choices: request.choices,
  };
}

export function hitlAnswerSummaryForTool(messages: ChatMessage[], call: ChatMessage): HitlAnswerSummary | null {
  const toolCall = call.parts?.[0] as ToolCallPart | undefined;
  const callId = toolCall?.call_id;
  if (!callId) return null;
  const sameExchange = messages.filter(
    (message) => message.session_id === call.session_id && message.exchange_id === call.exchange_id,
  );
  const request = sameExchange.find((message) => {
    const part = message.parts?.[0] as HitlRequestPart | undefined;
    return message.channel === "hitl_request" && part?.stage === "agent_question" && part.occurrence_id === callId;
  });
  const response = sameExchange.find((message) => {
    const part = message.parts?.[0] as HitlResponsePart | undefined;
    return message.channel === "hitl_response" && part?.occurrence_id === callId;
  });
  if (!request || !response) return null;
  const summary = hitlAnswerSummary(request.parts[0] as HitlRequestPart, response.parts[0] as HitlResponsePart);
  const authoredChoices = toolCall?.args?.choices;
  if (!Array.isArray(authoredChoices)) return summary;
  return {
    ...summary,
    choices: summary.choices.map((choice) => {
      const authored = authoredChoices.find((candidate) => candidate?.id === choice.id);
      return {
        ...choice,
        description: typeof authored?.description === "string" ? authored.description : undefined,
      };
    }),
  };
}
