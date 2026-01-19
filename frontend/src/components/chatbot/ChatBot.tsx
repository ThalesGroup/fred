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

/**
 * ChatBot
 * -------
 * - Owns the conversation view (welcome vs. messages) and message history loading.
 * - Delegates per-session preferences + option widgets to `ConversationOptionsController`.
 * - Avoids flicker on session switch by keeping messages while history loads; welcome shows only when truly empty.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import { AnyAgent } from "../../common/agent.ts";
import { getConfig } from "../../common/config.tsx";
import { useSessionChange } from "../../hooks/useSessionChange.ts";
import { KeyCloakService } from "../../security/KeycloakService.ts";
import {
  ChatAskInput,
  ChatMessage,
  FinalEvent,
  RuntimeContext,
  StreamEvent,
  useCreateSessionAgenticV1ChatbotSessionPostMutation,
  useGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useUploadFileAgenticV1ChatbotUploadPostMutation,
} from "../../slices/agentic/agenticOpenApi.ts";
import {
  TagType,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider.tsx";
import { keyOf, mergeAuthoritative, toWsUrl, upsertOne } from "./ChatBotUtils.tsx";
import ChatBotView from "./ChatBotView.tsx";
import { useConversationOptionsController } from "./ConversationOptionsController.tsx";
import { UserInputContent } from "./user_input/UserInput.tsx";

const HISTORY_TEXT_LIMIT = 1200;

export interface ChatBotError {
  session_id: string | null;
  content: string;
}

// interface TranscriptionResponse {
//   text?: string;
// }

export interface ChatBotProps {
  chatSessionId?: string;
  agents: AnyAgent[];
  runtimeContext?: RuntimeContext;
  onNewSessionCreated: (chatSessionId: string) => void;
}

const ChatBot = ({ chatSessionId, agents, onNewSessionCreated, runtimeContext: baseRuntimeContext }: ChatBotProps) => {
  const isNewConversation = !chatSessionId;

  const { showError } = useToast();
  const webSocketRef = useRef<WebSocket | null>(null);
  const wsTokenRef = useRef<string | null>(null);
  const wsConnectSeqRef = useRef<number>(0);
  // When backend creates a session during first file upload, keep it locally
  // so the immediate next message uses the same session id.
  const pendingSessionIdRef = useRef<string | null>(null);

  // Name of des libs / prompts / templates / chat-context
  const { data: docLibs = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" as TagType });
  const { data: promptResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "prompt" });
  const { data: templateResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "template" });
  const { data: chatContextResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({
    kind: "chat-context",
  });

  const libraryNameMap = useMemo(() => Object.fromEntries(docLibs.map((x) => [x.id, x.name])), [docLibs]);
  const libraryById = useMemo(() => Object.fromEntries(docLibs.map((x) => [x.id, x])), [docLibs]);
  const promptNameMap = useMemo(
    () => Object.fromEntries(promptResources.map((x) => [x.id, x.name ?? x.id])),
    [promptResources],
  );
  const templateNameMap = useMemo(
    () => Object.fromEntries(templateResources.map((x) => [x.id, x.name ?? x.id])),
    [templateResources],
  );
  const chatContextNameMap = useMemo(
    () => Object.fromEntries(chatContextResources.map((x) => [x.id, x.name ?? x.id])),
    [chatContextResources],
  );
  const chatContextResourceMap = useMemo(
    () => Object.fromEntries(chatContextResources.map((x) => [x.id, x])),
    [chatContextResources],
  );
  const {
    currentData: history,
    isFetching: isHistoryFetching,
    isSuccess: isHistorySuccess,
    isError: isHistoryError,
    error: historyError,
  } = useGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery(
    { sessionId: chatSessionId || "", textLimit: HISTORY_TEXT_LIMIT, textOffset: 0 },
    {
      skip: !chatSessionId,
      // Make the UI stateless/robust: always refresh when switching sessions (even if cached).
      refetchOnMountOrArgChange: true,
      refetchOnReconnect: false,
      refetchOnFocus: false,
    },
  );

  // Keep a ref to the latest chatSessionId so the (long-lived) WebSocket handlers don't capture a stale one.
  const activeSessionIdRef = useRef<string | undefined>(chatSessionId);
  useEffect(() => {
    activeSessionIdRef.current = chatSessionId;
  }, [chatSessionId]);

  // Clear messages when switching sessions (but not on draft→session to avoid blink when a new session is created from draft)
  useSessionChange(chatSessionId, {
    onSessionToDraft: () => {
      messagesRef.current = [];
      setAllMessages([]);
    },
    onSessionSwitch: () => {
      messagesRef.current = [];
      setAllMessages([]);
    },
  });

  const loadSeqRef = useRef<number>(0);
  const lastReadySeqRef = useRef<number>(0);
  const [loadState, setLoadState] = useState<{
    seq: number;
    chatSessionId?: string;
    startedAt: number;
    historyReady: boolean;
    prefsReady: boolean;
  }>(() => ({
    seq: 0,
    chatSessionId: undefined,
    startedAt: 0,
    historyReady: true,
    prefsReady: true,
  }));

  useEffect(() => {
    if (!chatSessionId) {
      setLoadState((prev) => ({
        seq: prev.seq,
        chatSessionId: undefined,
        startedAt: 0,
        historyReady: true,
        prefsReady: true,
      }));
      return;
    }

    const nextSeq = loadSeqRef.current + 1;
    loadSeqRef.current = nextSeq;
    const startedAt = Date.now();
    setLoadState({
      seq: nextSeq,
      chatSessionId,
      startedAt,
      historyReady: false,
      prefsReady: false,
    });
    console.info("[CHATBOT][LOAD] start", { seq: nextSeq, chatSessionId });
    console.info("[CHATBOT][UI] widgets reset", {
      seq: nextSeq,
      chatSessionId,
      chatContext: false,
      libraries: false,
      attachments: false,
      search: false,
      knowledge: false,
    });
  }, [chatSessionId]);

  // Load history when available (RTK Query handles fetching)
  useEffect(() => {
    if (history && chatSessionId) {
      const merged = mergeAuthoritative(messagesRef.current, history);
      messagesRef.current = merged;
      setAllMessages(merged);
    }
  }, [history, chatSessionId]);

  useEffect(() => {
    if (!chatSessionId || loadState.chatSessionId !== chatSessionId || loadState.historyReady) return;
    if (isHistoryFetching) return;
    if (!isHistorySuccess && !isHistoryError) return;
    setLoadState((prev) => {
      if (prev.chatSessionId !== chatSessionId || prev.historyReady) return prev;
      const elapsedMs = prev.startedAt ? Date.now() - prev.startedAt : 0;
      const messageCount = Array.isArray(history) ? history.length : 0;
      console.info("[CHATBOT][LOAD] history done", {
        seq: prev.seq,
        chatSessionId,
        messageCount,
        elapsedMs,
        status: isHistoryError ? "error" : "ok",
      });
      if (isHistoryError && historyError) {
        console.error("[CHATBOT][LOAD] history error", { seq: prev.seq, chatSessionId, error: historyError });
      }
      return { ...prev, historyReady: true };
    });
  }, [
    chatSessionId,
    loadState.chatSessionId,
    loadState.historyReady,
    isHistoryFetching,
    isHistorySuccess,
    isHistoryError,
    history,
    historyError,
  ]);

  const [uploadChatFile] = useUploadFileAgenticV1ChatbotUploadPostMutation();
  const [createSession] = useCreateSessionAgenticV1ChatbotSessionPostMutation();
  // Local tick to signal attachments list to refresh after successful uploads
  const [attachmentsRefreshTick, setAttachmentsRefreshTick] = useState<number>(0);
  const [isUploadingAttachments, setIsUploadingAttachments] = useState(false);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesRef = useRef<ChatMessage[]>([]);

  // keep state + ref in sync
  const setAllMessages = (msgs: ChatMessage[]) => {
    messagesRef.current = msgs;
    setMessages(msgs);
  };

  const [waitResponse, setWaitResponse] = useState<boolean>(false);
  const waitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const waitStartedAtRef = useRef<number>(0);
  const waitSeqRef = useRef<number>(0);
  const debugLoader = false;

  // --- Session preferences are handled by ConversationOptionsController ---
  const effectiveSessionId = pendingSessionIdRef.current || chatSessionId || undefined;
  const { data: sessions = [], refetch: refetchSessions } = useGetSessionsAgenticV1ChatbotSessionsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: false,
    refetchOnReconnect: false,
  });
  const attachmentSessionId = effectiveSessionId;
  useEffect(() => {
    if (attachmentSessionId) {
      refetchSessions();
    }
  }, [attachmentsRefreshTick, attachmentSessionId, refetchSessions]);
  const sessionAttachments = useMemo(() => {
    if (!attachmentSessionId) return [];
    const s = (sessions as any[]).find((x) => x?.id === attachmentSessionId) as any | undefined;
    const att = s?.attachments;
    if (Array.isArray(att)) return att as { id: string; name: string }[];
    const names = (s && (s.file_names as string[] | undefined)) || [];
    return Array.isArray(names) ? names.map((n) => ({ id: n, name: n })) : [];
  }, [sessions, attachmentSessionId]);
  const options = useConversationOptionsController({
    chatSessionId,
    prefsTargetSessionId: effectiveSessionId,
    agents,
  });
  const {
    conversationPrefs,
    currentAgent,
    supportsRagScopeSelection,
    supportsDeepSearchSelection,
    isHydratingSession,
    prefsLoadState,
    sessionPrefs,
    isPrefsFetching,
    isPrefsError,
    prefsError,
    layout,
  } = options.state;
  const { selectAgent, setSearchPolicy, setSearchRagScope, setDeepSearchEnabled, seedSessionPrefs } = options.actions;

  const beginWaiting = () => {
    waitSeqRef.current += 1;
    waitStartedAtRef.current = typeof performance !== "undefined" ? performance.now() : Date.now();
    if (waitTimerRef.current) {
      clearTimeout(waitTimerRef.current);
      waitTimerRef.current = null;
    }
    if (debugLoader) console.debug("[loader] begin", { seq: waitSeqRef.current });
    setWaitResponse(true);
  };

  const endWaiting = ({ immediate = false }: { immediate?: boolean } = {}) => {
    const seq = waitSeqRef.current;
    const MIN_MS = 200;

    if (waitTimerRef.current) {
      clearTimeout(waitTimerRef.current);
      waitTimerRef.current = null;
    }

    const finish = () => {
      if (seq === waitSeqRef.current) setWaitResponse(false);
    };

    if (immediate) {
      finish();
      return;
    }

    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    const elapsed = now - waitStartedAtRef.current;
    const remaining = MIN_MS - elapsed;
    if (remaining > 0) {
      if (debugLoader) console.debug("[loader] end (delayed)", { seq, remainingMs: Math.ceil(remaining) });
      waitTimerRef.current = setTimeout(finish, remaining);
    } else {
      if (debugLoader) console.debug("[loader] end", { seq, immediate });
      finish();
    }
  };

  const stopStreaming = () => {
    const socket = webSocketRef.current;
    if (!socket) {
      endWaiting({ immediate: true });
      return;
    }

    try {
      if (
        socket.readyState === WebSocket.OPEN ||
        socket.readyState === WebSocket.CONNECTING ||
        socket.readyState === WebSocket.CLOSING
      ) {
        socket.close(4000, "client_stop");
      }
    } catch (err) {
      console.error("[❌ ChatBot] Failed to close WebSocket on stop:", err);
    } finally {
      webSocketRef.current = null;
      wsTokenRef.current = null;
      endWaiting({ immediate: true });
    }
  };

  // Clear pending session once parent propagated the real session
  useEffect(() => {
    if (chatSessionId && pendingSessionIdRef.current === chatSessionId) {
      pendingSessionIdRef.current = null;
    }
  }, [chatSessionId]);

  const setupWebSocket = async (): Promise<WebSocket | null> => {
    const current = webSocketRef.current;
    if (current && current.readyState === WebSocket.OPEN) return current;
    if (current && (current.readyState === WebSocket.CLOSING || current.readyState === WebSocket.CLOSED)) {
      console.warn("[🔄 ChatBot] WebSocket was closed or closing. Resetting...");
      webSocketRef.current = null;
    }
    console.debug("[📩 ChatBot] initiate new connection:");

    // ✅ Pourquoi: on authentifie la *connexion* WS une fois pour toutes,
    //    exactement comme les autres endpoints HTTP (JWT). Le backend va décoder
    //    ce token au handshake et ignorer tout user_id client.
    await KeyCloakService.ensureFreshToken(30);
    const token = KeyCloakService.GetToken();
    const connectSeq = ++wsConnectSeqRef.current;

    return new Promise((resolve, reject) => {
      const rawWsUrl = toWsUrl(getConfig().backend_url_api, "/agentic/v1/chatbot/query/ws");
      const url = new URL(rawWsUrl);
      if (token) url.searchParams.set("token", token); // ⚠️ nécessite WSS en prod + logs sans query

      const socket = new WebSocket(url.toString());
      wsTokenRef.current = token || null; // mémo pour détection simple de changement

      socket.onopen = () => {
        if (connectSeq !== wsConnectSeqRef.current) {
          try {
            socket.close(4001, "stale_ws_connection");
          } catch {}
          return;
        }
        console.log("[CHATBOT] WebSocket connected");
        webSocketRef.current = socket;
        resolve(socket);
      };
      socket.onmessage = (event) => {
        if (connectSeq !== wsConnectSeqRef.current) return;
        try {
          const response = JSON.parse(event.data);

          switch (response.type) {
            case "stream": {
              const streamed = response as StreamEvent;
              const msg = streamed.message as ChatMessage;

              // Ignore streams for another session than the one being viewed
              const activeSessionId = activeSessionIdRef.current;
              if (activeSessionId && msg.session_id !== activeSessionId) {
                console.warn("Ignoring stream for another session:", msg.session_id);
                break;
              }

              // Upsert streamed message and keep order stable
              messagesRef.current = upsertOne(messagesRef.current, msg);
              setMessages(messagesRef.current);
              // Defensive: ensure loader is visible while we are streaming a response.
              beginWaiting();
              // ⛔ no scrolling logic here — the layout effect handles it post-render
              break;
            }

            case "final": {
              const finalEvent = response as FinalEvent;

              // Ignore finals for another session than the one being viewed
              const activeSessionId = activeSessionIdRef.current;
              if (activeSessionId && finalEvent.session?.id && finalEvent.session.id !== activeSessionId) {
                console.warn("Ignoring final for another session:", finalEvent.session.id);
                break;
              }

              // Optional debug summary
              const streamedKeys = new Set(messagesRef.current.map((m) => keyOf(m)));
              const finalKeys = new Set(finalEvent.messages.map((m) => keyOf(m)));
              const missing = [...finalKeys].filter((k) => !streamedKeys.has(k));
              const unexpected = [...streamedKeys].filter((k) => !finalKeys.has(k));
              console.debug("[CHATBOT] Final event summary", { missing, unexpected });

              // Merge authoritative finals (includes citations/metadata)
              messagesRef.current = mergeAuthoritative(messagesRef.current, finalEvent.messages);
              setMessages(messagesRef.current);
              endWaiting();
              break;
            }

            case "error": {
              showError({ summary: "Error", detail: response.content });
              console.error("[RCV ERROR ChatBot] WebSocket error:", response);
              endWaiting({ immediate: true });
              break;
            }

            default: {
              console.warn("[⚠️ ChatBot] Unknown message type:", response.type);
              showError({
                summary: "Unknown Message",
                detail: `Received unknown message type: ${response.type}`,
              });
              endWaiting({ immediate: true });
              break;
            }
          }
        } catch (err) {
          console.error("[❌ ChatBot] Failed to parse message:", err);
          showError({ summary: "Parsing Error", detail: "Assistant response could not be processed." });
          endWaiting({ immediate: true });
          socket.close(); // Close only if the payload is unreadable
        }
      };

      socket.onerror = (err) => {
        if (connectSeq !== wsConnectSeqRef.current) return;
        console.error("[❌ ChatBot] WebSocket error:", err);
        showError({ summary: "Connection Error", detail: "Chat connection failed." });
        endWaiting({ immediate: true });
        reject(err);
      };

      socket.onclose = () => {
        if (connectSeq !== wsConnectSeqRef.current) return;
        console.warn("[❌ ChatBot] WebSocket closed");
        webSocketRef.current = null;
        wsTokenRef.current = null;
        endWaiting();
      };
    });
  };

  // Set up the WebSocket connection when the component mounts
  useEffect(() => {
    setupWebSocket();

    return () => {
      // Invalidate any in-flight WS connection attempt / handlers
      wsConnectSeqRef.current += 1;

      // Clear loader timer
      if (waitTimerRef.current) {
        clearTimeout(waitTimerRef.current);
        waitTimerRef.current = null;
      }

      // Close WS regardless of state (OPEN / CONNECTING / CLOSING)
      const socket = webSocketRef.current;
      webSocketRef.current = null;
      wsTokenRef.current = null;

      if (!socket) return;

      try {
        if (
          socket.readyState === WebSocket.OPEN ||
          socket.readyState === WebSocket.CONNECTING ||
          socket.readyState === WebSocket.CLOSING
        ) {
          console.log("[ChatBot] Closing websocket on component unmount");
          socket.close(4000, "component_unmount");
        }
      } catch (err) {
        console.warn("[ChatBot] Failed to close WebSocket on unmount", err);
      }
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // mount/unmount

  useEffect(() => {
    if (!chatSessionId || loadState.chatSessionId !== chatSessionId || loadState.prefsReady) return;
    if (isPrefsFetching) return;
    const isPrefsHydrated = prefsLoadState === "hydrated";
    if (!isPrefsHydrated && !isPrefsError) return;
    setLoadState((prev) => {
      if (prev.chatSessionId !== chatSessionId || prev.prefsReady) return prev;
      const elapsedMs = prev.startedAt ? Date.now() - prev.startedAt : 0;
      const agentName = sessionPrefs?.agent_name;
      console.info("[CHATBOT][LOAD] prefs done", {
        seq: prev.seq,
        chatSessionId,
        agent: agentName ?? null,
        elapsedMs,
        status: isPrefsError ? "error" : "ok",
        prefsLoadState,
      });
      if (isPrefsError && prefsError) {
        console.error("[CHATBOT][LOAD] prefs error", { seq: prev.seq, chatSessionId, error: prefsError });
      }
      return { ...prev, prefsReady: true };
    });
  }, [
    chatSessionId,
    loadState.chatSessionId,
    loadState.prefsReady,
    isPrefsFetching,
    isPrefsError,
    prefsLoadState,
    sessionPrefs,
    prefsError,
  ]);

  useEffect(() => {
    if (!chatSessionId || loadState.chatSessionId !== chatSessionId) return;
    if (!loadState.historyReady || !loadState.prefsReady) return;
    if (lastReadySeqRef.current === loadState.seq) return;
    lastReadySeqRef.current = loadState.seq;
    const elapsedMs = loadState.startedAt ? Date.now() - loadState.startedAt : 0;
    console.info("[CHATBOT][LOAD] ready", {
      seq: loadState.seq,
      chatSessionId,
      elapsedMs,
      agent: currentAgent?.name ?? null,
      messageCount: messagesRef.current.length,
    });
  }, [
    chatSessionId,
    loadState.chatSessionId,
    loadState.historyReady,
    loadState.prefsReady,
    loadState.seq,
    loadState.startedAt,
    currentAgent?.name,
  ]);

  // Handle user input (text/audio)
  const handleSend = async (content: UserInputContent) => {
    // Init runtime context
    const runtimeContext: RuntimeContext = { ...(baseRuntimeContext ?? {}) };

    // Add selected chat contexts
    if (conversationPrefs.chatContextIds.length) {
      runtimeContext.selected_chat_context_ids = conversationPrefs.chatContextIds;
    }

    // Add selected libraries / profiles (CANONIQUES — pas de doublon)
    if (conversationPrefs.documentLibraryIds.length) {
      runtimeContext.selected_document_libraries_ids = conversationPrefs.documentLibraryIds;
    }

    // Policy
    runtimeContext.search_policy = conversationPrefs.searchPolicy || "semantic";
    if (supportsRagScopeSelection && conversationPrefs.searchRagScope) {
      runtimeContext.search_rag_scope = conversationPrefs.searchRagScope;
    }
    if (supportsDeepSearchSelection && typeof conversationPrefs.deepSearch === "boolean") {
      runtimeContext.deep_search = conversationPrefs.deepSearch;
    }

    // Files are now uploaded immediately upon selection (not here)

    if (content.text) {
      queryChatBot(content.text.trim(), undefined, runtimeContext);
      // } else if (content.audio) {
      //   setWaitResponse(true);
      //   const audioFile: File = new File([content.audio], "audio.mp3", { type: content.audio.type });
      //   postTranscribeAudio({ file: audioFile }).then((response) => {
      //     if (response.data) {
      //       const message: TranscriptionResponse = response.data as TranscriptionResponse;
      //       if (message.text) {
      //         queryChatBot(message.text, undefined, runtimeContext);
      //       }
      //     }
      //   });
    } else {
      console.warn("No content to send.");
    }
  };

  const ensureSessionId = useCallback(async (): Promise<string> => {
    const existing = pendingSessionIdRef.current || chatSessionId;
    if (existing) return existing;
    try {
      const session = await createSession({
        createSessionPayload: { agent_name: currentAgent?.name },
      }).unwrap();
      try {
        await seedSessionPrefs(session.id, currentAgent?.name);
      } catch (prefErr) {
        console.warn("[CHATBOT] Failed to seed session prefs on create", prefErr);
      }
      pendingSessionIdRef.current = session.id;
      onNewSessionCreated(session.id);
      return session.id;
    } catch (err: any) {
      const detail = err?.data?.detail ?? err?.data ?? err?.error;
      const errMsg =
        typeof detail === "string"
          ? detail
          : typeof detail === "object" && detail
            ? detail.message || detail.upstream || detail.code || JSON.stringify(detail)
            : (err as Error)?.message || "Unknown error";
      showError({ summary: "Session creation failed", detail: errMsg });
      throw err;
    }
  }, [createSession, currentAgent?.name, chatSessionId, showError, onNewSessionCreated, seedSessionPrefs]);

  const handleAddAttachments = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      setIsUploadingAttachments(true);
      let sid = pendingSessionIdRef.current || chatSessionId;
      if (!sid) {
        try {
          sid = await ensureSessionId();
        } catch {
          setIsUploadingAttachments(false);
          return;
        }
      }

      try {
        for (const file of files) {
          const formData = new FormData();
          formData.append("session_id", sid);
          formData.append("file", file);
          try {
            await uploadChatFile({
              bodyUploadFileAgenticV1ChatbotUploadPost: formData as any,
            }).unwrap();
          } catch (err: any) {
            const detail = err?.data?.detail ?? err?.data ?? err?.error;
            const errMsg =
              typeof detail === "string"
                ? detail
                : typeof detail === "object" && detail
                  ? detail.message || detail.upstream || detail.code || JSON.stringify(detail)
                  : (err as Error)?.message || "Unknown error";
            showError({ summary: "Upload failed", detail: errMsg });
          } finally {
            // no-op
          }
        }
      } finally {
        setIsUploadingAttachments(false);
      }

      setAttachmentsRefreshTick((tick) => tick + 1);
    },
    [ensureSessionId, chatSessionId, showError, uploadChatFile],
  );

  const handleAttachmentsUpdated = useCallback(() => {
    setAttachmentsRefreshTick((tick) => tick + 1);
  }, []);

  // Upload files immediately when user selects them (sequential to preserve session binding)

  /**
   * Send a new user message to the chatbot agent.
   * Backend is authoritative; we still add a brief optimistic bubble for UX.
   * The server stream replaces it using the same exchange_id.
   */
  const queryChatBot = async (input: string, agent?: AnyAgent, runtimeContext?: RuntimeContext) => {
    console.debug(`[CHATBOT] Sending message: ${input}`);
    let sid = pendingSessionIdRef.current || chatSessionId;
    if (!sid) {
      try {
        sid = await ensureSessionId();
      } catch {
        return;
      }
    }
    const exchangeId = uuidv4();
    const optimisticMessage: ChatMessage = {
      session_id: sid,
      exchange_id: exchangeId,
      rank: messagesRef.current.length,
      timestamp: new Date().toISOString(),
      role: "user",
      channel: "final",
      parts: [{ type: "text", text: input }],
      metadata: {
        agent_name: agent ? agent.name : currentAgent.name,
        runtime_context: runtimeContext ?? null,
      },
    };
    const optimisticKey = keyOf(optimisticMessage);
    messagesRef.current = upsertOne(messagesRef.current, optimisticMessage);
    setMessages(messagesRef.current);
    // Show loader immediately (even while WS is connecting).
    beginWaiting();
    // Get tokens for backend use. This proacively allows the backend to perform
    // user-authenticated operations (e.g., vector search) on behalf of the user.
    // The backend is then responsible for refreshing tokens as needed. Which will rarely be needed
    // because tokens are refreshed often on the frontend.
    const refreshToken = KeyCloakService.GetRefreshToken();
    const accessToken = KeyCloakService.GetToken();
    const eventBase: ChatAskInput = {
      message: input,
      agent_name: agent ? agent.name : currentAgent.name,
      // Use the already-resolved sid (may come from ensureSessionId()) to avoid any drift
      // between the check above and the payload build here.
      session_id: sid,
      runtime_context: runtimeContext,
      access_token: accessToken || undefined, // Now the backend can read the active token
      refresh_token: refreshToken || undefined, // Now the backend can save and use the refresh token
    };

    const event = {
      ...eventBase,
      client_exchange_id: exchangeId,
    } as ChatAskInput;

    try {
      const socket = await setupWebSocket();

      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(event));
        console.debug("[CHATBOT] Sent message:", event);
      } else {
        throw new Error("WebSocket not open");
      }
    } catch (err) {
      console.error("[CHATBOT] Failed to send message:", err);
      showError({ summary: "Connection Error", detail: "Could not send your message — connection failed." });
      messagesRef.current = messagesRef.current.filter((m) => keyOf(m) !== optimisticKey);
      setMessages(messagesRef.current);
      endWaiting({ immediate: true });
    }
  };

  const loadError = (isHistoryError && historyError) || (isPrefsError && prefsError);
  const hasLoadError = Boolean(loadError);
  const isSessionLoadBlocked =
    Boolean(chatSessionId) &&
    (loadState.chatSessionId !== chatSessionId ||
      !loadState.historyReady ||
      !loadState.prefsReady ||
      Boolean(loadError));
  const showWelcome = isNewConversation && !isSessionLoadBlocked && !waitResponse && messages.length === 0;
  // Helps spot session-history fetch issues quickly in dev without adding noisy logs.
  const showHistoryLoading = !!chatSessionId && isHistoryFetching && messages.length === 0 && !waitResponse;
  return (
    <ChatBotView
      chatSessionId={chatSessionId}
      options={options}
      attachmentSessionId={attachmentSessionId}
      sessionAttachments={sessionAttachments}
      onAddAttachments={handleAddAttachments}
      onAttachmentsUpdated={handleAttachmentsUpdated}
      isUploadingAttachments={isUploadingAttachments}
      libraryNameMap={libraryNameMap}
      libraryById={libraryById}
      promptNameMap={promptNameMap}
      templateNameMap={templateNameMap}
      chatContextNameMap={chatContextNameMap}
      chatContextResourceMap={chatContextResourceMap}
      isSessionLoadBlocked={isSessionLoadBlocked}
      loadError={hasLoadError}
      showWelcome={showWelcome}
      showHistoryLoading={showHistoryLoading}
      waitResponse={waitResponse}
      isHydratingSession={isHydratingSession}
      conversationPrefs={conversationPrefs}
      currentAgent={currentAgent}
      agents={agents}
      messages={messages}
      layout={layout}
      onSend={handleSend}
      onStop={stopStreaming}
      onSelectAgent={selectAgent}
      setSearchPolicy={setSearchPolicy}
      setSearchRagScope={setSearchRagScope}
      setDeepSearchEnabled={setDeepSearchEnabled}
    />
  );
};

export default ChatBot;
