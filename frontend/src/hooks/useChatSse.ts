// Copyright Thales 2025
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

import { useCallback, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

import { upsertOne } from "../components/chatbot/ChatBotUtils";
import { KeyCloakService } from "../security/KeycloakService";
import type { AwaitingHumanEvent, ChatMessage } from "../slices/agentic/agenticOpenApi";
import type { EffectiveChatOptions } from "../slices/controlPlane/controlPlaneOpenApi";
import { usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation } from "../slices/controlPlane/controlPlaneOpenApi";
import type {
  AssistantDeltaRuntimeEvent,
  AwaitingHumanRuntimeEvent,
  FinalRuntimeEvent,
  NodeErrorRuntimeEvent,
  RuntimeContext,
  StatusRuntimeEvent,
  ToolCallRuntimeEvent,
  ToolResultRuntimeEvent,
  TurnPersistedEvent,
} from "../slices/runtime/runtimeOpenApi";

type AnyRuntimeEvent =
  | ({ kind: "assistant_delta" } & AssistantDeltaRuntimeEvent)
  | ({ kind: "awaiting_human" } & AwaitingHumanRuntimeEvent)
  | ({ kind: "final" } & FinalRuntimeEvent)
  | ({ kind: "node_error" } & NodeErrorRuntimeEvent)
  | ({ kind: "status" } & StatusRuntimeEvent)
  | ({ kind: "tool_call" } & ToolCallRuntimeEvent)
  | ({ kind: "tool_result" } & ToolResultRuntimeEvent)
  | ({ kind: "turn_persisted" } & TurnPersistedEvent);

export type ChatSseCallbacks = {
  onBindDraftAgentToSessionId?: (sessionId: string) => void;
  onTurnPersisted?: (sessionId: string) => void;
  onAwaitingHuman?: (event: AwaitingHumanEvent) => void;
  onError?: (message: string) => void;
};

/**
 * SSE chat transport for managed agent instances.
 *
 * Unlike useChatSocket (WebSocket), this hook:
 * - Calls control-plane /prepare-execution before each send to get a short-lived ExecutionGrant
 * - POSTs to the runtime execute_stream_url using fetch() with SSE response parsing
 * - Maps RuntimeEvent frames (assistant_delta, final, tool_call, etc.) to ChatMessage[]
 * - Supports HITL resume via sendHitlResume()
 */
export function useChatSse(
  params: {
    agentInstanceId: string;
    teamId: string;
  } & ChatSseCallbacks,
) {
  const { agentInstanceId, teamId, onBindDraftAgentToSessionId, onTurnPersisted, onAwaitingHuman, onError } = params;

  const [prepareExecution] =
    usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation();

  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [waitResponse, setWaitResponse] = useState(false);
  const [effectiveChatOptions, setEffectiveChatOptions] = useState<EffectiveChatOptions | null>(null);

  const setAll = useCallback((next: ChatMessage[]) => {
    messagesRef.current = next;
    setMessages(next);
  }, []);

  const reset = useCallback(() => setAll([]), [setAll]);
  const replaceAllMessages = useCallback((msgs: ChatMessage[]) => setAll(msgs), [setAll]);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setWaitResponse(false);
  }, []);

  // Parse one SSE block and dispatch to ChatMessage state + callbacks.
  // Uses stable refs so this function itself stays stable across renders.
  const processEvent = useCallback(
    (
      event: AnyRuntimeEvent,
      ctx: {
        exchangeId: string;
        sessionId: string;
        rankRef: { current: number };
        deltaRankRef: { current: number | null };
      },
    ) => {
      const { exchangeId, sessionId, rankRef, deltaRankRef } = ctx;
      const ts = new Date().toISOString();

      const emit = (msg: ChatMessage) => {
        messagesRef.current = upsertOne(messagesRef.current, msg);
        setMessages([...messagesRef.current]);
      };

      switch (event.kind) {
        case "assistant_delta": {
          if (deltaRankRef.current === null) {
            deltaRankRef.current = rankRef.current++;
          }
          emit({
            session_id: sessionId,
            exchange_id: exchangeId,
            rank: deltaRankRef.current,
            timestamp: ts,
            role: "assistant",
            channel: "final",
            parts: [{ type: "text", text: event.delta }],
            metadata: { extras: { streaming_delta: true } },
          });
          break;
        }

        case "final": {
          // Authoritative frame — replaces any accumulated delta at the same rank.
          const rank = deltaRankRef.current ?? rankRef.current++;
          const parts: ChatMessage["parts"] = [{ type: "text", text: event.content ?? "" }];
          // Append geo/link ui_parts as native ChatMessage parts.
          if (event.ui_parts?.length) {
            for (const p of event.ui_parts) {
              parts.push(p as ChatMessage["parts"][number]);
            }
          }
          emit({
            session_id: sessionId,
            exchange_id: exchangeId,
            rank,
            timestamp: ts,
            role: "assistant",
            channel: "final",
            parts,
            metadata: {
              finish_reason: (event.finish_reason as any) ?? null,
              sources: (event.sources as any[]) ?? [],
              token_usage: event.token_usage
                ? {
                    input_tokens: (event.token_usage as any).input_tokens,
                    output_tokens: (event.token_usage as any).output_tokens,
                    total_tokens: (event.token_usage as any).total_tokens,
                  }
                : null,
              extras: {},
            },
          });
          break;
        }

        case "tool_call": {
          emit({
            session_id: sessionId,
            exchange_id: exchangeId,
            rank: rankRef.current++,
            timestamp: ts,
            role: "assistant",
            channel: "tool_call",
            parts: [
              {
                type: "tool_call",
                call_id: event.call_id,
                name: event.tool_name,
                args: (event.arguments ?? {}) as { [key: string]: any },
              },
            ],
          });
          break;
        }

        case "tool_result": {
          const toolResultParts: ChatMessage["parts"] = [
            {
              type: "tool_result",
              call_id: event.call_id,
              ok: !event.is_error,
              content: event.content ?? "",
            },
          ];
          if (event.ui_parts?.length) {
            for (const p of event.ui_parts) {
              toolResultParts.push(p as ChatMessage["parts"][number]);
            }
          }
          emit({
            session_id: sessionId,
            exchange_id: exchangeId,
            rank: rankRef.current++,
            timestamp: ts,
            role: "tool",
            channel: "tool_result",
            parts: toolResultParts,
          });
          break;
        }

        case "awaiting_human": {
          const hitl: AwaitingHumanEvent = {
            type: "awaiting_human",
            session_id: sessionId,
            exchange_id: exchangeId,
            payload: {
              title: event.request.title ?? null,
              question: event.request.question ?? null,
              choices:
                event.request.choices?.map((c) => ({
                  id: c.id,
                  label: c.label,
                  description: c.description ?? null,
                  default: c.default ?? null,
                })) ?? null,
              free_text: event.request.free_text ?? false,
              stage: event.request.stage ?? null,
              checkpoint_id: event.request.checkpoint_id ?? null,
              metadata: event.request.metadata ?? null,
            },
          };
          onAwaitingHuman?.(hitl);
          break;
        }

        case "turn_persisted": {
          onBindDraftAgentToSessionId?.(event.session_id);
          onTurnPersisted?.(event.session_id);
          break;
        }

        case "node_error": {
          onError?.(`Agent error in ${event.routed_to}/${event.node_id}: ${event.error_message}`);
          break;
        }

        case "status":
          console.debug("[useChatSse] status:", event.status, event.detail);
          break;
      }
    },
    [onAwaitingHuman, onBindDraftAgentToSessionId, onTurnPersisted, onError],
  );

  const streamToMessages = useCallback(
    async (
      body: object,
      executeStreamUrl: string,
      token: string,
      exchangeId: string,
      sessionId: string,
      signal: AbortSignal,
    ): Promise<void> => {
      const url = new URL(executeStreamUrl, window.location.origin);
      const response = await fetch(url.toString(), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
        signal,
      });

      if (!response.ok) {
        const text = await response.text().catch(() => String(response.status));
        throw new Error(`Runtime ${response.status}: ${text}`);
      }

      if (!response.body) throw new Error("Empty response body from runtime");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      const rankRef = { current: messagesRef.current.length + 1 };
      const deltaRankRef: { current: number | null } = { current: null };

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const blocks = buf.split("\n\n");
          buf = blocks.pop() ?? "";
          for (const block of blocks) {
            const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
            if (!dataLine) continue;
            const raw = dataLine.slice(6).trim();
            if (!raw || raw === "[DONE]") continue;
            let event: AnyRuntimeEvent;
            try {
              event = JSON.parse(raw) as AnyRuntimeEvent;
            } catch {
              console.warn("[useChatSse] Failed to parse SSE frame:", raw);
              continue;
            }
            processEvent(event, { exchangeId, sessionId, rankRef, deltaRankRef });
          }
        }
      } finally {
        reader.releaseLock();
      }
    },
    [processEvent],
  );

  const send = useCallback(
    async (input: string, sessionId: string | null, runtimeContext?: RuntimeContext) => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      await KeyCloakService.ensureFreshToken(30);
      const token = KeyCloakService.GetToken() ?? "";

      const prep = await prepareExecution({ teamId, agentInstanceId }).unwrap();
      setEffectiveChatOptions(prep.effective_chat_options ?? null);

      const effectiveContext: RuntimeContext = {
        ...(runtimeContext ?? {}),
        ...(prep.context_prompt_text != null ? { context_prompt_text: prep.context_prompt_text } : {}),
      };

      const exchangeId = uuidv4();
      const effectiveSessionId = sessionId ?? "draft";

      // Optimistic user message for immediate UI feedback.
      const userMsg: ChatMessage = {
        session_id: effectiveSessionId,
        exchange_id: exchangeId,
        rank: messagesRef.current.length,
        timestamp: new Date().toISOString(),
        role: "user",
        channel: "final",
        parts: [{ type: "text", text: input }],
        metadata: { extras: { optimistic_user: true } },
      };
      messagesRef.current = upsertOne(messagesRef.current, userMsg);
      setMessages([...messagesRef.current]);
      setWaitResponse(true);

      try {
        await streamToMessages(
          {
            agent_instance_id: agentInstanceId,
            execution_grant: prep.execution_grant,
            input,
            session_id: sessionId,
            runtime_context: effectiveContext,
          },
          prep.execute_stream_url,
          token,
          exchangeId,
          effectiveSessionId,
          ac.signal,
        );
      } catch (err) {
        if ((err as Error)?.name !== "AbortError") {
          onError?.(`Streaming failed: ${(err as Error).message ?? String(err)}`);
        }
      } finally {
        if (!ac.signal.aborted) {
          setWaitResponse(false);
        }
      }
    },
    [agentInstanceId, teamId, prepareExecution, streamToMessages, onError],
  );

  const sendHitlResume = useCallback(
    async (pending: AwaitingHumanEvent, answer: string | boolean | undefined, freeText?: string) => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      await KeyCloakService.ensureFreshToken(30);
      const token = KeyCloakService.GetToken() ?? "";

      const prep = await prepareExecution({ teamId, agentInstanceId }).unwrap();
      setEffectiveChatOptions(prep.effective_chat_options ?? null);

      const sessionId = pending.session_id;
      const exchangeId = uuidv4();
      const hitlPayload = pending.payload as {
        choices?: { id: string }[];
        checkpoint_id?: string | null;
      };
      const hasChoices = Array.isArray(hitlPayload?.choices) && hitlPayload.choices.length > 0;
      const normalizedFreeText = typeof freeText === "string" ? freeText.trim() || undefined : undefined;
      const answerValue = !hasChoices && normalizedFreeText ? normalizedFreeText : answer;

      setWaitResponse(true);

      try {
        await streamToMessages(
          {
            agent_instance_id: agentInstanceId,
            execution_grant: prep.execution_grant,
            session_id: sessionId,
            checkpoint_id: hitlPayload?.checkpoint_id ?? null,
            resume_payload: {
              answer: answerValue,
              choice_id: hasChoices && typeof answer === "string" ? answer : undefined,
              text: hasChoices ? normalizedFreeText : undefined,
            },
          },
          prep.execute_stream_url,
          token,
          exchangeId,
          sessionId,
          ac.signal,
        );
      } catch (err) {
        if ((err as Error)?.name !== "AbortError") {
          onError?.(`HITL resume failed: ${(err as Error).message ?? String(err)}`);
        }
      } finally {
        if (!ac.signal.aborted) {
          setWaitResponse(false);
        }
      }
    },
    [agentInstanceId, teamId, prepareExecution, streamToMessages, onError],
  );

  return {
    messages,
    waitResponse,
    effectiveChatOptions,
    send,
    sendHitlResume,
    abort,
    reset,
    replaceAllMessages,
  };
}
