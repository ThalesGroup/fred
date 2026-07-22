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
import type { AwaitingHumanEvent } from "../../../../slices/agentic/agenticOpenApi";
import {
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery,
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useSessionHistory } from "./useSessionHistory";
import { useChatAttachments } from "./useChatAttachments";
import { buildComposerRuntimeContext } from "./runtimeContextBuilder";
import { toThreadMessages } from "./toThreadMessages";

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
  // Capabilities active in this session — drives the capability side-panel slot
  // (#1979, RFC §9 item 3). The host resolves each id against the plugin index.
  const capabilityIds = agentInstance?.selected_capability_ids ?? [];

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

  const {
    messages,
    waitResponse,
    chatControls,
    prepareChatControls,
    send,
    sendHitlResume,
    abort,
    reset,
    replaceAllMessages,
  } = useChatSse({
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

  // Chat controls are resolved per agent instance/config, not per session — a
  // session change should keep showing the last-known controls (no composer
  // flicker) while prepareChatControls quietly refreshes them, mirroring the
  // old agentChatOptionsRef pattern this replaces.
  const chatControlsRef = useRef(chatControls);
  chatControlsRef.current = chatControls;

  const composer = useComposerSettings(sessionId, chatControls);

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
    composer.reset(sessionId, chatControlsRef.current);
    // Eager prep (RFC §3.7, CAPAB-01 #1976): resolve chat_controls at chat open
    // — not only inside send() — so the composer control slot isn't empty
    // until the first message. Safe with no session yet (sessionId null).
    void prepareChatControls(sessionId).catch(() => {});
  }, [sessionId, reset, composer.reset, prepareChatControls]);

  useEffect(() => {
    if (sessionData?.title != null) setSessionTitle(sessionData.title);
  }, [sessionData]);

  // Rehydrate attached chat-context prompts from the persisted session so the
  // pills survive a reload (PROMPTS.md §5).
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
    if ((!text && !attachmentContext) || waitResponse || attachments.hasUploadingAttachments) {
      console.debug(
        `[useManagedChat] handleSend() BLOCKED — text=${!!text} attachments=${!!attachmentContext} waitResponse=${waitResponse} uploading=${attachments.hasUploadingAttachments}`,
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
    // `document_scope`'s params carry the same `bound_library_ids` the retired
    // `EffectiveChatOptions.bound_library_ids` did (CAPAB-01 #1976) — an
    // MCP-server-bound library scope the picker cannot override.
    const documentScopeControl = chatControls.find((c) => c.widget === "document_scope");
    const boundLibraryIds =
      (documentScopeControl?.params as { bound_library_ids?: string[] | null } | undefined)?.bound_library_ids ?? null;
    // The picker's per-turn selection reaches the OWNING capability's typed
    // `turn_options[capability_id]` slice (RFC §3.5) — but ONLY
    // `document_access` declares a TurnOptionsModel for it. The MCP
    // capability's document_scope widget reads RuntimeContext (built below)
    // and validates turn_options against EmptyModel, so sending it a slice
    // is a typed 422.
    const turnOptions =
      documentScopeControl && documentScopeControl.capability_id === "document_access"
        ? {
            [documentScopeControl.capability_id]: {
              library_tag_ids: composer.selectedLibraryIds,
              document_uids: composer.selectedDocumentUids,
            },
          }
        : undefined;
    send(
      text,
      sid,
      buildComposerRuntimeContext({
        selectedLibraryIds: composer.selectedLibraryIds,
        selectedDocumentUids: composer.selectedDocumentUids,
        searchPolicy: composer.searchPolicy,
        ragScope: composer.ragScope,
        boundLibraryIds,
        attachmentsMarkdown: attachmentContext,
      }),
      turnOptions,
    );
    attachments.clearReadyAttachments();
  }, [
    attachments.attachmentsMarkdown,
    attachments.clearReadyAttachments,
    attachments.hasUploadingAttachments,
    input,
    waitResponse,
    sessionId,
    teamId,
    agentInstanceId,
    chatControls,
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
    capabilityIds,
    chatControls,
    input,
    setInput,
    pendingHitl,
    selectedLibraryIds: composer.selectedLibraryIds,
    attachments: attachments.attachments,
    persistedAttachments: attachments.persistedAttachments,
    isHydratingAttachments: attachments.isHydratingAttachments,
    attachmentsUploading: attachments.hasUploadingAttachments,
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
    isLoadingHistory,
    handleSend,
    handleHitlAnswer,
    handleAbort: abort,
    startNewConversation,
    commitTitle,
  };
}
