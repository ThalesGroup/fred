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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useComposerSettings } from "./useComposerSettings";
import { useSearchParams } from "react-router-dom";
import { v4 as uuidv4 } from "uuid";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useChatSse } from "@hooks/useChatSse";
import type { AwaitingHumanEvent, ChatMessage, VectorSearchHit } from "../../../../slices/agentic/agenticOpenApi";
import {
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery,
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { isTraceChannel, textOf } from "../../../../rework/utils/traceUtils";
import type { ThreadMessage } from "@rework/types/thread";
import type { TokenUsage } from "@rework/types/conversation";
import { useSessionHistory } from "./useSessionHistory";
import { useChatAttachments } from "./useChatAttachments";
import { buildComposerRuntimeContext } from "./runtimeContextBuilder";

// ── Local view model builder ──────────────────────────────────────────────────

function toThreadMessages(messages: ChatMessage[], isStreaming: boolean): ThreadMessage[] {
  const order: string[] = [];
  const groups = new Map<string, ChatMessage[]>();

  for (const msg of messages) {
    const eid = msg.exchange_id;
    if (!groups.has(eid)) {
      order.push(eid);
      groups.set(eid, []);
    }
    groups.get(eid)!.push(msg);
  }

  const result: ThreadMessage[] = [];
  const lastEid = order[order.length - 1] as string | undefined;

  for (const eid of order) {
    const msgs = groups.get(eid)!;
    const isLast = eid === lastEid;

    const userMsg = msgs.find((m) => m.role === "user" && (m.channel as string) !== "hitl_response");
    if (userMsg) {
      result.push({
        id: `${eid}:user`,
        role: "user",
        text: textOf(userMsg),
        isStreaming: false,
        traceMessages: [],
        sources: [],
      });
    }

    const hitlReqMsg = msgs.find((m) => (m.channel as string) === "hitl_request");
    if (hitlReqMsg) {
      type ReqPart = { question?: string; choices?: Array<{ id: string; label: string }>; title?: string | null };
      const part = hitlReqMsg.parts?.[0] as unknown as ReqPart | undefined;
      result.push({
        id: `${eid}:hitl_req`,
        role: "hitl_request",
        text: part?.question ?? "",
        isStreaming: false,
        traceMessages: [],
        sources: [],
        hitlChoices: part?.choices ?? [],
        hitlTitle: part?.title,
      });
    }

    const hitlRespMsg = msgs.find((m) => (m.channel as string) === "hitl_response");
    if (hitlRespMsg) {
      type RespPart = { label?: string | null; choice_id?: string };
      const part = hitlRespMsg.parts?.[0] as unknown as RespPart | undefined;
      result.push({
        id: `${eid}:hitl_resp`,
        role: "hitl_response",
        text: part?.label ?? part?.choice_id ?? "",
        isStreaming: false,
        traceMessages: [],
        sources: [],
      });
    }

    const traceMessages = msgs.filter((m) => isTraceChannel(m.channel));
    const finalMessages = msgs.filter((m) => {
      const ch = m.channel as string;
      return m.role !== "user" && ch !== "hitl_request" && ch !== "hitl_response" && !isTraceChannel(m.channel);
    });

    if (traceMessages.length > 0 || finalMessages.length > 0 || (isStreaming && isLast)) {
      const sources: VectorSearchHit[] = [];
      let tokenUsage: TokenUsage | null = null;
      for (let i = finalMessages.length - 1; i >= 0; i--) {
        const meta = finalMessages[i].metadata as Record<string, unknown> | undefined;
        if (!tokenUsage && meta?.token_usage) {
          const tu = meta.token_usage as Record<string, number>;
          tokenUsage = {
            input_tokens: tu.input_tokens ?? 0,
            output_tokens: tu.output_tokens ?? 0,
            total_tokens: tu.total_tokens ?? 0,
          };
        }
        if (sources.length === 0) {
          const srcs = meta?.sources as VectorSearchHit[] | undefined;
          if (srcs && srcs.length > 0) sources.push(...srcs);
        }
        if (tokenUsage && sources.length > 0) break;
      }
      result.push({
        id: `${eid}:assistant`,
        role: "assistant",
        text: finalMessages.map((m) => textOf(m)).join(""),
        isStreaming: isStreaming && isLast,
        traceMessages,
        sources,
        tokenUsage,
      });
    }
  }

  return result;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

interface UseManagedChatParams {
  teamId: string;
  agentInstanceId: string;
}

export function useManagedChat({ teamId, agentInstanceId }: UseManagedChatParams) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { showError } = useToast();
  const { i18n } = useTranslation();
  const lang = i18n.language.split("-")[0];

  const sessionId = searchParams.get("session");
  const [input, setInput] = useState("");
  const [pendingHitl, setPendingHitl] = useState<AwaitingHumanEvent | null>(null);
  const [sessionTitle, setSessionTitle] = useState<string | null>(null);
  // Ordered chat-context prompts attached to this session (PROMPT-05). Source of
  // truth is the control-plane session; hydrated from sessionData and persisted
  // via PATCH on every change.
  const [contextPromptIds, setContextPromptIds] = useState<string[]>([]);
  // Suppresses the sessionId-change reset when handleSend itself binds a new session.
  const skipResetOnSessionBindRef = useRef(false);

  const { data: agentInstances } = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery(
    { teamId },
    { skip: !teamId },
  );
  const agentInstance = agentInstances?.find((i) => i.agent_instance_id === agentInstanceId);
  const agentDisplayName = agentInstance?.display_name ?? "Agent";
  // Baseline capabilities available at mount — no message needed.
  const agentChatOptions = agentInstance?.effective_chat_options ?? null;
  const agentChatOptionsRef = useRef(agentChatOptions);
  agentChatOptionsRef.current = agentChatOptions;

  const composer = useComposerSettings(sessionId, agentChatOptions);
  const attachments = useChatAttachments({ teamId, sessionId });

  const { data: sessionData } = useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery(
    { teamId, sessionId: sessionId ?? "" },
    { skip: !teamId || !sessionId },
  );

  // Library prompts available as chat context (personal + team + platform defaults).
  const { data: contextPrompts = [] } = useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery(
    { teamId, lang },
    { skip: !teamId },
  );

  const [registerSession] = usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation();
  const [refreshSession] = usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation();

  const bindSessionId = useCallback(
    (sid: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("session", sid);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  // Session writes (row creation POST, context-prompt PATCH) are fired eagerly
  // for a snappy UI, but the first turn's prepare-execution must not read the
  // session before they commit. We track each in-flight write here and expose
  // flushSessionWrites() as an ordering barrier awaited just before prep.
  const pendingSessionWritesRef = useRef<Set<Promise<unknown>>>(new Set());
  // The latest session-creation POST, so context-prompt PATCHes can chain after
  // it (the brand-new-session sub-race: a PATCH must not reach the server before
  // the session row exists).
  const sessionCreatePromiseRef = useRef<Promise<unknown> | null>(null);

  const trackSessionWrite = useCallback((promise: Promise<unknown>) => {
    const settled: Promise<unknown> = promise
      .catch(() => {})
      .finally(() => {
        pendingSessionWritesRef.current.delete(settled);
      });
    pendingSessionWritesRef.current.add(settled);
  }, []);

  const flushSessionWrites = useCallback(async () => {
    // Await a snapshot: writes already in flight when the send starts must
    // commit before prep resolves chat context from the persisted session.
    await Promise.all(Array.from(pendingSessionWritesRef.current));
  }, []);

  const { messages, waitResponse, effectiveChatOptions, send, sendHitlResume, abort, reset, replaceAllMessages } =
    useChatSse({
      agentInstanceId,
      teamId,
      lang,
      flushPendingWrites: flushSessionWrites,
      onBindDraftAgentToSessionId: bindSessionId,
      onTurnPersisted: (sid) => {
        refreshSession({
          teamId,
          sessionId: sid,
          updateSessionRequest: { updated_at: new Date().toISOString() },
        }).catch(() => {});
      },
      onAwaitingHuman: (event) => setPendingHitl(event),
      onError: (msg) => showError({ summary: "Agent error", detail: msg }),
    });

  useEffect(() => {
    if (skipResetOnSessionBindRef.current) {
      console.debug(
        `[useManagedChat] sessionId changed → skipping reset (bound by handleSend) — sessionId=${sessionId ?? "null"}`,
      );
      skipResetOnSessionBindRef.current = false;
      return;
    }
    console.debug(`[useManagedChat] sessionId changed → reset() — sessionId=${sessionId ?? "null"}`);
    reset();
    setPendingHitl(null);
    setInput("");
    setSessionTitle(null);
    setContextPromptIds([]);
    composer.reset(sessionId, agentChatOptionsRef.current);
  }, [sessionId, reset, composer.reset]);

  useEffect(() => {
    if (sessionData?.title != null) setSessionTitle(sessionData.title);
  }, [sessionData]);

  // Rehydrate attached chat-context prompts from the persisted session so the
  // pills survive a reload (RFC Part 3 §19).
  useEffect(() => {
    if (sessionData?.context_prompt_ids != null) setContextPromptIds(sessionData.context_prompt_ids);
  }, [sessionData]);

  const threadMessages = useMemo(() => toThreadMessages(messages, waitResponse), [messages, waitResponse]);

  const { isLoading: isLoadingHistory } = useSessionHistory({
    sessionId,
    teamId,
    agentInstanceId,
    onLoaded: replaceAllMessages,
  });

  const ensureSessionForAttachments = useCallback((): string => {
    let sid = sessionId;
    if (!sid) {
      sid = uuidv4();
      skipResetOnSessionBindRef.current = true;
      bindSessionId(sid);
      const created = registerSession({
        teamId,
        createSessionRequest: { session_id: sid, agent_instance_id: agentInstanceId, title: "New conversation" },
      })
        .unwrap()
        .catch(() => {});
      sessionCreatePromiseRef.current = created;
      trackSessionWrite(created);
    }
    return sid;
  }, [agentInstanceId, bindSessionId, registerSession, sessionId, teamId, trackSessionWrite]);

  const handleAddAttachments = useCallback(
    (files: File[], source: "picker" | "drop") => {
      const sid = ensureSessionForAttachments();
      void attachments.addFiles(files, source, sid);
    },
    [attachments.addFiles, ensureSessionForAttachments],
  );

  const handleSend = useCallback(() => {
    const text = input.trim();
    const attachmentContext = attachments.attachmentsMarkdown;
    console.debug(
      `[useManagedChat] handleSend() — text="${text.slice(0, 40)}" waitResponse=${waitResponse} sessionId=${sessionId ?? "null"}`,
    );
    if ((!text && !attachmentContext) || waitResponse) {
      console.debug(
        `[useManagedChat] handleSend() BLOCKED — text=${!!text} attachments=${!!attachmentContext} waitResponse=${waitResponse}`,
      );
      return;
    }
    setInput("");
    setPendingHitl(null);
    let sid = sessionId;
    if (!sid) {
      sid = uuidv4();
      console.debug(`[useManagedChat] handleSend() — no session, creating new sid=${sid}, calling bindSessionId`);
      skipResetOnSessionBindRef.current = true;
      bindSessionId(sid);
      const created = registerSession({
        teamId,
        createSessionRequest: {
          session_id: sid,
          agent_instance_id: agentInstanceId,
          title: text ? text.slice(0, 120) : "Attached files",
        },
      })
        .unwrap()
        .catch(() => {});
      sessionCreatePromiseRef.current = created;
      // Tracked so the barrier below (send → flushSessionWrites) waits for the
      // session row before prepare-execution runs.
      trackSessionWrite(created);
    }
    console.debug(`[useManagedChat] handleSend() — calling send() with sid=${sid}`);
    send(
      text,
      sid,
      buildComposerRuntimeContext({
        selectedLibraryIds: composer.selectedLibraryIds,
        selectedDocumentUids: composer.selectedDocumentUids,
        searchPolicy: composer.searchPolicy,
        ragScope: composer.ragScope,
        boundLibraryIds: (effectiveChatOptions ?? agentChatOptions)?.bound_library_ids ?? null,
        attachmentsMarkdown: attachmentContext,
      }),
    );
    attachments.clearReadyAttachments();
  }, [
    attachments.attachmentsMarkdown,
    attachments.clearReadyAttachments,
    input,
    waitResponse,
    sessionId,
    teamId,
    agentInstanceId,
    effectiveChatOptions,
    agentChatOptions,
    composer.selectedLibraryIds,
    composer.selectedDocumentUids,
    composer.searchPolicy,
    composer.ragScope,
    bindSessionId,
    registerSession,
    trackSessionWrite,
    send,
  ]);

  const handleHitlAnswer = useCallback(
    (answer: string | boolean, freeText?: string) => {
      if (!pendingHitl) return;
      setPendingHitl(null);
      sendHitlResume(pendingHitl, answer, freeText);
    },
    [pendingHitl, sendHitlResume],
  );

  const startNewConversation = useCallback(() => {
    setPendingHitl(null);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("session");
        return next;
      },
      { replace: true },
    );
  }, [setSearchParams]);

  const commitTitle = useCallback(
    (title: string) => {
      if (!sessionId) return;
      setSessionTitle(title);
      refreshSession({ teamId, sessionId, updateSessionRequest: { title } }).catch(() => {});
    },
    [teamId, sessionId, refreshSession],
  );

  // Replace the full ordered set of attached chat-context prompts and persist it.
  // Ensures a session exists first so prompts can be attached before the first
  // message of a brand-new conversation.
  const setContextPrompts = useCallback(
    (ids: string[]) => {
      setContextPromptIds(ids);
      const sid = ensureSessionForAttachments();
      // Chain the PATCH after any in-flight session creation so the row exists
      // before its context prompts are written, then track it so the next send
      // waits for it to commit (see flushSessionWrites).
      const create = sessionCreatePromiseRef.current ?? Promise.resolve();
      const patch = create.then(() =>
        refreshSession({ teamId, sessionId: sid, updateSessionRequest: { context_prompt_ids: ids } }).unwrap(),
      );
      trackSessionWrite(patch);
    },
    [ensureSessionForAttachments, refreshSession, teamId, trackSessionWrite],
  );

  return {
    sessionId,
    sessionTitle,
    agentDisplayName,
    agentChatOptions,
    input,
    setInput,
    pendingHitl,
    selectedLibraryIds: composer.selectedLibraryIds,
    attachments: attachments.attachments,
    persistedAttachments: attachments.persistedAttachments,
    isHydratingAttachments: attachments.isHydratingAttachments,
    handleAddAttachments,
    removeAttachment: attachments.removeAttachment,
    deletePersistedAttachment: attachments.deletePersistedAttachment,
    setSelectedLibraryIds: composer.setSelectedLibraryIds,
    selectedDocumentUids: composer.selectedDocumentUids,
    setSelectedDocumentUids: composer.setSelectedDocumentUids,
    searchPolicy: composer.searchPolicy,
    setSearchPolicy: composer.setSearchPolicy,
    ragScope: composer.ragScope,
    setRagScope: composer.setRagScope,
    contextPrompts,
    contextPromptIds,
    setContextPrompts,
    threadMessages,
    messages,
    waitResponse,
    effectiveChatOptions: effectiveChatOptions ?? agentChatOptions,
    isLoadingHistory,
    handleSend,
    handleHitlAnswer,
    handleAbort: abort,
    startNewConversation,
    commitTitle,
  };
}
