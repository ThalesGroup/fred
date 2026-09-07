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
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useChatSse } from "@hooks/useChatSse";
import type { RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";
import {
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery,
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useSessionHistory } from "./useSessionHistory";
import { setCachedSessionHistory } from "./sessionHistoryCache";
import { useChatAttachments } from "./useChatAttachments";
import { buildComposerRuntimeContext } from "./runtimeContextBuilder";
import { reconstructPendingHitl, toThreadMessages } from "./toThreadMessages";
import type { ChatMessage } from "../../../../slices/runtime/runtimeOpenApi";
import { countUnicodeCodePoints } from "@core/utils/chatInput";
import type { AttachmentSource } from "@rework/types/attachments";

// ── Hook ──────────────────────────────────────────────────────────────────────

interface UseManagedChatParams {
  teamId: string;
  agentInstanceId: string;
}

export function useManagedChat({ teamId, agentInstanceId }: UseManagedChatParams) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { showError } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { t } = useTranslation();

  const sessionId = searchParams.get("session");
  const [input, setInput] = useState("");
  const submittedDraftRef = useRef<{ sessionId: string; draft: string } | null>(null);
  const [pendingHitl, setPendingHitl] = useState<RuntimeAwaitingHumanEvent | null>(null);
  const [hitlFreeText, setHitlFreeText] = useState("");
  // Identifies the HITL prompt that owns `hitlFreeText`. A resume can settle
  // after another prompt has arrived; only its own draft may be cleared.
  const hitlDraftOwnerRef = useRef(0);
  const [sessionTitle, setSessionTitle] = useState<string | null>(null);
  // Ordered chat-context prompts attached to this session (PROMPT-05). Source of
  // truth is the control-plane session; hydrated from sessionData and persisted
  // via PATCH on every change.
  const [contextPromptIds, setContextPromptIds] = useState<string[]>([]);
  // Monotonic counter, PER SESSION ID — the "generation" of the most
  // recently issued setContextPrompts call for that sid. A write's failure
  // callback only rolls back if its own generation still matches the
  // CURRENT generation for the SAME sid it was issued for (i.e. no newer
  // selection for that same session has since superseded it) — otherwise an
  // old rejection could stomp a newer already-applied selection, regardless
  // of network resolution order. Keyed by sid (not a single global counter)
  // so session A's write settling after navigating to session B can never
  // even be mistaken for "still current" — B's generation for A's sid never
  // moves, since nothing ever calls setContextPrompts against A's sid again.
  const contextPromptGenerationBySidRef = useRef<Map<string, number>>(new Map());
  // The last context-prompt selection we know the server actually holds,
  // PER SESSION ID — the correct rollback target on a failed PATCH. Kept in
  // sync by every successful write and by the session-load rehydrate
  // effect, both scoped to the sid they apply to.
  const lastConfirmedContextPromptIdsBySidRef = useRef<Map<string, string[]>>(new Map());
  // Always the CURRENTLY active session id, refreshed every render — a
  // callback closure captures `sid` (whatever session it was issued for) at
  // call time, but must compare against the LATEST active session at
  // settlement time, which requires a ref (a plain closure over `sessionId`
  // would be frozen at call time too). A settling write for a session the
  // user has since navigated away from must never touch `contextPromptIds`
  // (a single, not-per-session piece of UI state) or show a toast for it.
  const activeSessionIdRef = useRef(sessionId);
  activeSessionIdRef.current = sessionId;
  // Live mirror of the rendered thread. `handleHitlAnswer`'s continuation
  // settles after arbitrary delay and must read the CURRENT thread, not the one
  // captured when the user answered.
  const latestMessagesRef = useRef<ChatMessage[]>([]);
  // Whether a local context-prompt mutation has happened for the CURRENTLY
  // active session. Once true, the rehydrate effect below stops applying
  // incoming `sessionData` snapshots — a GET that resolves late (e.g. after
  // a refetch) must never overwrite an already-pending or already-confirmed
  // local selection with an older server snapshot. Reset to false by the
  // sessionId-change effect below, so entering a (new or different) session
  // always starts with normal rehydration.
  const hasLocalMutationForActiveSessionRef = useRef(false);
  // Suppresses the sessionId-change reset when handleSend itself binds a new session.
  const skipResetOnSessionBindRef = useRef(false);
  // Synchronous reentrancy guard for handleSend()'s OWN preflight — session
  // id selection, bindSessionId, and createSessionRow all happen BEFORE
  // useChatSse's send() (and its own lock) is ever called: send() is not
  // reached until after `await flushSessionWrites(sid)` resolves. The
  // `waitResponse` check below does not cover this window — it only flips
  // true once send() itself runs, well after two rapid handleSend() calls
  // (e.g. a double Enter) could each have already generated their own
  // session id, bound it, and created a session row. Checked and set
  // synchronously, before any await, independent of `waitResponse` or a
  // React rerender — a second handleSend() arriving while the first is
  // still inside this window (including while suspended in
  // flushSessionWrites) is dropped outright, not queued or merged.
  const handleSendOwnerRef = useRef(false);

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

  // `currentData`, not `data`: RTK Query's `data` deliberately reuses the last
  // resolved result across an arg change (here, a session switch) while the
  // new args' request is still in flight — exactly the case navigating from
  // session A to session B hits. `currentData` is undefined until the result
  // actually belongs to the CURRENT args, closing the window where A's stale
  // payload could get attributed to B below (title, context prompt rehydrate).
  const { currentData: sessionData } = useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery(
    { teamId, sessionId: sessionId ?? "" },
    { skip: !teamId || !sessionId },
  );

  const [registerSession] = usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation();
  const [refreshSession] = usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation();
  // Bumps the session's activity timestamp (tile date + chat-list ordering) —
  // called both at send time (so the tile jumps to the top the moment the
  // user hits Enter) and again when the turn completes.
  const touchSessionActivity = useCallback(
    (sid: string) => {
      refreshSession({
        teamId,
        sessionId: sid,
        updateSessionRequest: { updated_at: new Date().toISOString() },
      }).catch(() => {});
    },
    [refreshSession, teamId],
  );

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

  // Serialized per-session write queue for critical session writes (row
  // creation POST, context-prompt PATCH). These must never race: two
  // concurrent PATCHes for the same session can have their HTTP responses
  // land out of order, letting an OLDER selection silently overwrite a
  // NEWER one server-side. Each session's writes are chained onto a per-sid
  // "tail" promise — write N+1's actual network call does not start until
  // write N has fully settled (success or failure) — so responses are
  // always received in send order, and two writes for the same sid are
  // never in flight together. Writes for DIFFERENT sessions use different
  // tails and never block or contaminate each other. A tail promise NEVER
  // rejects (a failure is converted to `{ok:false}` and reported via that
  // write's own `onError`) so a failure never stops the NEXT write in the
  // chain from being attempted, and nothing here can become an unhandled
  // rejection.
  const writeTailsRef = useRef<Map<string, Promise<{ ok: boolean }>>>(new Map());

  const enqueueSessionWrite = useCallback(
    (sid: string, action: () => Promise<unknown>, onError: (error: unknown) => void): Promise<{ ok: boolean }> => {
      const previousTail = writeTailsRef.current.get(sid) ?? Promise.resolve({ ok: true });
      const nextTail: Promise<{ ok: boolean }> = previousTail
        .then(() => action())
        .then(() => ({ ok: true }))
        .catch((error: unknown) => {
          onError(error);
          return { ok: false };
        });
      writeTailsRef.current.set(sid, nextTail);
      return nextTail;
    },
    [],
  );

  // Every sid bound to the URL whose creation POST is known to have failed
  // (and hasn't since succeeded). `bindSessionId` runs eagerly, before the
  // POST settles, so on retry `sessionId` already equals this sid — without
  // this, a retry would see "session already bound" and skip re-creating the
  // row entirely, then send against a session that was never actually
  // persisted. Keyed by sid (not a single scalar, matching `writeTailsRef`'s
  // per-sid keying) — different sessions can each be creating concurrently
  // (e.g. two "new conversation" starts in quick succession), and a single
  // shared slot would let one session's failure silently overwrite another's:
  // the forgotten session's own write tail stays permanently failed, but
  // `needsCreate` would no longer recognize it, so it can never be retried.
  const sessionCreateFailedIdRef = useRef<Set<string>>(new Set());

  // Stability loop, not a single snapshot await: `Promise.all` over a
  // point-in-time collection can miss a write enqueued WHILE the flush is
  // already awaiting — send() could then reach prepare-execution before
  // that write commits. This re-reads the session's tail after every await
  // and keeps waiting as long as a newer tail keeps replacing the one just
  // observed. Returns the outcome of the LAST write actually enqueued for
  // this session: an earlier failure superseded by a later success must not
  // block send (mirrors the generation guard in setContextPrompts below —
  // the most recent user intent, not write history, decides the outcome).
  const flushSessionWrites = useCallback(async (sid: string | null): Promise<boolean> => {
    if (!sid) return true;
    let ok = true;
    let observedTail: Promise<{ ok: boolean }> | undefined;
    for (;;) {
      const currentTail = writeTailsRef.current.get(sid);
      if (!currentTail || currentTail === observedTail) return ok;
      observedTail = currentTail;
      ok = (await currentTail).ok;
    }
  }, []);

  // Stabilized (not inlined at the useChatSse call site below): useChatSse's
  // own send()/sendHitlResume() memoize around these callbacks, so an inline
  // arrow here — recreated on every useManagedChat render, including every
  // composer keystroke — would silently invalidate that memoization on every
  // keystroke too, cascading into handleHitlAnswer below and defeating
  // ConversationThread's React.memo (#2221).
  const handleAwaitingHuman = useCallback((event: RuntimeAwaitingHumanEvent) => {
    hitlDraftOwnerRef.current += 1;
    setHitlFreeText("");
    setPendingHitl(event);
  }, []);
  const handleChatError = useCallback((msg: string) => showError({ summary: "Agent error", detail: msg }), [showError]);
  // Fires only once prepare-execution has actually succeeded and the turn is
  // really starting — clearing the composer any earlier would lose the
  // user's text/attachments on a prepare-execution failure (404/503/network).
  const handleTurnStarted = useCallback(() => {
    setInput("");
    attachments.clearReadyAttachments();
  }, [attachments.clearReadyAttachments]);
  const handleTurnRejected = useCallback((_wireDraft: string, rejectedSessionId: string) => {
    const submitted = submittedDraftRef.current;
    if (activeSessionIdRef.current !== rejectedSessionId || submitted?.sessionId !== rejectedSessionId) return;
    setInput(submitted.draft);
  }, []);
  const isTurnCurrent = useCallback((turnSessionId: string) => activeSessionIdRef.current === turnSessionId, []);

  const {
    messages,
    waitResponse,
    chatControls,
    maxChatInputChars,
    prepareChatControls,
    send,
    sendHitlResume,
    abort,
    reset,
    replaceAllMessages,
  } = useChatSse({
    agentInstanceId,
    teamId,
    flushPendingWrites: flushSessionWrites,
    onBindDraftAgentToSessionId: bindSessionId,
    onTurnPersisted: touchSessionActivity,
    onAwaitingHuman: handleAwaitingHuman,
    onError: handleChatError,
    onTurnStarted: handleTurnStarted,
    onTurnRejected: handleTurnRejected,
    isTurnCurrent,
  });
  latestMessagesRef.current = messages;

  // Chat controls are resolved per agent instance/config, not per session — a
  // session change should keep showing the last-known controls (no composer
  // flicker) while prepareChatControls quietly refreshes them, mirroring the
  // old agentChatOptionsRef pattern this replaces.
  const chatControlsRef = useRef(chatControls);
  chatControlsRef.current = chatControls;

  // Live-turn indicator handed to useSessionHistory — its async closures need
  // the CURRENT streaming state at response-arrival time, not the render-time
  // value a plain boolean capture would freeze.
  const waitResponseRef = useRef(waitResponse);
  waitResponseRef.current = waitResponse;
  const isTurnActive = useCallback(() => waitResponseRef.current, []);

  // Mirrors read by the departure-snapshot cleanup below: a cleanup closure
  // captures its own render's values, but must snapshot what is on screen at
  // DEPARTURE time.
  const displayedMessagesRef = useRef(messages);
  displayedMessagesRef.current = messages;
  const isLoadingHistoryRef = useRef(false);

  // #2239: on leaving a session (switch or unmount), snapshot the displayed
  // thread into the session-history cache — this cleanup runs BEFORE the next
  // session's reset effect wipes the state, and it is what folds
  // live-streamed turns into the cache without any extra fetch. Skipped while
  // the initial history load is still in flight: caching a half-loaded thread
  // would make the next visit render it as if it were complete.
  useEffect(() => {
    if (!sessionId) return;
    return () => {
      if (isLoadingHistoryRef.current) return;
      setCachedSessionHistory(sessionId, displayedMessagesRef.current);
    };
  }, [sessionId]);

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
    // reset() aborts any in-flight turn synchronously, but the waitResponse
    // STATE only flips false on the next render — too late for the history
    // effect running later in this same commit, whose isTurnActive() must
    // already see "no live turn" or a cached thread would refuse to render.
    waitResponseRef.current = false;
    setPendingHitl(null);
    hitlDraftOwnerRef.current += 1;
    setHitlFreeText("");
    setInput("");
    setSessionTitle(null);
    setContextPromptIds([]);
    // A genuine entry into a (new or different) session — normal
    // rehydration governs from here until the first local mutation.
    hasLocalMutationForActiveSessionRef.current = false;
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
  // pills survive a reload (PROMPTS.md §5). Also resets the rollback target
  // (see setContextPrompts) to this freshly-loaded, durably-confirmed value.
  //
  // Guarded by `hasLocalMutationForActiveSessionRef`: `sessionData` is an
  // RTK Query result that can resolve or re-resolve (a refetch, a slow
  // initial fetch racing a fast local PATCH) at any time, including WHILE a
  // local mutation for this same session is pending or has already
  // committed. Once the user has made at least one local mutation for the
  // CURRENTLY active session, an incoming (possibly older) server snapshot
  // must never silently replace their pending/confirmed selection — this
  // effect goes back to applying it only once a genuinely new session is
  // entered (the sessionId-change effect above resets the flag).
  useEffect(() => {
    if (!sessionId) return;
    if (sessionData?.context_prompt_ids == null) return;
    if (hasLocalMutationForActiveSessionRef.current) return;
    setContextPromptIds(sessionData.context_prompt_ids);
    lastConfirmedContextPromptIdsBySidRef.current.set(sessionId, sessionData.context_prompt_ids);
  }, [sessionData, sessionId]);

  const threadMessages = useMemo(() => toThreadMessages(messages, waitResponse), [messages, waitResponse]);
  const inputCharacterCount = useMemo(() => countUnicodeCodePoints(input.trim()), [input]);
  const inputTooLong = maxChatInputChars !== undefined && inputCharacterCount > maxChatInputChars;

  // History load/switch always REPLACES pendingHitl with whatever the loaded
  // messages actually say — set when the trailing exchange has a HITL gate
  // still open (no matching response yet), cleared (null) otherwise. Fixes
  // refreshing mid-confirmation: the prompt used to simply vanish (live-only
  // state, never reconstructed from history) and the gated tool stayed stuck
  // rendering as "running" with no way to answer it.
  const handleHistoryLoaded = useCallback(
    (msgs: ChatMessage[]) => {
      replaceAllMessages(msgs);
      hitlDraftOwnerRef.current += 1;
      setHitlFreeText("");
      setPendingHitl(reconstructPendingHitl(msgs));
    },
    [replaceAllMessages],
  );

  const { isLoading: isLoadingHistory } = useSessionHistory({
    sessionId,
    teamId,
    agentInstanceId,
    onLoaded: handleHistoryLoaded,
    isTurnActive,
  });
  isLoadingHistoryRef.current = isLoadingHistory;

  const notifySessionSaveFailed = useCallback(
    (error: unknown) =>
      notifyApiError(error, {
        summary: t("chatbot.errors.sessionSaveFailedSummary"),
        fallbackDetail: t("chatbot.errors.sessionSaveFailedDetail"),
      }),
    [notifyApiError, t],
  );

  // Enqueues the session-row creation POST onto this sid's write tail, so it
  // always precedes any context-prompt PATCH for the same sid (both go
  // through `enqueueSessionWrite` keyed on `sid`). Marks/clears `sid` in
  // `sessionCreateFailedIdRef` so a retry against the same (already
  // URL-bound) sid re-attempts creation instead of silently skipping it.
  const createSessionRow = useCallback(
    (sid: string, title: string) => {
      void enqueueSessionWrite(
        sid,
        () =>
          registerSession({
            teamId,
            createSessionRequest: { session_id: sid, agent_instance_id: agentInstanceId, title },
          }).unwrap(),
        (error) => {
          sessionCreateFailedIdRef.current.add(sid);
          notifySessionSaveFailed(error);
        },
      ).then((result) => {
        if (result.ok) {
          sessionCreateFailedIdRef.current.delete(sid);
        }
      });
    },
    [agentInstanceId, enqueueSessionWrite, notifySessionSaveFailed, registerSession, teamId],
  );

  const ensureSessionForAttachments = useCallback((): string => {
    let sid = sessionId;
    const needsCreate = !sid || sessionCreateFailedIdRef.current.has(sid);
    if (!sid) {
      sid = uuidv4();
      skipResetOnSessionBindRef.current = true;
      // Before bindSessionId: the composer settings the user picked while this
      // conversation had no id are only in memory until they are written under
      // one (#2369).
      composer.bindSession(sid);
      bindSessionId(sid);
    }
    if (needsCreate) {
      createSessionRow(sid, "New conversation");
    }
    return sid;
  }, [bindSessionId, composer.bindSession, createSessionRow, sessionId]);

  const handleAddAttachments = useCallback(
    (files: File[], source: AttachmentSource) => {
      const sid = ensureSessionForAttachments();
      void attachments.addFiles(files, source, sid);
    },
    [attachments.addFiles, ensureSessionForAttachments],
  );

  const handleSend = useCallback(async () => {
    const text = input.trim();
    const attachmentContext = attachments.attachmentsMarkdown;
    console.debug(
      `[useManagedChat] handleSend() — inputChars=${inputCharacterCount} waitResponse=${waitResponse} sessionId=${sessionId ?? "null"}`,
    );
    if ((!text && !attachmentContext) || waitResponse || attachments.hasUploadingAttachments || inputTooLong) {
      console.debug(
        `[useManagedChat] handleSend() BLOCKED — hasText=${!!text} attachments=${!!attachmentContext} waitResponse=${waitResponse} uploading=${attachments.hasUploadingAttachments} inputTooLong=${inputTooLong}`,
      );
      return;
    }
    if (handleSendOwnerRef.current) {
      console.debug("[useManagedChat] handleSend() IGNORED — a handleSend() is already in flight");
      return;
    }
    handleSendOwnerRef.current = true;
    try {
      // Composer input is left untouched until the session write barrier below
      // confirms success — clearing it eagerly would lose the user's message if
      // session creation fails, forcing a retype on retry.
      let sid = sessionId;
      const needsCreate = !sid || sessionCreateFailedIdRef.current.has(sid);
      if (!sid) {
        sid = uuidv4();
        console.debug(`[useManagedChat] handleSend() — no session, creating new sid=${sid}, calling bindSessionId`);
        skipResetOnSessionBindRef.current = true;
        // See ensureSessionForAttachments: makes this turn's composer settings
        // durable under the id they were picked for (#2369).
        composer.bindSession(sid);
        bindSessionId(sid);
      }
      if (needsCreate) {
        // Tracked so the barrier below (flushSessionWrites) waits for the
        // session row before prepare-execution runs, and surfaces a toast +
        // aborts the send if the row was never actually created. Re-fires on a
        // retry against the same (already URL-bound) sid whose prior creation
        // failed — see `sessionCreateFailedIdRef`.
        createSessionRow(sid, text ? text.slice(0, 120) : "Attached files");
      }

      // Block the send entirely on any pending or just-failed session write —
      // including a context-prompt PATCH fired earlier that hasn't committed
      // yet. A failure already triggered its own toast (via the write's
      // onError above); nothing further to show here, just don't proceed —
      // the message stays in the composer for an explicit retry.
      const writesOk = await flushSessionWrites(sid);
      if (!writesOk) {
        console.debug("[useManagedChat] handleSend() ABORTED — a pending session write failed");
        return;
      }

      // Input/attachments stay untouched here too — cleared only from
      // onTurnStarted, once prepare-execution inside send() has actually
      // succeeded. A prepare-execution failure (404/503/network) must never
      // wipe text the user still needs to retry with; see useChatSse.ts.
      setPendingHitl(null);
      console.debug(`[useManagedChat] handleSend() — calling send() with sid=${sid}`);
      // `document_scope`'s params carry the same `bound_library_ids` the retired
      // `EffectiveChatOptions.bound_library_ids` did (CAPAB-01 #1976) — an
      // MCP-server-bound library scope the picker cannot override.
      const documentScopeControl = chatControls.find((c) => c.widget === "document_scope");
      const boundLibraryIds =
        (documentScopeControl?.params as { bound_library_ids?: string[] | null } | undefined)?.bound_library_ids ??
        null;
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
      // REASON-01 level 4 (MODEL-REASONING-ENABLEMENT-RFC.md §7): reasoning is a
      // platform chat option, not a capability's turn_options slice — it travels
      // on RuntimeContext exactly like search policy and RAG scope. Sent ONLY
      // when the composer actually offers the control: its absence means the
      // agent does not offer reasoning (or a gate upstream is closed, §8), and
      // that must reach the runtime as "no choice made", never as an explicit
      // `false` that would suppress reasoning the agent never offered to begin
      // with.
      const offersReasoning = chatControls.some((c) => c.widget === "reasoning_toggle");
      touchSessionActivity(sid);
      // `send()` receives the trimmed wire value, but a backend rejection must
      // restore the complete editable draft, including surrounding whitespace.
      submittedDraftRef.current = { sessionId: sid, draft: input };
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
          ...(offersReasoning ? { reasoning: composer.reasoning } : {}),
        }),
        turnOptions,
      );
    } finally {
      handleSendOwnerRef.current = false;
    }
  }, [
    attachments.attachmentsMarkdown,
    attachments.hasUploadingAttachments,
    input,
    inputCharacterCount,
    inputTooLong,
    waitResponse,
    sessionId,
    chatControls,
    composer.bindSession,
    composer.selectedLibraryIds,
    composer.selectedDocumentUids,
    composer.searchPolicy,
    composer.ragScope,
    composer.reasoning,
    bindSessionId,
    createSessionRow,
    flushSessionWrites,
    touchSessionActivity,
    send,
  ]);

  const handleHitlAnswer = useCallback(
    (answer: string | boolean | undefined, freeText?: string) => {
      if (!pendingHitl) return;
      if (
        freeText !== undefined &&
        maxChatInputChars !== undefined &&
        countUnicodeCodePoints(freeText) > maxChatInputChars
      ) {
        return;
      }
      const prompt = pendingHitl;
      const draftOwner = hitlDraftOwnerRef.current;
      setPendingHitl(null);
      // Restore the prompt when the resume never reached the backend: the
      // checkpoint is still paused, so dropping it would strand the turn with
      // no way to answer.
      //
      // Whether the restore is still WANTED is derived from the thread itself,
      // not accumulated in a counter. `sendHitlResume` also reports
      // "not reached" when a newer interaction aborted it, and its continuation
      // can settle arbitrarily late — but if the user has genuinely moved on,
      // the new turn has already appended its optimistic user message under a
      // DIFFERENT exchange_id, so the thread says so. A turn that failed before
      // committing (write barrier, prepare-execution, the token floor) appends
      // nothing, which is exactly when the prompt should come back.
      //
      // This replaced a turn-generation counter with rollbacks and ownership:
      // three rounds of review found three holes in it (bumping on rejected
      // sends, a bail that skipped the rollback, one rollback slot with several
      // owners). Nothing here accumulates, so there is nothing to unwind.
      const restoreIfStillWanted = () => {
        if (activeSessionIdRef.current !== prompt.session_id) return;
        const thread = latestMessagesRef.current;
        const last = thread.length > 0 ? thread[thread.length - 1] : undefined;
        if (last && last.exchange_id !== prompt.exchange_id) return;
        // Functional update: a newer awaiting_human that arrived meanwhile owns
        // the slot and must not be stomped.
        setPendingHitl((current) => current ?? prompt);
      };
      void sendHitlResume(prompt, answer, freeText)
        .then((reached) => {
          if (reached) {
            if (hitlDraftOwnerRef.current === draftOwner) setHitlFreeText("");
            return;
          }
          restoreIfStillWanted();
        })
        // `pendingHitl` is already cleared, so these are the ONLY paths that can
        // put it back — a rejection would strand the checkpoint exactly like the
        // silent refusal this restore exists to prevent, and surface as an
        // unhandled rejection on top.
        .catch((err) => {
          console.error("[useManagedChat] HITL resume rejected; restoring the prompt", err);
          restoreIfStillWanted();
        });
    },
    [maxChatInputChars, pendingHitl, sendHitlResume],
  );

  const startNewConversation = useCallback(() => {
    setPendingHitl(null);
    hitlDraftOwnerRef.current += 1;
    setHitlFreeText("");
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
  // message of a brand-new conversation. Optimistic for a snappy UI; on a
  // failed PATCH, rolled back — but ONLY if:
  // - this call is still the most recent one FOR THIS SID (per-sid
  //   generation counter), so a slow/failed old write can never stomp a
  //   newer selection for the SAME session, regardless of which write's
  //   network response lands first (both are additionally serialized
  //   per-sid — see `enqueueSessionWrite` — so this guard is defense-in-depth
  //   against the fact that the optimistic update itself is synchronous and
  //   not part of that serialization);
  // - AND `sid` is still the currently active session (`activeSessionIdRef`)
  //   — a write for session A settling after the user has navigated to
  //   session B must never touch B's `contextPromptIds` (a single, shared
  //   piece of UI state, not itself keyed by session) or show a toast in B's
  //   context. A's own write still completes normally server-side either
  //   way; only the UI-facing side effects are suppressed.
  const setContextPrompts = useCallback(
    (ids: string[]) => {
      const sid = ensureSessionForAttachments();
      const myGeneration = (contextPromptGenerationBySidRef.current.get(sid) ?? 0) + 1;
      contextPromptGenerationBySidRef.current.set(sid, myGeneration);
      hasLocalMutationForActiveSessionRef.current = true;
      setContextPromptIds(ids);
      void enqueueSessionWrite(
        sid,
        () => refreshSession({ teamId, sessionId: sid, updateSessionRequest: { context_prompt_ids: ids } }).unwrap(),
        (error) => {
          if (activeSessionIdRef.current !== sid) {
            // The user has navigated away from `sid` entirely — its write
            // still failed for real (surfaced nowhere now, by design: there
            // is no longer a UI context to attach the error to), but must
            // not touch whatever session is displayed now.
            return;
          }
          if (myGeneration !== contextPromptGenerationBySidRef.current.get(sid)) {
            // Superseded by a newer selection for this SAME session — that
            // one's own outcome now governs the UI; showing an error for a
            // choice the user has already moved past would be confusing
            // and, worse, could silently revert their newer, already-
            // confirmed selection.
            return;
          }
          setContextPromptIds(lastConfirmedContextPromptIdsBySidRef.current.get(sid) ?? []);
          notifyApiError(error, {
            summary: t("chatbot.errors.contextPromptSaveFailedSummary"),
            fallbackDetail: t("chatbot.errors.contextPromptSaveFailedDetail"),
          });
        },
      ).then((result) => {
        // Always recorded, even for a no-longer-active sid — this is the
        // durable per-session bookkeeping a LATER visit to `sid` (or a
        // still-current write for it) may need, not a UI side effect.
        if (result.ok) lastConfirmedContextPromptIdsBySidRef.current.set(sid, ids);
      });
    },
    [enqueueSessionWrite, ensureSessionForAttachments, notifyApiError, refreshSession, t, teamId],
  );

  return {
    sessionId,
    sessionTitle,
    agentDisplayName,
    capabilityIds,
    chatControls,
    input,
    setInput,
    inputCharacterCount,
    inputTooLong,
    maxChatInputChars,
    pendingHitl,
    hitlFreeText,
    setHitlFreeText,
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
    reasoning: composer.reasoning,
    setReasoning: composer.setReasoning,
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
