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
import { useDispatch } from "react-redux";
import { useTranslation } from "react-i18next";
import { v4 as uuidv4 } from "uuid";

import { setCapabilityBaseUrls } from "../../../common/capabilityRoutingSlice";
import { KeyCloakService } from "../../../security/KeycloakService";
import type { ChatControlDescriptor, ExecutionPreparation } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation } from "../../../slices/controlPlane/controlPlaneOpenApi";
import type {
  AssistantDeltaRuntimeEvent,
  AwaitingHumanRuntimeEvent,
  ChatMessage,
  FinalRuntimeEvent,
  HumanInputRequest,
  NodeErrorRuntimeEvent,
  RuntimeContext,
  RuntimeErrorEvent,
  RuntimeExecuteRequest,
  StatusRuntimeEvent,
  ThoughtDeltaEvent,
  ThoughtEndEvent,
  ThoughtStartEvent,
  ToolCallRuntimeEvent,
  ToolResultRuntimeEvent,
  TurnPersistedEvent,
} from "../../../slices/runtime/runtimeOpenApi";
import { upsertOne } from "./chatSseUtils";
import {
  mergeContextPromptText,
  mergeReasoningActivation,
  mergeRoutingPolicy,
  parseSseFrames,
} from "../utils/runtimeStream";
import { personalTeamId } from "../../components/shared/utils/teamId";

// The UI may still carry the bare "personal" placeholder (teamId.ts) in the URL
// before bootstrap resolves the real per-user id. The control-plane resolves
// that alias server-side (teams/system.py), but fred-runtime's OpenFGA check
// does not — it authorizes the raw team_id in runtime_context. Canonicalize
// before it reaches the runtime, mirroring usePipelineRun.ts.
function canonicalizeRuntimeTeamId(teamId: string): string {
  return teamId === "personal" ? personalTeamId(KeyCloakService.GetUserId() ?? "") : teamId;
}

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

// ── HITL event/payload (#2216) ──────────────────────────────────────────────
//
// Explicit types based on the generated runtime `HumanInputRequest` contract.
// `checkpoint_id`/`interrupt_id` stay independently typed here, exactly one
// populated per runtime (legacy Graph V2 vs ReAct V2) — never aliased for
// each other.

export type RuntimeHitlPayload = HumanInputRequest;

export type RuntimeAwaitingHumanEvent = {
  type?: "awaiting_human";
  session_id: string;
  exchange_id: string;
  payload: RuntimeHitlPayload;
};

// ── Public API ────────────────────────────────────────────────────────────────

export type ChatSseCallbacks = {
  onBindDraftAgentToSessionId?: (sessionId: string) => void;
  onTurnPersisted?: (sessionId: string) => void;
  onAwaitingHuman?: (event: RuntimeAwaitingHumanEvent) => void;
  onError?: (message: string) => void;
  /**
   * Fires the instant this turn actually starts — right before the
   * optimistic user message is created and streaming begins, once
   * prepare-execution has succeeded. Callers use this (not a fixed point
   * before send() is even called) to clear composer input/attachments, so a
   * prepare-execution failure (flush barrier, 404/503/network) never wipes
   * text or attachments the user still needs for a retry. Deliberately a
   * distinct, positive-only signal rather than a second error callback: by
   * default (this never firing) nothing has been cleared, so there is
   * nothing to "undo" on failure — no `onPreparationFailed` needed, `onError`
   * already covers showing the failure itself.
   */
  onTurnStarted?: () => void;
  /**
   * Ordering barrier awaited immediately before prepare-execution, keyed on
   * the session id this turn is about to use. Lets the caller flush any
   * in-flight session writes (row creation, context-prompt PATCH) for THAT
   * session so the control-plane resolves chat context from the freshly
   * persisted session instead of a stale/empty set on the first turn.
   *
   * Resolves `false` when any tracked write failed — `send()` must then abort
   * before calling prepare-execution rather than proceed against a session
   * the caller's own writes never actually committed to.
   */
  flushPendingWrites?: (sessionId: string) => Promise<boolean>;
};

/**
 * SSE chat transport for managed agent instances.
 *
 * - Calls control-plane /prepare-execution before each send to resolve the runtime URLs
 *   and context prompt (no signed grant — the pod authorizes via Keycloak JWT + OpenFGA).
 * - POSTs to the runtime execute_stream_url using fetch() with SSE response parsing.
 * - Maps RuntimeEvent frames (assistant_delta, final, tool_call, …) onto a flat ChatMessage[].
 * - Supports HITL resume via sendHitlResume().
 */
export function useChatSse(
  params: {
    agentInstanceId: string;
    teamId: string;
  } & ChatSseCallbacks,
) {
  const {
    agentInstanceId,
    teamId,
    onBindDraftAgentToSessionId,
    onTurnPersisted,
    onAwaitingHuman,
    onError,
    onTurnStarted,
    flushPendingWrites,
  } = params;

  const [prepareExecution] =
    usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation();
  const dispatch = useDispatch();
  const { i18n } = useTranslation();

  const abortRef = useRef<AbortController | null>(null);
  // Synchronous reentrancy lock for the preflight phase of send() (token
  // refresh → flush → prepare-execution, i.e. everything before
  // onTurnStarted). Checked and set BEFORE any await, so two Enters fired
  // back to back can never both reach prepare-execution — the second is
  // dropped outright, not turned into a cancel/replace of the first. Once
  // the preflight succeeds and the turn genuinely starts, this is released
  // and the existing "a new send() aborts the current stream" behavior
  // (via abortRef) takes back over, unchanged.
  //
  // Holds the OWNING attempt's own AbortController, not a bare boolean —
  // ownership matters because an aborted attempt can resume its cleanup
  // (releasePreflightLock, below) arbitrarily late, well after a later
  // send() has already become the current owner. A boolean flag would let
  // that stale cleanup wrongly clear the NEW owner's lock (the exact bug: A
  // aborted, B starts, A's suspended await resumes and releases B's lock,
  // letting a third send() sneak in concurrently with B). Comparing against
  // `ac` — this attempt's own controller — makes a late cleanup a no-op
  // once someone else owns the slot.
  const preflightOwnerRef = useRef<AbortController | null>(null);
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
  // Chat-turn controls (CAPAB-01 #1976, RFC §3.3/§3.7) — supersedes the retired
  // `effectiveChatOptions`. Populated by prepare-execution; the composer
  // resolves each descriptor's `widget` id against the chat-turn-control
  // registry (plugin first, then the capability-agnostic stock kit).
  const [chatControls, setChatControls] = useState<ChatControlDescriptor[]>([]);

  const setAll = useCallback((next: ChatMessage[]) => {
    messagesRef.current = next;
    setMessages(next);
  }, []);

  // Applies a prepare-execution response's session-scoped side effects, shared
  // by the eager open-time prep, every send(), and HITL resume.
  const applyPreparation = useCallback(
    (prep: ExecutionPreparation) => {
      setChatControls(prep.chat_controls ?? []);
      // #1979: publish the instance-bound capability route base URLs so each
      // capability's generated RTK slice can reach its pod routes directly.
      dispatch(setCapabilityBaseUrls(prep.capability_base_urls ?? {}));
    },
    [dispatch],
  );

  const reset = useCallback(() => {
    console.debug("[useChatSse] reset() called — clearing all state");
    abortRef.current?.abort();
    abortRef.current = null;
    // An explicit reset always cancels whatever attempt currently owns the
    // lock (if any) and immediately frees the slot for the next send() —
    // unconditional, unlike releasePreflightLock's ownership-checked release,
    // because this IS the current owner's cancellation, issued from outside.
    preflightOwnerRef.current = null;
    setWaitResponse(false);
    thoughtBufsRef.current.clear();
    setAll([]);
    setChatControls([]);
  }, [setAll]);
  const replaceAllMessages = useCallback((msgs: ChatMessage[]) => setAll(msgs), [setAll]);

  const abort = useCallback(() => {
    console.debug("[useChatSse] abort() called — clearing waitResponse");
    abortRef.current?.abort();
    abortRef.current = null;
    // Otherwise an explicit Stop during preflight would leave the lock held
    // forever, blocking every subsequent Send. Unconditional for the same
    // reason as in reset() above.
    preflightOwnerRef.current = null;
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
          // `final` is the only reliable end-of-turn signal on this stream (see
          // agent_app.py's `execute_stream` docstring) — the contract's
          // `turn_persisted` event is defined but never actually emitted, so the
          // session's activity timestamp/list position must be refreshed here
          // instead of waiting on that dead event.
          onTurnPersisted?.(sessionId);
          // Authoritative frame — replaces any accumulated delta at the same rank.
          const rank = deltaRankRef.current ?? rankRef.current++;
          const parts: ChatMessage["parts"] = [{ type: "text", text: event.content ?? "" }];
          if (event.ui_parts?.length) {
            for (const p of event.ui_parts) {
              parts.push(p as unknown as ChatMessage["parts"][number]);
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
              model: event.model_name ?? null,
              finish_reason: event.finish_reason ?? null,
              sources: event.sources ?? [],
              token_usage: event.token_usage
                ? {
                    input_tokens: event.token_usage["input_tokens"] ?? 0,
                    output_tokens: event.token_usage["output_tokens"] ?? 0,
                    total_tokens: event.token_usage["total_tokens"] ?? 0,
                    cache_read_tokens: event.token_usage["cache_read_tokens"],
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
            metadata: event.token_usage
              ? {
                  token_usage: {
                    input_tokens: event.token_usage["input_tokens"] ?? 0,
                    output_tokens: event.token_usage["output_tokens"] ?? 0,
                    total_tokens: event.token_usage["total_tokens"] ?? 0,
                    cache_read_tokens: event.token_usage["cache_read_tokens"],
                  },
                }
              : undefined,
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
              latency_ms: event.latency_ms ?? null,
            },
          ];
          if (event.ui_parts?.length) {
            for (const p of event.ui_parts) {
              toolResultParts.push(p as unknown as ChatMessage["parts"][number]);
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
          const hitl: RuntimeAwaitingHumanEvent = {
            type: "awaiting_human",
            session_id: sessionId,
            exchange_id: exchangeId,
            payload: {
              title: event.request.title ?? null,
              question: event.request.question ?? null,
              choices: event.request.choices ?? [],
              free_text: event.request.free_text ?? false,
              stage: event.request.stage ?? null,
              // ReAct V2's occurrence identity (#2216) — LangGraph's own
              // Interrupt.id, required back on resume so the backend can
              // reject a stale/duplicate response. checkpoint_id is a
              // DIFFERENT field (legacy Graph V2's real storage id); never
              // aliased. Both are explicitly typed on `RuntimeHitlPayload`.
              interrupt_id: event.request.interrupt_id ?? null,
              checkpoint_id: event.request.checkpoint_id ?? null,
              metadata: event.request.metadata,
              // Tool calls this prompt gates (#2177 batching — one combined
              // interrupt can cover several calls at once). Lets the trace
              // correlate every one of them, not just a single call_id.
              pending_calls: event.request.pending_calls ?? [],
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
          // Persist the crash in the chain of thought as an error entry (not
          // just the transient toast): a trailing error row whose raw message is
          // browsable in the trace drawer. The toast still fires for the
          // immediate signal.
          emit({
            session_id: sessionId,
            exchange_id: exchangeId,
            rank: rankRef.current++,
            timestamp: ts,
            role: "assistant",
            channel: "error",
            parts: [{ type: "text", text: event.message ?? "Agent execution error" }],
          });
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
      body: RuntimeExecuteRequest,
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

      const rankRef = { current: messagesRef.current.length + 1 };
      const deltaRankRef: { current: number | null } = { current: null };

      const frames = parseSseFrames<AnyRuntimeEvent>(response.body, (raw) =>
        console.warn("[useChatSse] Failed to parse SSE frame:", raw),
      );
      for await (const event of frames) {
        processEvent(event, { exchangeId, sessionId, rankRef, deltaRankRef });
      }
    },
    [processEvent],
  );

  const send = useCallback(
    async (
      input: string,
      sessionId: string | null,
      runtimeContext?: RuntimeContext,
      turnOptions?: RuntimeExecuteRequest["turn_options"],
    ) => {
      const sendId = Math.random().toString(36).slice(2, 8);
      console.debug(
        `[useChatSse][${sendId}] send() START — sessionId=${sessionId ?? "null"} input="${input.slice(0, 40)}"`,
      );

      // Synchronous reentrancy lock — checked and acquired before the first
      // await. A second Enter fired while this call is still preflighting
      // is dropped here, outright: not cancelled, not merged, not queued.
      if (preflightOwnerRef.current) {
        console.debug(`[useChatSse][${sendId}] IGNORED — a send() is already preflighting`);
        return;
      }

      if (abortRef.current) {
        console.debug(`[useChatSse][${sendId}] aborting previous in-flight request`);
        abortRef.current.abort();
      }
      const ac = new AbortController();
      abortRef.current = ac;
      preflightOwnerRef.current = ac;
      // Immediately non-reentrant, not only once prepare-execution succeeds —
      // the send button disables right away, matching the synchronous lock.
      setWaitResponse(true);

      // Releases the preflight lock on every early-return path below —
      // INCLUDING every error path (a rejected await must never leave the
      // lock or waitResponse stuck, or the composer becomes permanently
      // unusable). Ownership-checked: only touches preflightOwnerRef/
      // abortRef/waitResponse if THIS attempt (`ac`) still owns them. An
      // explicit abort()/reset() (Stop button, or a later attempt that took
      // over after this one was cancelled) may already have handed the slot
      // to someone else — this attempt's cleanup, however late it resumes,
      // must then be a complete no-op on shared state.
      const releasePreflightLock = () => {
        if (preflightOwnerRef.current === ac) {
          preflightOwnerRef.current = null;
        }
        if (abortRef.current === ac) {
          abortRef.current = null;
          setWaitResponse(false);
        }
      };

      // Uniform handling for every preflight-stage failure (token refresh,
      // write-barrier flush, prepare-execution + its synchronous response
      // processing): release this attempt's own state, then — unless the
      // failure is really just this attempt having been cancelled (Stop /
      // reset while the stage was in flight, in which case no toast is
      // shown for an intentional cancellation) — surface it via onError.
      // Always returns normally: no stage here is allowed to let a
      // rejection escape send() as an unhandled promise rejection, since
      // callers (handleSend) do not await/catch send()'s own promise.
      const failPreflight = (stage: string, err: unknown) => {
        releasePreflightLock();
        if (ac.signal.aborted) {
          console.debug(`[useChatSse][${sendId}] ${stage} settled after cancellation — no toast`);
          return;
        }
        const msg = (err as Error)?.message ?? String(err);
        console.error(`[useChatSse][${sendId}] ${stage} failed — ${msg}`);
        onError?.(`Could not prepare this turn: ${msg}`);
      };

      try {
        await KeyCloakService.ensureFreshToken(30);
      } catch (err) {
        failPreflight("token refresh", err);
        return;
      }
      if (ac.signal.aborted) {
        console.debug(`[useChatSse][${sendId}] aborted during token refresh — never reaching onTurnStarted`);
        releasePreflightLock();
        return;
      }
      const token = KeyCloakService.GetToken() ?? "";

      // Ordering barrier: any in-flight session row creation and context-prompt
      // PATCH must commit before prepare-execution reads them, otherwise the
      // first turn is prepared from a stale/empty prompt set while the composer
      // chip already shows the new selection. No-op latency when already settled.
      // A `false` result means a tracked write failed — never call
      // prepare-execution against a session the caller's writes never actually
      // committed to; the failure already surfaced its own toast at the write
      // site, this just stops the turn from starting.
      let writesCommitted: boolean | undefined;
      try {
        writesCommitted = await flushPendingWrites?.(sessionId ?? "");
      } catch (err) {
        failPreflight("session write flush", err);
        return;
      }
      if (ac.signal.aborted) {
        console.debug(`[useChatSse][${sendId}] aborted during flush — never reaching onTurnStarted`);
        releasePreflightLock();
        return;
      }
      if (writesCommitted === false) {
        console.debug(`[useChatSse][${sendId}] aborting — a pending session write failed`);
        releasePreflightLock();
        return;
      }

      console.debug(`[useChatSse][${sendId}] calling prepareExecution...`);
      // Pass the session id so the control-plane can resolve and concatenate the
      // session's attached chat-context prompts into `context_prompt_text`.
      let prep: ExecutionPreparation;
      let effectiveContext: RuntimeContext;
      let exchangeId: string;
      let effectiveSessionId: string;
      try {
        prep = await prepareExecution({
          teamId,
          agentInstanceId,
          ...(sessionId ? { sessionId } : {}),
        }).unwrap();
        if (ac.signal.aborted) {
          console.debug(`[useChatSse][${sendId}] aborted right after prepare-execution — never reaching onTurnStarted`);
          releasePreflightLock();
          return;
        }
        console.debug(
          `[useChatSse][${sendId}] prepareExecution done — aborted=${ac.signal.aborted} execute_stream_url=${prep.execute_stream_url}`,
        );
        applyPreparation(prep);

        // RUNTIME-07 rev. 2: the pod authorizes the user against OpenFGA on the
        // team carried in runtime_context (no signed grant). Always include team_id.
        // `language` rides the same way: it drives backend-rendered copy (e.g.
        // FredHitlMiddleware's approval prompt), which otherwise defaults to
        // English regardless of the UI's own locale — read live off i18next
        // (not memoized) so a mid-session language switch takes effect on the
        // very next turn, matching the existing pattern for voice transcription
        // (ManagedChatPage.tsx's handleTranscribeAudio).
        effectiveContext = mergeReasoningActivation(
          mergeRoutingPolicy(
            mergeContextPromptText(
              {
                ...(runtimeContext ?? {}),
                team_id: canonicalizeRuntimeTeamId(teamId),
                language: i18n.language?.split("-")[0] || undefined,
              },
              prep.context_prompt_text,
            ),
            prep.chat_default_profile_id,
            prep.operation_route_rules,
          ),
          prep.reasoning_enabled_model_ids,
        );
        exchangeId = uuidv4();
        effectiveSessionId = sessionId ?? "draft";
      } catch (err) {
        // Was previously unguarded: a rejection here (e.g. an unknown/foreign
        // session_id, an unreachable runtime source) propagated as an
        // unhandled promise rejection — silently dropping the turn with no
        // toast and `waitResponse` never set, so the composer looked idle
        // with no sign the message never sent.
        failPreflight("prepare-execution", err);
        return;
      }

      // The turn is now genuinely starting. Preflight is over — release the
      // reentrancy lock so the existing "a new send() replaces the current
      // stream" behavior (via abortRef, below) governs from here on,
      // unchanged. This is also the caller's cue to clear composer
      // input/attachments; any earlier failure or cancellation returned
      // above without ever reaching this point, leaving them untouched.
      if (preflightOwnerRef.current === ac) {
        preflightOwnerRef.current = null;
      }
      onTurnStarted?.();

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
      console.debug(`[useChatSse][${sendId}] starting streamToMessages`);

      try {
        await streamToMessages(
          {
            agent_instance_id: agentInstanceId,
            input,
            session_id: sessionId,
            runtime_context: effectiveContext,
            ...(turnOptions ? { turn_options: turnOptions } : {}),
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
    [
      agentInstanceId,
      teamId,
      prepareExecution,
      streamToMessages,
      onError,
      onTurnStarted,
      flushPendingWrites,
      applyPreparation,
      i18n,
    ],
  );

  const sendHitlResume = useCallback(
    async (pending: RuntimeAwaitingHumanEvent, answer: string | boolean | undefined, freeText?: string) => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      // Takes over `abortRef` from outside, exactly like abort()/reset() do —
      // so it must also unconditionally free preflightOwnerRef the same way
      // they do. Without this, a send() still preflighting when this fires
      // keeps "owning" preflightOwnerRef until its own stale continuation
      // happens to resume and notice it was aborted — which can be
      // arbitrarily late, since prepare-execution isn't actually
      // signal-cancellable — silently dropping every send() attempt made in
      // the meantime.
      preflightOwnerRef.current = null;

      // Optimistic cancel: flip every tool call this HITL prompt gated from
      // "running" straight to a cancelled state, without waiting for the resume
      // round-trip (which may even crash before resolving them). Each error
      // tool_result flagged `cancelled_by_user` pairs with the dangling
      // tool_call by call_id; a real result later would simply supersede it.
      if (answer === "cancel") {
        const cancelTs = new Date().toISOString();
        const rankBase = Date.now();
        (pending.payload.pending_calls ?? []).forEach((call, i) => {
          if (!call.tool_call_id) return;
          messagesRef.current = upsertOne(messagesRef.current, {
            session_id: pending.session_id,
            exchange_id: pending.exchange_id,
            rank: rankBase + i,
            timestamp: cancelTs,
            role: "tool",
            channel: "tool_result",
            parts: [{ type: "tool_result", call_id: call.tool_call_id, ok: false, content: "", latency_ms: null }],
            metadata: { extras: { cancelled_by_user: true } },
          });
        });
        setMessages([...messagesRef.current]);
      }

      try {
        await KeyCloakService.ensureFreshToken(30);
      } catch (err) {
        if (!ac.signal.aborted) {
          onError?.(`Could not resume this turn: ${(err as Error)?.message ?? String(err)}`);
        }
        return;
      }
      if (ac.signal.aborted) {
        return;
      }
      const token = KeyCloakService.GetToken() ?? "";

      let prep: ExecutionPreparation;
      try {
        prep = await prepareExecution({ teamId, agentInstanceId }).unwrap();
      } catch (err) {
        if (!ac.signal.aborted) {
          onError?.(`Could not resume this turn: ${(err as Error)?.message ?? String(err)}`);
        }
        return;
      }
      // This attempt may have been superseded (by a new send() or another
      // sendHitlResume) while prepare-execution was in flight — don't apply
      // a stale response's chat controls/capability URLs over the current
      // owner's state.
      if (ac.signal.aborted) {
        return;
      }
      applyPreparation(prep);

      const sessionId = pending.session_id;
      // Reuse the interrupted turn's exchange_id straight from the event that
      // reported it — `pending` is the exact `RuntimeAwaitingHumanEvent` this
      // resume answers, so its own `exchange_id` is authoritative by construction,
      // unlike a ref that a later, unrelated send() could have overwritten
      // (or that a stale closure could read before it was ever set). A HITL
      // resume continues the same exchange as the interrupted turn, not a
      // new one — otherwise the pre-pause tool_call and the post-resume
      // tool_result would land under two different exchange_ids and the
      // trace step would stay "in progress" forever, even after the result
      // had actually arrived (toThreadMessages buckets trace entries by
      // exchange_id before groupTraceEntries can pair a call with its result
      // by call_id).
      const exchangeId = pending.exchange_id;
      const hitlPayload = pending.payload;
      const hasChoices = Array.isArray(hitlPayload?.choices) && hitlPayload.choices.length > 0;
      const normalizedFreeText = typeof freeText === "string" ? freeText.trim() || undefined : undefined;
      const answerValue = !hasChoices && normalizedFreeText ? normalizedFreeText : answer;

      setWaitResponse(true);

      try {
        await streamToMessages(
          {
            agent_instance_id: agentInstanceId,
            session_id: sessionId,
            // #2216: ReAct V2 resumes must echo interrupt_id (LangGraph's
            // Interrupt.id, validated against the currently pending
            // occurrence backend-side) — checkpoint_id is the unrelated
            // legacy Graph V2 field and is forwarded only for that runtime.
            interrupt_id: hitlPayload?.interrupt_id ?? null,
            checkpoint_id: hitlPayload?.checkpoint_id ?? null,
            // `language` matters here too: a resumed turn can reach a fresh
            // gated tool call of its own (the model replans and requests more
            // approval-needing tools within the same resumed stream) — see
            // the matching comment in send() above.
            runtime_context: {
              team_id: canonicalizeRuntimeTeamId(teamId),
              language: i18n.language?.split("-")[0] || undefined,
            },
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
    [agentInstanceId, teamId, prepareExecution, streamToMessages, onError, applyPreparation, i18n],
  );

  // Eager prep (RFC §3.7): call prepare-execution at chat open — not only
  // inside send() — so `chatControls` are populated before the first message
  // and the composer isn't empty until the user sends something. Safe to call
  // with no session yet (sessionId omitted); the composer's own state
  // (selected libraries/policy/scope) is unaffected until a real send happens.
  const prepareChatControls = useCallback(
    async (sessionId?: string | null) => {
      const prep = await prepareExecution({
        teamId,
        agentInstanceId,
        ...(sessionId ? { sessionId } : {}),
      }).unwrap();
      applyPreparation(prep);
      return prep;
    },
    [teamId, agentInstanceId, prepareExecution, applyPreparation],
  );

  return {
    messages,
    waitResponse,
    chatControls,
    prepareChatControls,
    send,
    sendHitlResume,
    abort,
    reset,
    replaceAllMessages,
  };
}
