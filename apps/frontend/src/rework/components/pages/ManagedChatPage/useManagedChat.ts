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
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import type { ExecutionPreparation } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useComposerSettings } from "./useComposerSettings";
import { documentSelectionTurnOptions } from "./documentSelectionTurnOptions";
import { DOCUMENT_SELECTION_SUPPORTED } from "@shared/molecules/DocumentLibraryScopePicker/documentLibrarySelection";
import { useSearchParams } from "react-router-dom";
import { v4 as uuidv4 } from "uuid";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { useChatSse } from "@hooks/useChatSse";
import type { HitlBatchAnswer, InterruptedRunChoice, RuntimeAwaitingHumanEvent } from "@hooks/useChatSse";
import { hitlHoldsComposer } from "./hitlHoldsComposer";
import {
  useListAgentInstancesQuery,
  useUpdateSessionMutation,
  useCreateSessionMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";

import { useConversationAvailability } from "./useConversationAvailability";
import { useSessionHistory } from "./useSessionHistory";
import { useChatAttachments } from "./useChatAttachments";
import { modelChoiceKey, offersReasoning, parseModelChoice } from "../../../features/capabilities/modelChoice";
import { reconstructPendingHitls, toThreadMessages } from "./toThreadMessages";
import type { ChatMessage, SkillInvocation, TurnCommand } from "../../../../slices/runtime/runtimeOpenApi";
import { countUnicodeCodePoints } from "@core/utils/chatInput";
import { hasToolApprovalGrants, rememberToolApprovalGrants } from "@core/utils/toolApprovalGrants";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type { AttachmentSource } from "@rework/types/attachments";
import type { HitlQuestionState } from "@shared/molecules/HitlPrompt/HitlPrompt";

type StagedHitlAnswer = {
  answer: string | boolean | undefined;
  freeText?: string;
  skipped: boolean;
};

function hitlKey(event: RuntimeAwaitingHumanEvent): string {
  return [
    event.session_id,
    event.exchange_id,
    event.payload.occurrence_id ?? event.payload.interrupt_id ?? event.payload.question,
  ].join(":");
}

function answerWithOtherPriority(
  event: RuntimeAwaitingHumanEvent,
  answer: string | boolean | undefined,
  freeText?: string,
): string | boolean | undefined {
  return event.payload.stage === "agent_question" &&
    event.payload.free_text &&
    event.payload.choices?.length &&
    freeText?.trim()
    ? undefined
    : answer;
}

// Typed text stays a draft until the person validates it (button or shortcut).
function resolvedHitlAnswer(
  event: RuntimeAwaitingHumanEvent,
  stagedAnswers: ReadonlyMap<string, StagedHitlAnswer>,
): StagedHitlAnswer | undefined {
  return stagedAnswers.get(hitlKey(event));
}

// ── Hook ──────────────────────────────────────────────────────────────────────

interface UseManagedChatParams {
  teamId: string;
  agentInstanceId: string;
  spaceId?: string;
}

type PendingMessage = { id: string; text: string; status: "waiting" | "offered" | "uncertain" };

export function useManagedChat({ teamId, agentInstanceId, spaceId = "" }: UseManagedChatParams) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { showError, showWarn } = useToast();
  const { notifyApiError } = useApiErrorToast();
  const { t } = useTranslation();
  const { agentsNicknameSingular } = useFrontendProperties();

  const sessionId = searchParams.get("session");
  const actorRef = useRef(KeyCloakService.GetSessionIdentity());
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
  const isScopeCurrent = useCallback(
    () => mountedRef.current && actorRef.current === KeyCloakService.GetSessionIdentity(),
    [],
  );
  const [persistedSessionId, setPersistedSessionId] = useState<string | null>(null);
  const visibleSessionRef = useRef(sessionId);
  const sameSession = visibleSessionRef.current === sessionId;
  const [configurationRefused, setConfigurationRefused] = useState(false);
  const composerRef = useRef<ReturnType<typeof useComposerSettings> | null>(null);
  const acceptPreparation = useCallback((prep: ExecutionPreparation) => {
    composerRef.current?.acceptPreparation(prep.agent_configuration_revision, prep.chat_controls);
  }, []);
  const [input, setInput] = useState("");
  const [pendingMessages, setPendingMessages] = useState<PendingMessage[]>([]);
  const queuedStartRef = useRef<PendingMessage | null>(null);
  const queueDrainRef = useRef(false);
  const executionDisabledRef = useRef(false);
  const locallyCreatedSessionIdRef = useRef<string | null>(null);
  const sessionCreatingIdsRef = useRef<Set<string>>(new Set());
  const sessionCreateFailedIdRef = useRef<Set<string>>(new Set());
  const confirmedSessionIdsRef = useRef<Set<string>>(new Set());
  const failedContextWriteIdsRef = useRef<Set<string>>(new Set());
  // `text`/`command` are what went on the wire, so a Restart re-sends the same turn.
  const submittedDraftRef = useRef<{
    sessionId: string;
    draft: string;
    text: string;
    command?: TurnCommand;
    skills?: SkillInvocation[];
  } | null>(null);
  const [pendingHitls, setPendingHitls] = useState<RuntimeAwaitingHumanEvent[]>([]);
  const pendingHitlsRef = useRef<RuntimeAwaitingHumanEvent[]>([]);
  const [selectedHitlKey, setSelectedHitlKey] = useState<string | null>(null);
  const lastHitlExchangeRef = useRef<string | null>(null);
  const hitlDraftsRef = useRef<Map<string, string>>(new Map());
  const [stagedHitlAnswers, setStagedHitlAnswers] = useState<Map<string, StagedHitlAnswer>>(new Map());
  const stagedHitlAnswersRef = useRef<Map<string, StagedHitlAnswer>>(new Map());
  const replaceStagedHitlAnswers = useCallback((answers: Map<string, StagedHitlAnswer>) => {
    stagedHitlAnswersRef.current = answers;
    setStagedHitlAnswers(answers);
  }, []);
  const replacePendingHitls = useCallback((events: RuntimeAwaitingHumanEvent[]) => {
    pendingHitlsRef.current = events;
    setPendingHitls(events);
  }, []);
  const pendingHitl = pendingHitls.find((event) => hitlKey(event) === selectedHitlKey) ?? pendingHitls[0] ?? null;
  const pendingHitlTabs = pendingHitl?.payload.stage === "agent_question" ? pendingHitls : [];
  const stagedHitlAnswer = pendingHitl ? resolvedHitlAnswer(pendingHitl, stagedHitlAnswers) : undefined;
  const stagedHitlCount = pendingHitlTabs.filter((event) => resolvedHitlAnswer(event, stagedHitlAnswers)).length;
  // One state per tab, in tab order, for the tab icons.
  const hitlTabStates: HitlQuestionState[] = pendingHitlTabs.map((event) => {
    const answer = resolvedHitlAnswer(event, stagedHitlAnswers);
    if (!answer) return "waiting";
    return answer.skipped ? "skipped" : "answered";
  });
  const [resumingAgentQuestionSessionId, setResumingAgentQuestionSessionId] = useState<string | null>(null);
  const hitlResumeOwnerRef = useRef<RuntimeAwaitingHumanEvent | null>(null);
  const hitlResumePreparingRef = useRef<RuntimeAwaitingHumanEvent | null>(null);
  const waitResponseRef = useRef(false);
  const submittedBatchKeysRef = useRef<Set<string>>(new Set());
  const autoApprovalAttemptedRef = useRef(new Set<string>());
  const [hitlFreeText, setHitlFreeText] = useState("");
  // Identifies the HITL prompt that owns `hitlFreeText`. A resume can settle
  // after another prompt has arrived; only its own draft may be cleared.
  const hitlDraftOwnerRef = useRef(0);
  const setSelectedHitlFreeText = useCallback(
    (value: string) => {
      if (executionDisabledRef.current) return;
      const selected =
        pendingHitlsRef.current.find((event) => hitlKey(event) === selectedHitlKey) ?? pendingHitlsRef.current[0];
      if (selected) {
        const key = hitlKey(selected);
        hitlDraftsRef.current.set(key, value);
        // Editing the text withdraws a validated answer until it is validated again.
        const staged = stagedHitlAnswersRef.current.get(key);
        if (staged && value !== (staged.freeText ?? "")) {
          const next = new Map(stagedHitlAnswersRef.current);
          next.delete(key);
          replaceStagedHitlAnswers(next);
        }
      }
      setHitlFreeText(value);
    },
    [selectedHitlKey, replaceStagedHitlAnswers],
  );
  const selectHitlTab = useCallback((event: RuntimeAwaitingHumanEvent) => {
    if (!pendingHitlsRef.current.some((candidate) => hitlKey(candidate) === hitlKey(event))) return;
    setSelectedHitlKey(hitlKey(event));
    setHitlFreeText(hitlDraftsRef.current.get(hitlKey(event)) ?? "");
    hitlDraftOwnerRef.current += 1;
  }, []);
  const stageHitlAnswer = useCallback(
    (answer: string | boolean | undefined, freeText?: string, skipped = false) => {
      if (executionDisabledRef.current) return;
      const current = pendingHitlsRef.current;
      const selected = current.find((event) => hitlKey(event) === selectedHitlKey) ?? current[0];
      if (!selected || current.length < 2) return;
      const nextAnswers = new Map(stagedHitlAnswersRef.current);
      nextAnswers.set(hitlKey(selected), {
        answer: answerWithOtherPriority(selected, answer, freeText),
        freeText,
        skipped,
      });
      replaceStagedHitlAnswers(nextAnswers);
      const index = current.findIndex((event) => hitlKey(event) === hitlKey(selected));
      const next = [...current.slice(index + 1), ...current.slice(0, index)].find(
        (event) => !resolvedHitlAnswer(event, nextAnswers),
      );
      if (next) {
        setSelectedHitlKey(hitlKey(next));
        setHitlFreeText(hitlDraftsRef.current.get(hitlKey(next)) ?? "");
      }
    },
    [replaceStagedHitlAnswers, selectedHitlKey],
  );
  const [sessionTitle, setSessionTitle] = useState<string | null>(null);
  const contextPromptIds: string[] = [];
  const activeSessionIdRef = useRef(sessionId);
  activeSessionIdRef.current = sessionId ?? locallyCreatedSessionIdRef.current;
  // Live mirror of the rendered thread. `handleHitlAnswer`'s continuation
  // settles after arbitrary delay and must read the CURRENT thread, not the one
  // captured when the user answered.
  const latestMessagesRef = useRef<ChatMessage[]>([]);
  // Suppresses the sessionId-change reset when handleSend itself binds a new session.
  const skipResetOnSessionBindRef = useRef(false);
  // The attempt owns preflight before SSE starts. Navigation revokes it even
  // if the user later returns to the same session while creation is pending.
  const sendAttemptRef = useRef<{ sessionId: string; originSessionId: string | null; cancelled: boolean } | null>(null);
  useEffect(
    () => () => {
      if (sendAttemptRef.current) sendAttemptRef.current.cancelled = true;
    },
    [],
  );

  const { currentData: agentInstances } = useListAgentInstancesQuery(
    { spaceId },
    { skip: !spaceId, refetchOnMountOrArgChange: true },
  );
  const agentInstance = agentInstances?.find((i) => i.agent_instance_id === agentInstanceId);
  // Capabilities active in this session — drives the capability side-panel slot
  // (#1979, RFC §9 item 3). The host resolves each id against the plugin index.
  const capabilityIds: string[] = [];

  useEffect(() => {
    const attempt = sendAttemptRef.current;
    if (attempt && sessionId !== attempt.sessionId && sessionId !== attempt.originSessionId) attempt.cancelled = true;
    // A mutation can render the draft route before its new session binding commits.
    if (locallyCreatedSessionIdRef.current !== sessionId) locallyCreatedSessionIdRef.current = null;
  }, [sessionId]);
  const locallyCreatingSession =
    sessionId !== null &&
    sessionId !== persistedSessionId &&
    (locallyCreatedSessionIdRef.current === sessionId || sessionCreateFailedIdRef.current.has(sessionId));
  const {
    sessionData,
    isReadOnly,
    executionDisabled: availabilityDisabled,
    sessionUnavailable,
    historyRevision,
    sessionErrorKey,
    refetchSession,
  } = useConversationAvailability(spaceId, agentInstanceId, sessionId, locallyCreatingSession);
  const agentConfigurationChanged = configurationRefused || sessionData?.agent_configuration_changed === true;
  const executionDisabled = availabilityDisabled || agentConfigurationChanged;
  const agentDisplayName =
    (isReadOnly ? sessionData?.agent_display_name : (agentInstance?.display_name ?? sessionData?.agent_display_name)) ??
    t("rework.sidebar.chatList.unknownAgent", { agentsNicknameSingular });
  executionDisabledRef.current = executionDisabled;
  if (sessionData) {
    locallyCreatedSessionIdRef.current = null;
    if (sessionId) {
      confirmedSessionIdsRef.current.add(sessionId);
      sessionCreateFailedIdRef.current.delete(sessionId);
    }
  }
  const refetchSessionRef = useRef(refetchSession);
  refetchSessionRef.current = refetchSession;

  const [registerSession] = useCreateSessionMutation();
  const [refreshSession] = useUpdateSessionMutation();
  // Bumps the session's activity timestamp (tile date + chat-list ordering) —
  // called both at send time (so the tile jumps to the top the moment the
  // user hits Enter) and again when the turn completes.
  const touchSessionActivity = useCallback(
    (sid: string) => {
      if (!isScopeCurrent()) return;
      refreshSession({
        spaceId,
        sessionId: sid,
        updateSessionRequest: { updated_at: new Date().toISOString() },
      }).catch(() => {});
    },
    [refreshSession, spaceId, isScopeCurrent],
  );

  const bindSessionId = useCallback(
    (sid: string) => {
      activeSessionIdRef.current = sid;
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

  // Serialize creation and context writes per session so older requests cannot
  // overwrite newer intent. Failed writes settle normally so retries can run.
  const writeTailsRef = useRef<Map<string, Promise<{ ok: boolean; sessionCreation?: boolean }>>>(new Map());

  const enqueueSessionWrite = useCallback(
    (
      sid: string,
      action: () => Promise<unknown>,
      onError: (error: unknown) => void,
      sessionCreation = false,
    ): Promise<{ ok: boolean; sessionCreation?: boolean }> => {
      const previousTail = writeTailsRef.current.get(sid) ?? Promise.resolve({ ok: true });
      const nextTail: Promise<{ ok: boolean; sessionCreation?: boolean }> = previousTail
        .then(() => {
          if (!isScopeCurrent()) throw new Error("Conversation closed");
          return action();
        })
        .then(() => {
          if (!sessionCreation) failedContextWriteIdsRef.current.delete(sid);
          return { ok: true, sessionCreation };
        })
        .catch((error: unknown) => {
          if (!sessionCreation) failedContextWriteIdsRef.current.add(sid);
          onError(error);
          return { ok: false, sessionCreation };
        });
      writeTailsRef.current.set(sid, nextTail);
      return nextTail;
    },
    [isScopeCurrent],
  );

  // Re-read after each await so writes queued during a flush also settle before
  // sending. Creation confirmation cannot clear an unresolved context failure.
  const flushSessionWrites = useCallback(async (sid: string | null): Promise<boolean> => {
    if (!sid) return true;
    let ok = true;
    let observedTail: Promise<{ ok: boolean; sessionCreation?: boolean }> | undefined;
    for (;;) {
      const currentTail = writeTailsRef.current.get(sid);
      if (!currentTail || currentTail === observedTail) return ok;
      observedTail = currentTail;
      const result = await currentTail;
      // A confirmed row recovers a lost creation response, not failed context writes.
      ok =
        !failedContextWriteIdsRef.current.has(sid) &&
        (result.ok || Boolean(result.sessionCreation && confirmedSessionIdsRef.current.has(sid)));
    }
  }, []);

  // Stabilized (not inlined at the useChatSse call site below): useChatSse's
  // own send()/sendHitlResume() memoize around these callbacks, so an inline
  // arrow here — recreated on every useManagedChat render, including every
  // composer keystroke — would silently invalidate that memoization on every
  // keystroke too, cascading into handleHitlAnswer below and defeating
  // ConversationThread's React.memo (#2221).
  const handleAwaitingHuman = useCallback(
    (event: RuntimeAwaitingHumanEvent) => {
      if (submittedBatchKeysRef.current.has(hitlKey(event))) return;
      const current = pendingHitlsRef.current;
      const sameGroup = event.payload.stage === "agent_question" && lastHitlExchangeRef.current === event.exchange_id;
      if (sameGroup && current.some((candidate) => hitlKey(candidate) === hitlKey(event))) return;
      const next =
        sameGroup && current.every((candidate) => candidate.payload.stage === "agent_question")
          ? [...current, event]
          : [event];
      if (!sameGroup) {
        submittedBatchKeysRef.current = new Set();
        hitlDraftsRef.current.clear();
        replaceStagedHitlAnswers(new Map());
      }
      if (!sameGroup || current.length === 0) {
        setSelectedHitlKey(null);
        setHitlFreeText(hitlDraftsRef.current.get(hitlKey(event)) ?? "");
        hitlDraftOwnerRef.current += 1;
      }
      lastHitlExchangeRef.current = event.exchange_id;
      replacePendingHitls(next);
    },
    [replacePendingHitls, replaceStagedHitlAnswers],
  );
  const handleChatError = useCallback(
    (msg: string, code?: string) => {
      if (code === "agent_configuration_changed") setConfigurationRefused(true);
      const resumePreparing = hitlResumePreparingRef.current?.session_id === activeSessionIdRef.current;
      setPendingMessages((current) => {
        const queued = queuedStartRef.current;
        const pending = queued && !current.some((message) => message.id === queued.id) ? [queued, ...current] : current;
        return pending.map((message) =>
          (message.status === "offered" && !resumePreparing) || message.id === queued?.id
            ? { ...message, status: "uncertain" }
            : message,
        );
      });
      showError({ summary: "Agent error", detail: msg });
      refetchSessionRef.current();
    },
    [showError],
  );
  // Fires only once prepare-execution has actually succeeded and the turn is
  // really starting — clearing the composer any earlier would lose the
  // user's text/attachments on a prepare-execution failure (404/503/network).
  const handleTurnStarted = useCallback(() => {
    if (queuedStartRef.current) {
      const id = queuedStartRef.current.id;
      setPendingMessages((current) => current.filter((message) => message.id !== id));
      return;
    }
    setInput("");
  }, []);
  const handleTurnRejected = useCallback((_wireDraft: string, rejectedSessionId: string) => {
    if (queuedStartRef.current) {
      const queued = { ...queuedStartRef.current, status: "uncertain" as const };
      setPendingMessages((current) =>
        current.some((message) => message.id === queued.id) ? current : [queued, ...current],
      );
      return;
    }
    const submitted = submittedDraftRef.current;
    if (activeSessionIdRef.current !== rejectedSessionId || submitted?.sessionId !== rejectedSessionId) return;
    setInput(submitted.draft);
  }, []);
  const isTurnCurrent = useCallback(
    (turnSessionId: string) => {
      const attempt = sendAttemptRef.current;
      return (
        isScopeCurrent() &&
        activeSessionIdRef.current === turnSessionId &&
        !(attempt?.sessionId === turnSessionId && attempt.cancelled)
      );
    },
    [isScopeCurrent],
  );

  const isExecutionAllowed = useCallback(() => isScopeCurrent() && !executionDisabledRef.current, [isScopeCurrent]);
  const handleSteeredMessage = useCallback((messageId: string, deliveredSessionId: string) => {
    if (activeSessionIdRef.current !== deliveredSessionId) return;
    setPendingMessages((current) => current.filter((message) => message.id !== messageId));
  }, []);

  const {
    messages,
    waitResponse,
    chatControls,
    maxChatInputChars,
    preparation,
    preparationUnavailable,
    preparationErrorDetail,
    prepareChatControls,
    steerActiveTurn,
    send,
    sendHitlResume,
    abort,
    reset,
    replaceAllMessages,
  } = useChatSse({
    agentInstanceId,
    teamId,
    spaceId,
    flushPendingWrites: flushSessionWrites,
    onBindDraftAgentToSessionId: bindSessionId,
    onTurnPersisted: useCallback(
      (sid: string) => {
        touchSessionActivity(sid);
        if (activeSessionIdRef.current === sid) setPersistedSessionId(sid);
      },
      [touchSessionActivity],
    ),
    onSteeredMessage: handleSteeredMessage,
    onAwaitingHuman: handleAwaitingHuman,
    onError: handleChatError,
    onPreparation: acceptPreparation,
    onTurnStarted: handleTurnStarted,
    onTurnRejected: handleTurnRejected,
    isTurnCurrent,
    isExecutionAllowed,
  });
  waitResponseRef.current = waitResponse;
  const canSendAllHitl =
    pendingHitlTabs.length > 1 &&
    pendingHitlTabs.every((event) => {
      const answer = resolvedHitlAnswer(event, stagedHitlAnswers);
      if (!answer) return false;
      if (!answer.skipped && answer.answer === undefined && !answer.freeText?.trim()) return false;
      return (
        answer.freeText === undefined ||
        maxChatInputChars === undefined ||
        countUnicodeCodePoints(answer.freeText) <= maxChatInputChars
      );
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
  const isTurnActive = useCallback(() => waitResponseRef.current, []);
  const getCurrentMessages = useCallback(() => latestMessagesRef.current, []);

  const composer = useComposerSettings(sessionId, chatControls, preparation?.models, `${spaceId}:${agentInstanceId}`);
  composerRef.current = composer;
  useEffect(() => {
    visibleSessionRef.current = sessionId;
    if (skipResetOnSessionBindRef.current) {
      console.debug(
        `[useManagedChat] sessionId changed → skipping reset (bound by handleSend) — sessionId=${sessionId ?? "null"}`,
      );
      skipResetOnSessionBindRef.current = false;
      return;
    }
    setConfigurationRefused(false);
    console.debug(`[useManagedChat] sessionId changed → reset() — sessionId=${sessionId ?? "null"}`);
    reset();
    // reset() aborts any in-flight turn synchronously, but the waitResponse
    // STATE only flips false on the next render — too late for the history
    // effect running later in this same commit, whose isTurnActive() must
    // already see "no live turn" or a cached thread would refuse to render.
    waitResponseRef.current = false;
    replacePendingHitls([]);
    hitlResumeOwnerRef.current = null;
    hitlResumePreparingRef.current = null;
    setResumingAgentQuestionSessionId(null);
    lastHitlExchangeRef.current = null;
    submittedBatchKeysRef.current = new Set();
    hitlDraftsRef.current.clear();
    replaceStagedHitlAnswers(new Map());
    setSelectedHitlKey(null);
    hitlDraftOwnerRef.current += 1;
    setHitlFreeText("");
    setInput("");
    setPendingMessages([]);
    setSessionTitle(null);
    // A genuine entry into a (new or different) session — normal
    // rehydration governs from here until the first local mutation.
    composer.reset(sessionId, chatControlsRef.current);
  }, [sessionId, reset, composer.reset, replacePendingHitls, replaceStagedHitlAnswers]);

  // Reading an existing conversation needs no execution preparation. Typing
  // expresses send intent; a fresh draft can prepare immediately.
  const preparingExecution = !sessionId || input.length > 0;
  const requestedModel = useMemo(() => {
    try {
      return { choice: composer.chatProfileId ? parseModelChoice(composer.chatProfileId) : undefined, error: null };
    } catch {
      return { choice: undefined, error: "The saved model choice must be selected again in the Models menu." };
    }
  }, [composer.chatProfileId]);
  const preparedModelKey = preparation?.model_choice ? modelChoiceKey(preparation.model_choice) : null;
  const requestedModelKey = requestedModel.choice ? modelChoiceKey(requestedModel.choice) : null;
  const modelPreparationCurrent = preparation !== undefined && preparedModelKey === requestedModelKey;
  const modelPreparationError =
    requestedModel.error ?? (modelPreparationCurrent ? preparation?.model_error?.message : null);
  const modelPreparationPending =
    (!sessionId && composer.agentConfigurationRevision === null) ||
    (preparingExecution && !preparationUnavailable && !modelPreparationCurrent);
  useEffect(() => {
    if (executionDisabled || !sameSession || !preparingExecution || (sessionId && locallyCreatingSession)) return;
    const request = prepareChatControls(sessionId, requestedModel.choice);
    void request.catch(() => refetchSessionRef.current());
    return () => request.abort();
  }, [
    sessionId,
    executionDisabled,
    preparingExecution,
    prepareChatControls,
    sameSession,
    locallyCreatingSession,
    requestedModel,
  ]);

  useEffect(() => {
    if (sessionData) setSessionTitle(sessionData.title);
  }, [sessionData]);

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
      submittedBatchKeysRef.current = new Set();
      hitlDraftsRef.current.clear();
      replaceStagedHitlAnswers(new Map());
      setHitlFreeText("");
      setSelectedHitlKey(null);
      const pending = reconstructPendingHitls(msgs);
      lastHitlExchangeRef.current = pending[0]?.exchange_id ?? null;
      replacePendingHitls(pending);
    },
    [replaceAllMessages, replacePendingHitls, replaceStagedHitlAnswers],
  );

  const {
    isLoading: isLoadingHistory,
    isSettled: isHistorySettled,
    isUnavailable: historyUnavailable,
    errorKey: historyErrorKey,
  } = useSessionHistory({
    sessionId: locallyCreatingSession && !sessionData ? null : sessionId,
    spaceId,
    revision: historyRevision,
    messagesUrl: sessionData ? (sessionData.messages_url ?? null) : sessionUnavailable ? null : undefined,
    onLoaded: handleHistoryLoaded,
    isTurnActive,
    getCurrentMessages,
  });

  const mayShowMessages = sameSession && !sessionUnavailable && (!historyUnavailable || waitResponse);
  const threadMessages = useMemo(
    () => toThreadMessages(mayShowMessages ? messages : [], waitResponse),
    [mayShowMessages, messages, waitResponse],
  );
  executionDisabledRef.current = executionDisabled;
  const attachments = useChatAttachments({
    spaceId,
    sessionId,
    enabled: !executionDisabled,
    canUpload: chatControls.some((control) => control.widget === "attach_files"),
  });

  const notifySessionSaveFailed = useCallback(
    (error: unknown) => {
      if (normalizeApiError(error).code === "agent_configuration_changed") {
        handleChatError(t("chatbot.agentConfigurationChanged"), "agent_configuration_changed");
        return;
      }
      notifyApiError(error, {
        summary: t("chatbot.errors.sessionSaveFailedSummary"),
        fallbackDetail: t("chatbot.errors.sessionSaveFailedDetail"),
      });
    },
    [notifyApiError, t, handleChatError],
  );

  // Enqueues the session-row creation POST onto this sid's write tail, so it
  // always precedes any context-prompt PATCH for the same sid (both go
  // through `enqueueSessionWrite` keyed on `sid`). Marks/clears `sid` in
  // `sessionCreateFailedIdRef` so a retry against the same (already
  // URL-bound) sid re-attempts creation instead of silently skipping it.
  const createSessionRow = useCallback(
    (sid: string, title: string) => {
      const revision = composer.agentConfigurationRevision;
      if (revision === null || sessionCreatingIdsRef.current.has(sid)) return;
      sessionCreatingIdsRef.current.add(sid);
      locallyCreatedSessionIdRef.current = sid;
      void enqueueSessionWrite(
        sid,
        () =>
          registerSession({
            spaceId,
            createSessionRequest: {
              session_id: sid,
              agent_instance_id: agentInstanceId,
              agent_configuration_revision: revision,
              title,
            },
          }).unwrap(),
        (error) => {
          if (!confirmedSessionIdsRef.current.has(sid)) sessionCreateFailedIdRef.current.add(sid);
          if (isTurnCurrent(sid)) notifySessionSaveFailed(error);
        },
        true,
      ).then((result) => {
        sessionCreatingIdsRef.current.delete(sid);
        if (result.ok) {
          sessionCreateFailedIdRef.current.delete(sid);
          confirmedSessionIdsRef.current.add(sid);
        }
      });
    },
    [
      agentInstanceId,
      enqueueSessionWrite,
      notifySessionSaveFailed,
      registerSession,
      spaceId,
      composer.agentConfigurationRevision,
      isTurnCurrent,
    ],
  );

  const [attachmentPreparations, setAttachmentPreparations] = useState<Record<string, number>>({});
  const attachmentPreparationsRef = useRef<Record<string, number>>({});
  const ensureSessionForAttachments = useCallback(async (): Promise<string | null> => {
    let sid = sessionId ?? locallyCreatedSessionIdRef.current;
    const needsCreate = !sid || sessionCreateFailedIdRef.current.has(sid);
    if (!sid) {
      sid = uuidv4();
      locallyCreatedSessionIdRef.current = sid;
      activeSessionIdRef.current = sid;
      skipResetOnSessionBindRef.current = true;
      composer.bindSession(sid);
      bindSessionId(sid);
    }
    if (needsCreate) createSessionRow(sid, "New conversation");
    if (!(await flushSessionWrites(sid)) || !confirmedSessionIdsRef.current.has(sid)) return null;
    return isScopeCurrent() && activeSessionIdRef.current === sid ? sid : null;
  }, [bindSessionId, composer.bindSession, createSessionRow, flushSessionWrites, isScopeCurrent, sessionId]);

  const handleAddAttachments = useCallback(
    async (files: File[], source: AttachmentSource) => {
      if (executionDisabledRef.current || !chatControlsRef.current.some((control) => control.widget === "attach_files"))
        return;
      const confirmation = ensureSessionForAttachments();
      const pendingSid = activeSessionIdRef.current;
      if (!pendingSid) return;
      const updatePending = (delta: number) => {
        const next = {
          ...attachmentPreparationsRef.current,
          [pendingSid]: (attachmentPreparationsRef.current[pendingSid] ?? 0) + delta,
        };
        attachmentPreparationsRef.current = next;
        setAttachmentPreparations(next);
      };
      updatePending(1);
      try {
        const sid = await confirmation;
        if (
          sid &&
          !executionDisabledRef.current &&
          chatControlsRef.current.some((control) => control.widget === "attach_files")
        )
          await attachments.addFiles(files, source, sid);
      } finally {
        updatePending(-1);
      }
    },
    [attachments.addFiles, ensureSessionForAttachments],
  );

  const buildTurnContext = useCallback(
    (_resumedExchangeId?: string) => ({
      runtimeContext: {
        ...(composer.chatProfileId ? { model_choice: parseModelChoice(composer.chatProfileId) } : {}),
        ...(offersReasoning(chatControls, preparation?.models, composer.chatProfileId)
          ? { reasoning: composer.reasoning }
          : {}),
      },
      turnOptions:
        DOCUMENT_SELECTION_SUPPORTED &&
        (composer.documentSelection !== null || chatControls.some((control) => control.widget === "document_scope"))
          ? documentSelectionTurnOptions(composer.documentSelection)
          : undefined,
    }),
    [composer.chatProfileId, composer.reasoning, composer.documentSelection, chatControls, preparation?.models],
  );

  // Read at answer time so handleHitlAnswer keeps its identity across keystrokes.
  const buildTurnContextRef = useRef(buildTurnContext);
  buildTurnContextRef.current = buildTurnContext;

  // One send path for both entry points: the composer's own draft, and a
  // command whose text comes from the prompt behind it and never passed
  // through the composer. `turnCommand` only adds the descriptor to the
  // context; every guard, session write and restore below is shared.
  const sendTurn = useCallback(
    async (
      text: string,
      turnCommand?: TurnCommand,
      interrupted?: InterruptedRunChoice,
      skills?: SkillInvocation[],
      queued?: boolean,
    ): Promise<boolean> => {
      const hasAttachments =
        !queued && chatControls.some((control) => control.widget === "attach_files") && attachments.hasReadyAttachments;
      console.debug(
        `[useManagedChat] sendTurn() — inputChars=${inputCharacterCount} waitResponse=${waitResponse} sessionId=${sessionId ?? "null"}`,
      );
      const awaitingAgentQuestion =
        hitlHoldsComposer(pendingHitl, sessionId) || hitlHoldsComposer(hitlResumeOwnerRef.current, sessionId);
      if (
        executionDisabledRef.current ||
        (!text && !hasAttachments) ||
        waitResponse ||
        awaitingAgentQuestion ||
        attachments.hasUploadingAttachments ||
        (attachmentPreparationsRef.current[activeSessionIdRef.current ?? ""] ?? 0) > 0 ||
        (!queued && inputTooLong) ||
        modelPreparationError ||
        modelPreparationPending
      ) {
        console.debug(
          `[useManagedChat] sendTurn() BLOCKED — hasText=${!!text} attachments=${!!hasAttachments} waitResponse=${waitResponse} uploading=${attachments.hasUploadingAttachments} inputTooLong=${inputTooLong}`,
        );
        return false;
      }
      if (sendAttemptRef.current && !sendAttemptRef.current.cancelled) {
        console.debug("[useManagedChat] sendTurn() IGNORED — a send is already in flight");
        return false;
      }
      // `inputTooLong` above measures the composer draft, which on a command
      // is the short command line — not what goes on the wire. The runtime
      // rejects an oversized turn either way; checking here spares the round
      // trip and says so before the send rather than after.
      if (
        turnCommand !== undefined &&
        maxChatInputChars !== undefined &&
        countUnicodeCodePoints(text) > maxChatInputChars
      ) {
        showError({
          summary: t("chatbot.commandMenu.runErrorSummary"),
          detail: t("chatbot.errors.chatInputTooLong", { limit: maxChatInputChars }),
        });
        return false;
      }
      const attempt = { sessionId: sessionId ?? uuidv4(), originSessionId: sessionId, cancelled: false };
      sendAttemptRef.current = attempt;
      try {
        // Composer input is left untouched until the session write barrier below
        // confirms success — clearing it eagerly would lose the user's message if
        // session creation fails, forcing a retype on retry.
        let sid = sessionId;
        const needsCreate = !sid || sessionCreateFailedIdRef.current.has(sid);
        if (!sid) {
          sid = attempt.sessionId;
          console.debug(`[useManagedChat] sendTurn() — no session, creating new sid=${sid}, calling bindSessionId`);
          skipResetOnSessionBindRef.current = true;
          // See ensureSessionForAttachments: makes this turn's composer settings
          // durable under the id they were picked for.
          composer.bindSession(sid);
          bindSessionId(sid);
        }
        if (needsCreate) {
          // Tracked so the barrier below (flushSessionWrites) waits for the
          // session row before prepare-execution runs, and surfaces a toast +
          // aborts the send if the row was never actually created. Re-fires on a
          // retry against the same (already URL-bound) sid whose prior creation
          // failed — see `sessionCreateFailedIdRef`.
          // A command turn titles itself from what was RUN, not from the
          // composer (which may hold only the partial query `Enter` matched)
          // and not from the prompt body (which would give every run of one
          // command the same name). The prompt's name reads best; any text
          // typed after the command is what makes this conversation its own.
          // Nothing retitles a session afterwards, so this is the only shot.
          const titleSource = turnCommand
            ? [turnCommand.prompt_name || `/${turnCommand.command}`, turnCommand.appended_text]
                .filter(Boolean)
                .join(" — ")
            : text;
          createSessionRow(sid, titleSource ? titleSource.slice(0, 120) : "Attached files");
        }

        // Block the send entirely on any pending or just-failed session write —
        // including a context-prompt PATCH fired earlier that hasn't committed
        // yet. A failure already triggered its own toast (via the write's
        // onError above); nothing further to show here, just don't proceed —
        // the message stays in the composer for an explicit retry.
        const writesOk = await flushSessionWrites(sid);
        if (
          !writesOk ||
          !isScopeCurrent() ||
          executionDisabledRef.current ||
          attempt.cancelled ||
          activeSessionIdRef.current !== sid
        ) {
          console.debug("[useManagedChat] sendTurn() ABORTED — a pending session write failed");
          return false;
        }

        // Input/attachments stay untouched here too — cleared only from
        // onTurnStarted, once prepare-execution inside send() has actually
        // succeeded. A prepare-execution failure (404/503/network) must never
        // wipe text the user still needs to retry with; see useChatSse.ts.
        replacePendingHitls([]);
        lastHitlExchangeRef.current = null;
        submittedBatchKeysRef.current = new Set();
        hitlDraftsRef.current.clear();
        replaceStagedHitlAnswers(new Map());
        setSelectedHitlKey(null);
        console.debug(`[useManagedChat] sendTurn() — calling send() with sid=${sid}`);
        const { runtimeContext, turnOptions } = buildTurnContext();
        touchSessionActivity(sid);
        // `send()` receives the trimmed wire value, but a backend rejection must
        // restore the complete editable draft, including surrounding whitespace —
        // for a command, the command line the user actually typed.
        submittedDraftRef.current = {
          sessionId: sid,
          draft: queued ? text : input,
          text,
          command: turnCommand,
          skills,
        };
        return send(
          text,
          sid,
          {
            ...runtimeContext,
            ...(turnCommand ? { command: turnCommand } : {}),
            ...(skills?.length ? { skills } : {}),
          },
          turnOptions,
          interrupted,
        );
      } catch (error) {
        if (isScopeCurrent() && !attempt.cancelled && activeSessionIdRef.current === attempt.sessionId)
          notifySessionSaveFailed(error);
        return false;
      } finally {
        if (sendAttemptRef.current === attempt) sendAttemptRef.current = null;
      }
    },
    [
      attachments.hasReadyAttachments,
      chatControls,
      attachments.hasUploadingAttachments,
      input,
      inputCharacterCount,
      inputTooLong,
      modelPreparationError,
      modelPreparationPending,
      waitResponse,
      pendingHitl,
      replacePendingHitls,
      replaceStagedHitlAnswers,
      sessionId,
      buildTurnContext,
      composer.bindSession,
      bindSessionId,
      createSessionRow,
      flushSessionWrites,
      isScopeCurrent,
      touchSessionActivity,
      send,
      maxChatInputChars,
      notifySessionSaveFailed,
      showError,
      t,
    ],
  );

  const handleSend = useCallback(async () => {
    if (waitResponse || pendingMessages.length > 0) {
      if (attachments.hasUploadingAttachments) {
        showWarn({ summary: t("chatbot.pendingMessages.textOnly") });
        return;
      }
      const text = input.trim();
      if (!text || inputTooLong) return;
      setPendingMessages((current) => [...current, { id: uuidv4(), text, status: "waiting" }]);
      setInput("");
      return;
    }
    await sendTurn(input.trim());
  }, [
    sendTurn,
    input,
    waitResponse,
    pendingMessages.length,
    attachments.hasUploadingAttachments,
    inputTooLong,
    showWarn,
    t,
  ]);

  const editPendingMessage = useCallback(
    (id: string) => {
      const message = pendingMessages.find((item) => item.id === id && item.status === "waiting");
      if (!message) return;
      setInput(message.text);
      setPendingMessages((current) => current.filter((item) => item.id !== id));
    },
    [pendingMessages],
  );
  const removePendingMessage = useCallback((id: string) => {
    setPendingMessages((current) => current.filter((item) => item.id !== id || item.status !== "waiting"));
  }, []);
  const retryPendingMessage = useCallback(
    (id: string) => {
      if (waitResponse) return;
      setPendingMessages((current) =>
        current.map((item) => (item.id === id && item.status === "uncertain" ? { ...item, status: "waiting" } : item)),
      );
    },
    [waitResponse],
  );
  const forcePendingMessage = useCallback(
    async (id: string) => {
      const message = pendingMessages.find((item) => item.id === id && item.status === "waiting");
      if (!message || !sessionId || !waitResponse) return;
      setPendingMessages((current) => current.map((item) => (item.id === id ? { ...item, status: "offered" } : item)));
      const result = await steerActiveTurn(sessionId, id, message.text);
      if (result !== "accepted") {
        setPendingMessages((current) =>
          current.map((item) =>
            item.id === id ? { ...item, status: result === "uncertain" ? "uncertain" : "waiting" } : item,
          ),
        );
        if (result === "uncertain") {
          showWarn({ summary: t("chatbot.pendingMessages.uncertain") });
        } else {
          showWarn({ summary: t("chatbot.pendingMessages.forceUnavailable") });
        }
      }
    },
    [pendingMessages, sessionId, waitResponse, steerActiveTurn, showWarn, t],
  );

  useEffect(() => {
    if (
      waitResponse ||
      !sessionId ||
      executionDisabledRef.current ||
      pendingHitl ||
      hitlResumeOwnerRef.current?.session_id === sessionId ||
      attachments.hasUploadingAttachments ||
      (attachmentPreparations[sessionId] ?? 0) > 0 ||
      isLoadingHistory
    )
      return;
    if (pendingMessages.some((message) => message.status === "offered")) {
      setPendingMessages((current) =>
        current.map((message) => (message.status === "offered" ? { ...message, status: "waiting" } : message)),
      );
      return;
    }
    const next = pendingMessages[0];
    if (!next || next.status !== "waiting" || queueDrainRef.current) return;
    queueDrainRef.current = true;
    queuedStartRef.current = next;
    void sendTurn(next.text, undefined, undefined, undefined, true)
      .then((accepted) => {
        if (!accepted) {
          if (activeSessionIdRef.current !== sessionId) return;
          setPendingMessages((current) => {
            const pending = current.some((message) => message.id === next.id) ? current : [next, ...current];
            return pending.map((message) => (message.id === next.id ? { ...message, status: "uncertain" } : message));
          });
        }
      })
      .finally(() => {
        queuedStartRef.current = null;
        queueDrainRef.current = false;
      });
  }, [
    waitResponse,
    sessionId,
    pendingHitl,
    isLoadingHistory,
    pendingMessages,
    sendTurn,
    attachments.hasUploadingAttachments,
    attachmentPreparations,
  ]);
  // Read at answer time, like buildTurnContextRef, so the card's handler keeps
  // its identity across keystrokes.
  const restartLastTurn = () => {
    const submitted = submittedDraftRef.current;
    return sendTurn(submitted?.text ?? input.trim(), submitted?.command, { action: "restart" }, submitted?.skills);
  };
  const restartLastTurnRef = useRef(restartLastTurn);
  restartLastTurnRef.current = restartLastTurn;

  // Runs a prompt command: the assembled text goes on the wire, the descriptor
  // on the turn's context, and the composer keeps the short command line the
  // user typed until the turn actually starts.
  const runSkill = useCallback(
    async (run: { text: string; skills: SkillInvocation[] }) => {
      if (waitResponse) {
        showWarn({ summary: t("chatbot.pendingMessages.textOnly") });
        return;
      }
      await sendTurn(run.text, undefined, undefined, run.skills);
    },
    [sendTurn, waitResponse, showWarn, t],
  );

  const runCommand = useCallback(
    async (run: { text: string; command: TurnCommand; skills?: SkillInvocation[] }) => {
      if (waitResponse) {
        showWarn({ summary: t("chatbot.pendingMessages.textOnly") });
        return;
      }
      await sendTurn(run.text, run.command, undefined, run.skills);
    },
    [sendTurn, waitResponse, showWarn, t],
  );

  const handleHitlAnswer = useCallback(
    (answer: string | boolean | undefined, freeText?: string, skipped = false, rememberApproval = false) => {
      if (executionDisabledRef.current || !pendingHitl || hitlResumeOwnerRef.current === pendingHitl) return;
      if (pendingHitl.payload.stage === "execution_interrupted") {
        // Not a HITL resume: the answer is a new turn that continues or restarts.
        const prompt = pendingHitl;
        const interruptionId = prompt.payload.metadata?.interruption_id;
        replacePendingHitls([]);
        if (answer === "later") return;
        // A request that never started leaves the run interrupted: offer the choice again.
        const restoreIfNotSent = (started: boolean) => {
          if (!started && activeSessionIdRef.current === prompt.session_id) {
            if (pendingHitlsRef.current.length === 0) replacePendingHitls([prompt]);
          }
        };
        if (answer === "continue" && typeof interruptionId === "string" && interruptionId) {
          const { runtimeContext, turnOptions } = buildTurnContextRef.current();
          void send("", prompt.session_id, runtimeContext, turnOptions, { action: "continue", interruptionId }).then(
            restoreIfNotSent,
          );
        } else {
          void restartLastTurnRef.current().then(restoreIfNotSent);
        }
        return;
      }
      if (
        freeText !== undefined &&
        maxChatInputChars !== undefined &&
        countUnicodeCodePoints(freeText) > maxChatInputChars
      ) {
        return;
      }
      const prompt = pendingHitl;
      hitlResumeOwnerRef.current = prompt;
      hitlResumePreparingRef.current = prompt;
      if (prompt.payload.stage === "agent_question") setResumingAgentQuestionSessionId(prompt.session_id);
      const draftOwner = hitlDraftOwnerRef.current;
      const promptsBeforeResume = pendingHitlsRef.current;
      const remaining =
        prompt.payload.stage === "agent_question"
          ? promptsBeforeResume.filter((event) => hitlKey(event) !== hitlKey(prompt))
          : [];
      replacePendingHitls(remaining);
      if (remaining.length > 0) {
        const answeredIndex = promptsBeforeResume.findIndex((event) => hitlKey(event) === hitlKey(prompt));
        const next = remaining[Math.min(answeredIndex, remaining.length - 1)];
        setSelectedHitlKey(hitlKey(next));
        setHitlFreeText(hitlDraftsRef.current.get(hitlKey(next)) ?? "");
        hitlDraftOwnerRef.current += 1;
      }
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
        if (pendingHitlsRef.current === remaining || pendingHitlsRef.current.length === 0) {
          replacePendingHitls(promptsBeforeResume);
          lastHitlExchangeRef.current = prompt.exchange_id;
          setSelectedHitlKey(hitlKey(prompt));
          setHitlFreeText(hitlDraftsRef.current.get(hitlKey(prompt)) ?? "");
        }
      };
      const { runtimeContext, turnOptions } = buildTurnContextRef.current(prompt.exchange_id);
      const toolNames = (prompt.payload.pending_calls ?? []).map((call) => call.tool_name);
      const rememberTools =
        rememberApproval && prompt.payload.stage === "tool_approval" && answer === "proceed" && toolNames.length > 0;
      const onAccepted = () => {
        if (hitlResumePreparingRef.current === prompt) hitlResumePreparingRef.current = null;
        if (rememberTools) {
          const saved = rememberToolApprovalGrants(
            { userId: KeyCloakService.GetUserId(), agentInstanceId, sessionId: prompt.session_id },
            toolNames,
          );
          if (!saved) {
            showError({
              summary: t("chatbot.errors.toolApprovalSaveFailedSummary"),
              detail: t("chatbot.errors.toolApprovalSaveFailedDetail"),
            });
          }
        }
      };
      const selectedAnswer = answerWithOtherPriority(prompt, answer, freeText);
      const resume = sendHitlResume(prompt, selectedAnswer, freeText, runtimeContext, turnOptions, skipped, onAccepted);
      void resume
        .then((reached) => {
          if (reached) {
            hitlDraftsRef.current.delete(hitlKey(prompt));
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
        })
        .finally(() => {
          if (hitlResumeOwnerRef.current !== prompt) return;
          hitlResumeOwnerRef.current = null;
          if (hitlResumePreparingRef.current === prompt) hitlResumePreparingRef.current = null;
          if (prompt.payload.stage === "agent_question") setResumingAgentQuestionSessionId(null);
        });
    },
    [agentInstanceId, maxChatInputChars, pendingHitl, replacePendingHitls, send, sendHitlResume, showError, t],
  );

  const submitHitlBatch = useCallback(
    (skipAll: boolean) => {
      if (executionDisabledRef.current) return;
      const prompts = pendingHitlsRef.current;
      if (prompts.length < 2 || prompts.some((event) => event.payload.stage !== "agent_question")) return;
      if (hitlResumeOwnerRef.current) return;
      const answers: HitlBatchAnswer[] = [];
      for (const event of prompts) {
        const staged = skipAll
          ? { answer: undefined, freeText: undefined, skipped: true }
          : resolvedHitlAnswer(event, stagedHitlAnswersRef.current);
        if (!staged || !event.payload.interrupt_id || !event.payload.occurrence_id) return;
        if (!staged.skipped && staged.answer === undefined && !staged.freeText?.trim()) return;
        if (
          staged.freeText &&
          maxChatInputChars !== undefined &&
          countUnicodeCodePoints(staged.freeText) > maxChatInputChars
        )
          return;
        answers.push({
          event,
          ...staged,
          answer: answerWithOtherPriority(event, staged.answer, staged.freeText),
        });
      }
      const owner = prompts[0];
      hitlResumeOwnerRef.current = owner;
      hitlResumePreparingRef.current = owner;
      setResumingAgentQuestionSessionId(owner.session_id);
      const submittedKeys = new Set(prompts.map(hitlKey));
      submittedBatchKeysRef.current = submittedKeys;
      let cleared = false;
      const clearAcceptedBatch = () => {
        if (hitlResumePreparingRef.current === owner) hitlResumePreparingRef.current = null;
        if (cleared) return;
        cleared = true;
        if (activeSessionIdRef.current !== owner.session_id) return;
        const current = pendingHitlsRef.current;
        const remaining = current.filter((event) => !submittedKeys.has(hitlKey(event)));
        if (remaining.length === current.length) return;
        replacePendingHitls(remaining);
        const staged = new Map(stagedHitlAnswersRef.current);
        for (const key of submittedKeys) {
          staged.delete(key);
          hitlDraftsRef.current.delete(key);
        }
        replaceStagedHitlAnswers(staged);
        setSelectedHitlKey(remaining.length ? hitlKey(remaining[0]) : null);
        setHitlFreeText(remaining.length ? (hitlDraftsRef.current.get(hitlKey(remaining[0])) ?? "") : "");
      };
      const { runtimeContext, turnOptions } = buildTurnContextRef.current(owner.exchange_id);
      void sendHitlResume(owner, undefined, undefined, runtimeContext, turnOptions, false, clearAcceptedBatch, answers)
        .then((accepted) => {
          if (!accepted) {
            if (submittedBatchKeysRef.current === submittedKeys) submittedBatchKeysRef.current = new Set();
            return;
          }
          clearAcceptedBatch();
        })
        .catch((error) => {
          console.error("[useManagedChat] HITL batch resume failed", error);
          if (submittedBatchKeysRef.current === submittedKeys) submittedBatchKeysRef.current = new Set();
        })
        .finally(() => {
          if (hitlResumeOwnerRef.current !== owner) return;
          hitlResumeOwnerRef.current = null;
          if (hitlResumePreparingRef.current === owner) hitlResumePreparingRef.current = null;
          setResumingAgentQuestionSessionId(null);
        });
    },
    [maxChatInputChars, replacePendingHitls, replaceStagedHitlAnswers, sendHitlResume],
  );
  const handleSendAllHitl = useCallback(() => submitHitlBatch(false), [submitHitlBatch]);
  const handleSkipAllHitl = useCallback(() => submitHitlBatch(true), [submitHitlBatch]);

  useEffect(() => {
    if (executionDisabled || !pendingHitl || waitResponse || pendingHitl.payload.stage !== "tool_approval") return;
    if (!pendingHitl.payload.choices?.some((choice) => choice.id === "proceed")) return;
    if (activeSessionIdRef.current !== pendingHitl.session_id) return;
    const toolNames = (pendingHitl.payload.pending_calls ?? []).map((call) => call.tool_name);
    const scope = {
      userId: KeyCloakService.GetUserId(),
      agentInstanceId,
      sessionId: pendingHitl.session_id,
    };
    if (!hasToolApprovalGrants(scope, toolNames)) return;
    const occurrence = [
      pendingHitl.session_id,
      pendingHitl.exchange_id,
      pendingHitl.payload.interrupt_id,
      pendingHitl.payload.occurrence_id,
    ].join(":");
    if (autoApprovalAttemptedRef.current.has(occurrence)) return;
    autoApprovalAttemptedRef.current.add(occurrence);
    handleHitlAnswer("proceed");
  }, [agentInstanceId, executionDisabled, handleHitlAnswer, pendingHitl, waitResponse]);

  const startNewConversation = useCallback(() => {
    if (availabilityDisabled && !agentConfigurationChanged) return;
    setConfigurationRefused(false);
    const attempt = sendAttemptRef.current;
    if (attempt) attempt.cancelled = true;
    locallyCreatedSessionIdRef.current = null;
    activeSessionIdRef.current = null;
    composer.discardDraft();
    composer.reset(null, []);
    reset();
    setInput("");
    setPendingMessages([]);
    skipResetOnSessionBindRef.current = false;
    if (!sessionId) void prepareChatControls(null).catch(() => {});
    replacePendingHitls([]);
    lastHitlExchangeRef.current = null;
    submittedBatchKeysRef.current = new Set();
    hitlDraftsRef.current.clear();
    replaceStagedHitlAnswers(new Map());
    setSelectedHitlKey(null);
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
  }, [
    setSearchParams,
    replacePendingHitls,
    replaceStagedHitlAnswers,
    reset,
    sessionId,
    composer.discardDraft,
    composer.reset,
    availabilityDisabled,
    agentConfigurationChanged,
    prepareChatControls,
  ]);

  const commitTitle = useCallback(
    async (title: string) => {
      if (!sessionId || sessionUnavailable) return;
      try {
        const saved = await refreshSession({ spaceId, sessionId, updateSessionRequest: { title } }).unwrap();
        if (isScopeCurrent() && activeSessionIdRef.current === sessionId) setSessionTitle(saved.title);
      } catch (error) {
        if (isScopeCurrent() && activeSessionIdRef.current === sessionId) notifySessionSaveFailed(error);
      }
    },
    [spaceId, sessionId, sessionUnavailable, refreshSession, notifySessionSaveFailed, isScopeCurrent],
  );

  const setContextPrompts = useCallback((_ids: string[]) => {}, []);

  const guardChange = useCallback(
    <Args extends unknown[]>(action: (...args: Args) => unknown) =>
      (...args: Args) => {
        if (!executionDisabledRef.current) return action(...args);
      },
    [],
  );
  const guardedComposer = useMemo(
    () => ({
      setDocumentSelection: guardChange(composer.setDocumentSelection),
      setSearchPolicy: guardChange(composer.setSearchPolicy),
      setRagScope: guardChange(composer.setRagScope),
      setReasoning: guardChange(composer.setReasoning),
      setAskUser: guardChange(composer.setAskUser),
      setChatProfileId: guardChange(composer.setChatProfileId),
    }),
    [
      guardChange,
      composer.setDocumentSelection,
      composer.setSearchPolicy,
      composer.setRagScope,
      composer.setReasoning,
      composer.setAskUser,
      composer.setChatProfileId,
    ],
  );
  const setComposerInput = useMemo(() => guardChange(setInput), [guardChange]);
  const removeAttachment = useMemo(
    () => guardChange(attachments.removeAttachment),
    [guardChange, attachments.removeAttachment],
  );
  const deletePersistedAttachment = useCallback(
    async (id: string) => {
      if (!executionDisabledRef.current) await attachments.deletePersistedAttachment(id);
    },
    [attachments.deletePersistedAttachment],
  );

  return {
    sessionId,
    sessionTitle: sameSession && !sessionUnavailable ? sessionTitle : null,
    agentDisplayName,
    isReadOnly,
    executionDisabled,
    sessionUnavailable,
    agentConfigurationChanged,
    preparationUnavailable,
    preparationErrorDetail,
    modelPreparationError,
    modelPreparationPending,
    historyErrorKey: sessionErrorKey ?? historyErrorKey,
    historyUnavailable,
    agentInstance,
    capabilityIds,
    chatControls,
    models: preparation?.models,
    supportsHitl: preparation?.supports_hitl === true,
    input,
    pendingMessages,
    editPendingMessage,
    removePendingMessage,
    forcePendingMessage,
    retryPendingMessage,
    setInput: setComposerInput,
    inputCharacterCount,
    inputTooLong,
    maxChatInputChars,
    pendingHitl,
    pendingHitlTabs,
    stagedHitlAnswer,
    stagedHitlCount,
    hitlTabStates,
    canSendAllHitl,
    stageHitlAnswer,
    selectHitlTab,
    resumingAgentQuestionSessionId,
    hitlFreeText,
    setHitlFreeText: setSelectedHitlFreeText,
    documentSelection: composer.documentSelection,
    attachments: attachments.attachments,
    persistedAttachments: attachments.persistedAttachments,
    isHydratingAttachments: attachments.isHydratingAttachments,
    attachmentsUploading:
      attachments.hasUploadingAttachments ||
      (attachmentPreparations[sessionId ?? locallyCreatedSessionIdRef.current ?? ""] ?? 0) > 0,
    handleAddAttachments,
    retryAttachmentUpload: async (id: string, file: File) => {
      if (!executionDisabledRef.current && chatControlsRef.current.some((control) => control.widget === "attach_files"))
        await attachments.retryUpload(id, file);
    },
    attachmentListError: attachments.listError,
    refreshAttachments: attachments.refreshAttachments,
    removeAttachment,
    deletePersistedAttachment,
    setDocumentSelection: guardedComposer.setDocumentSelection,
    searchPolicy: composer.searchPolicy,
    setSearchPolicy: guardedComposer.setSearchPolicy,
    ragScope: composer.ragScope,
    setRagScope: guardedComposer.setRagScope,
    reasoning: composer.reasoning,
    setReasoning: guardedComposer.setReasoning,
    askUser: composer.askUser,
    setAskUser: guardedComposer.setAskUser,
    chatProfileId: composer.chatProfileId,
    setChatProfileId: guardedComposer.setChatProfileId,
    contextPromptIds,
    setContextPrompts,
    threadMessages,
    messages: mayShowMessages ? messages : [],
    waitResponse,
    isLoadingHistory,
    isHistorySettled,
    handleSend,
    runCommand,
    runSkill,
    handleHitlAnswer,
    handleSendAllHitl,
    handleSkipAllHitl,
    handleAbort: abort,
    startNewConversation,
    commitTitle,
  };
}
