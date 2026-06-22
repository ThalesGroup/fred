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

import { useCallback, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

import { KeyCloakService } from "../../../security/KeycloakService";
import type { AwaitingHumanEvent, ChatMessage, FinishReason } from "../../../slices/agentic/agenticOpenApi";
import type { EffectiveChatOptions } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type {
  AssistantDeltaRuntimeEvent,
  AwaitingHumanRuntimeEvent,
  FinalRuntimeEvent,
  NodeErrorRuntimeEvent,
  RuntimeContext,
  RuntimeErrorEvent,
  StatusRuntimeEvent,
  ThoughtDeltaEvent,
  ThoughtEndEvent,
  ThoughtStartEvent,
  ToolCallRuntimeEvent,
  ToolResultRuntimeEvent,
  TurnPersistedEvent,
} from "../../../slices/runtime/runtimeOpenApi";
import { upsertOne } from "./chatSseUtils";

// ── SSE event union ───────────────────────────────────────────────────────────

type AnyRuntimeEvent =
  | ({ kind: "assistant_delta" } & AssistantDeltaRuntimeEvent)
  | ({ kind: "awaiting_human" } & AwaitingHumanRuntimeEvent)
  | ({ kind: "final" } & FinalRuntimeEvent)
  | ({ kind: "node_error" } & NodeErrorRuntimeEvent)
  | ({ kind: "status" } & StatusRuntimeEvent)
  | ({ kind: "thought_start" } & ThoughtStartEvent)
  | ({ kind: "thought_delta" } & ThoughtDeltaEvent)
  | ({ kind: "thought_end" } & ThoughtEndEvent)
  | ({ kind: "tool_call" } & ToolCallRuntimeEvent)
  | ({ kind: "tool_result" } & ToolResultRuntimeEvent)
  | ({ kind: "turn_persisted" } & TurnPersistedEvent)
  | ({ kind: "execution_error" } & RuntimeErrorEvent);

// ── Public API ────────────────────────────────────────────────────────────────

export type ChatSseCallbacks = {
  onBindDraftAgentToSessionId?: (sessionId: string) => void;
  onTurnPersisted?: (sessionId: string) => void;
  onAwaitingHuman?: (event: AwaitingHumanEvent) => void;
  onError?: (message: string) => void;
  /**
   * Ordering barrier awaited immediately before prepare-execution. Lets the
   * caller flush any in-flight session writes (row creation, context-prompt
   * PATCH) so the control-plane resolves chat context from the freshly
   * persisted session instead of a stale/empty set on the first turn.
   */
  flushPendingWrites?: () => Promise<void>;
};

/**
 * SSE chat transport for managed agent instances.
 *
 * - Calls control-plane /prepare-execution before each send to obtain a short-lived ExecutionGrant.
 * - POSTs to the runtime execute_stream_url using fetch() with SSE response parsing.
 * - Maps RuntimeEvent frames (assistant_delta, final, tool_call, …) onto a flat ChatMessage[].
 * - Supports HITL resume via sendHitlResume().
 */
export function useChatSse(
  params: {
    agentInstanceId: string;
    teamId: string;
    /** UI language forwarded to prepare-execution so platform `default:` context
     *  prompts resolve in the same language shown in the picker. */
    lang: string;
  } & ChatSseCallbacks,
) {
  const {
    agentInstanceId,
    teamId,
    lang,
    onBindDraftAgentToSessionId,
    onTurnPersisted,
    onAwaitingHuman,
    onError,
    flushPendingWrites,
  } = params;

  const [prepareExecution] =
    usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation();

  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);
  const thoughtBufsRef = useRef<
    Map<
      string,
      {
        rank: number;
        text: string;
        phase: string;
        title: string | null | undefined;
        source: string | null | undefined;
      }
    >
  >(new Map());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [waitResponse, setWaitResponse] = useState(false);
  const [effectiveChatOptions, setEffectiveChatOptions] = useState<EffectiveChatOptions | null>(null);

  const setAll = useCallback((next: ChatMessage[]) => {
    messagesRef.current = next;
    setMessages(next);
  }, []);

  const reset = useCallback(() => {
    console.debug("[useChatSse] reset() called — clearing all state");
    abortRef.current?.abort();
    abortRef.current = null;
    setWaitResponse(false);
    thoughtBufsRef.current.clear();
    setAll([]);
    setEffectiveChatOptions(null);
  }, [setAll]);
  const replaceAllMessages = useCallback((msgs: ChatMessage[]) => setAll(msgs), [setAll]);

  const abort = useCallback(() => {
    console.debug("[useChatSse] abort() called — clearing waitResponse");
    abortRef.current?.abort();
    abortRef.current = null;
    setWaitResponse(false);
  }, []);

  // Parse one SSE block and dispatch to ChatMessage state + callbacks.
  // Captures stable refs so this function itself stays stable across renders.
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

      // Emit one streaming "thought" trace message. The start/delta/end handlers
      // share the same envelope and differ only in rank, accumulated text, and extras.
      const emitThought = (rank: number, text: string, extras: Record<string, unknown>) =>
        emit({
          session_id: sessionId,
          exchange_id: exchangeId,
          rank,
          timestamp: ts,
          role: "assistant",
          channel: "thought",
          parts: [{ type: "text", text }],
          metadata: { extras },
        });

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
              finish_reason: (event.finish_reason as FinishReason | null) ?? null,
              sources: event.sources ?? [],
              token_usage: event.token_usage
                ? {
                    input_tokens: event.token_usage["input_tokens"] ?? 0,
                    output_tokens: event.token_usage["output_tokens"] ?? 0,
                    total_tokens: event.token_usage["total_tokens"] ?? 0,
                  }
                : null,
              extras: {},
            },
          });
          break;
        }

        case "tool_call": {
          console.debug(`[useChatSse] tool_call name=${event.tool_name} call_id=${event.call_id}`);
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
                args: event.arguments ?? {},
              },
            ],
          });
          break;
        }

        case "tool_result": {
          console.debug(`[useChatSse] tool_result call_id=${event.call_id} ok=${!event.is_error}`);
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

        case "thought_start": {
          const rank = rankRef.current++;
          console.debug(
            `[useChatSse] thought_start id=${event.thought_id} phase=${event.phase} title="${event.title ?? ""}"`,
          );
          thoughtBufsRef.current.set(event.thought_id, {
            rank,
            text: "",
            phase: event.phase,
            title: event.title,
            source: event.source,
          });
          emitThought(rank, "", {
            thought_id: event.thought_id,
            phase: event.phase,
            title: event.title ?? null,
            source: event.source ?? null,
            streaming_delta: true,
          });
          break;
        }

        case "thought_delta": {
          const buf = thoughtBufsRef.current.get(event.thought_id);
          if (!buf) break;
          buf.text += event.delta;
          emitThought(buf.rank, buf.text, {
            thought_id: event.thought_id,
            phase: buf.phase,
            title: buf.title ?? null,
            source: buf.source ?? null,
            streaming_delta: true,
          });
          break;
        }

        case "thought_end": {
          const buf = thoughtBufsRef.current.get(event.thought_id);
          console.debug(
            `[useChatSse] thought_end id=${event.thought_id} buf_found=${!!buf} open_ids=[${[...thoughtBufsRef.current.keys()].join(",")}]`,
          );
          if (!buf) break;
          thoughtBufsRef.current.delete(event.thought_id);
          emitThought(buf.rank, buf.text, {
            thought_id: event.thought_id,
            phase: buf.phase,
            title: buf.title ?? null,
            source: buf.source ?? null,
            conclusion: event.conclusion ?? null,
            duration_ms: event.duration_ms ?? null,
          });
          break;
        }

        case "execution_error": {
          console.error(`[useChatSse] execution_error received — ${event.message ?? "unknown error"}`);
          // Close any thoughts that are still open so they don't blink forever.
          for (const [thoughtId, buf] of thoughtBufsRef.current.entries()) {
            emit({
              session_id: sessionId,
              exchange_id: exchangeId,
              rank: buf.rank,
              timestamp: ts,
              role: "assistant",
              channel: "thought",
              parts: [{ type: "text", text: buf.text }],
              metadata: {
                extras: {
                  thought_id: thoughtId,
                  phase: buf.phase,
                  title: buf.title ?? null,
                  conclusion: "Error",
                  duration_ms: null,
                },
              },
            });
          }
          thoughtBufsRef.current.clear();
          onError?.(event.message ?? "Agent execution error");
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
      console.debug(
        `[useChatSse] streamToMessages — resolved URL="${url.toString()}" signal.aborted=${signal.aborted}`,
      );
      const response = await fetch(url.toString(), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
        signal,
      });

      console.debug(`[useChatSse] fetch response — status=${response.status} ok=${response.ok}`);
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
      const sendId = Math.random().toString(36).slice(2, 8);
      console.debug(
        `[useChatSse][${sendId}] send() START — sessionId=${sessionId ?? "null"} input="${input.slice(0, 40)}"`,
      );

      if (abortRef.current) {
        console.debug(`[useChatSse][${sendId}] aborting previous in-flight request`);
        abortRef.current.abort();
      }
      const ac = new AbortController();
      abortRef.current = ac;

      await KeyCloakService.ensureFreshToken(30);
      const token = KeyCloakService.GetToken() ?? "";

      // Ordering barrier: any in-flight session row creation and context-prompt
      // PATCH must commit before prepare-execution reads them, otherwise the
      // first turn is prepared from a stale/empty prompt set while the composer
      // chip already shows the new selection. No-op latency when already settled.
      await flushPendingWrites?.();

      console.debug(`[useChatSse][${sendId}] calling prepareExecution...`);
      // Pass the session id so the control-plane can resolve and concatenate the
      // session's attached chat-context prompts into `context_prompt_text`, and
      // the UI lang so platform `default:` prompts resolve in the picker's
      // language (library prompts are language-agnostic).
      const prep = await prepareExecution({
        teamId,
        agentInstanceId,
        lang,
        ...(sessionId ? { sessionId } : {}),
      }).unwrap();
      console.debug(
        `[useChatSse][${sendId}] prepareExecution done — aborted=${ac.signal.aborted} execute_stream_url=${prep.execute_stream_url}`,
      );
      setEffectiveChatOptions(prep.effective_chat_options ?? null);

      const effectiveContext: RuntimeContext = {
        ...(runtimeContext ?? {}),
        ...(prep.context_prompt_text != null ? { context_prompt_text: prep.context_prompt_text } : {}),
      };

      const exchangeId = uuidv4();
      const effectiveSessionId = sessionId ?? "draft";

      // Optimistic user message for immediate UI feedback before the first SSE frame.
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
      console.debug(`[useChatSse][${sendId}] waitResponse=true — starting streamToMessages`);

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
        console.debug(`[useChatSse][${sendId}] streamToMessages completed normally`);
      } catch (err) {
        const name = (err as Error)?.name;
        const msg = (err as Error)?.message ?? String(err);
        if (name === "AbortError") {
          console.debug(`[useChatSse][${sendId}] streamToMessages aborted (AbortError) — swallowed`);
        } else {
          console.error(`[useChatSse][${sendId}] streamToMessages error — ${name}: ${msg}`);
          onError?.(`Streaming failed: ${msg}`);
        }
      } finally {
        console.debug(
          `[useChatSse][${sendId}] finally — ac.signal.aborted=${ac.signal.aborted} → will ${ac.signal.aborted ? "NOT" : ""} clear waitResponse`,
        );
        if (!ac.signal.aborted) {
          setWaitResponse(false);
        }
      }
    },
    [agentInstanceId, teamId, lang, prepareExecution, streamToMessages, onError, flushPendingWrites],
  );

  const sendHitlResume = useCallback(
    async (pending: AwaitingHumanEvent, answer: string | boolean | undefined, freeText?: string) => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      await KeyCloakService.ensureFreshToken(30);
      const token = KeyCloakService.GetToken() ?? "";

      const prep = await prepareExecution({ teamId, agentInstanceId, action: "resume" }).unwrap();
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
