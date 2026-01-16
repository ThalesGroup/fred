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
 * - Uses `useInitialChatInputContext` to supply draft (pre-session) defaults to the input area.
 * - Delegates per-session preference hydration/persistence to `UserInput`.
 * - Avoids flicker on session switch by keeping messages while history loads; welcome shows only when truly empty.
 */

import TravelExploreOutlinedIcon from "@mui/icons-material/TravelExploreOutlined";
import { Box, CircularProgress, Grid2, IconButton, Tooltip, Typography, useTheme } from "@mui/material";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { v4 as uuidv4 } from "uuid";
import { AnyAgent } from "../../common/agent.ts";
import { getConfig } from "../../common/config.tsx";
import { useInitialChatInputContext } from "../../hooks/useInitialChatInputContext.ts";
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
  useGetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetQuery,
  useUpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutMutation,
  useUploadFileAgenticV1ChatbotUploadPostMutation,
} from "../../slices/agentic/agenticOpenApi.ts";
import {
  TagType,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider.tsx";
import { AttachmentsButton } from "./AttachmentsButton.tsx";
import { keyOf, mergeAuthoritative, toWsUrl, upsertOne } from "./ChatBotUtils.tsx";
import ChatKnowledge from "./ChatKnowledge.tsx";
import { FeatureTooltip } from "./FeatureTooltip.tsx";
import { MessagesArea } from "./MessagesArea.tsx";
import { ChatContextPickerPanel } from "./settings/ChatContextPickerPanel.tsx";
import UserInput, { UserInputContent, UserInputHandle } from "./user_input/UserInput.tsx";

const HISTORY_TEXT_LIMIT = 1200;

export interface ChatBotError {
  session_id: string | null;
  content: string;
}

// interface TranscriptionResponse {
//   text?: string;
// }

export interface ChatBotProps {
  sessionId?: string;
  agents: AnyAgent[];
  runtimeContext?: RuntimeContext;
  onNewSessionCreated: (sessionId: string) => void;
}

const ChatBot = ({ sessionId, agents, onNewSessionCreated, runtimeContext: baseRuntimeContext }: ChatBotProps) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const username =
    KeyCloakService.GetUserGivenName?.() ||
    KeyCloakService.GetUserFullName?.() ||
    KeyCloakService.GetUserName?.() ||
    "";
  const greetingText = username ? t("chatbot.welcomeUser", { username }) : t("chatbot.welcomeFallback");
  const [typedGreeting, setTypedGreeting] = useState<string>(greetingText);
  useEffect(() => {
    setTypedGreeting(greetingText);
  }, [greetingText]);

  const isNewConversation = !sessionId;

  const [contextOpen, setContextOpen] = useState<boolean>(() => {
    try {
      const uid = KeyCloakService.GetUserId?.() || "anon";
      return localStorage.getItem(`chatctx_open:${uid}`) === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      const uid = KeyCloakService.GetUserId?.() || "anon";
      localStorage.setItem(`chatctx_open:${uid}`, contextOpen ? "1" : "0");
    } catch {}
  }, [contextOpen]);

  const { showError } = useToast();
  const webSocketRef = useRef<WebSocket | null>(null);
  const wsTokenRef = useRef<string | null>(null);
  const wsConnectSeqRef = useRef<number>(0);
  // When backend creates a session during first file upload, keep it locally
  // so the immediate next message uses the same session id.
  const pendingSessionIdRef = useRef<string | null>(null);
  // Track files being uploaded right now to surface inline progress in the input bar
  const [uploadingFiles, setUploadingFiles] = useState<string[]>([]);
  const userInputRef = useRef<UserInputHandle | null>(null);

  // Name of des libs / prompts / templates / chat-context
  const { data: docLibs = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" as TagType });
  const { data: promptResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "prompt" });
  const { data: templateResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "template" });
  const { data: chatContextResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({
    kind: "chat-context",
  });

  const [selectedChatContextIds, setSelectedChatContextIds] = useState<string[]>([]);
  const setSelectedChatContextIdsFromHydration = useCallback((ids: string[]) => {
    setSelectedChatContextIds(ids);
  }, []);
  const setSelectedChatContextIdsFromUser = useCallback((ids: string[]) => {
    setSelectedChatContextIds(ids);
    userInputRef.current?.markSessionPrefsDirty();
  }, []);

  const libraryNameMap = useMemo(() => Object.fromEntries(docLibs.map((x) => [x.id, x.name])), [docLibs]);
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

  const {
    currentData: history,
    refetch: refetchHistory,
    isFetching: isHistoryFetching,
  } = useGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery(
    { sessionId: sessionId || "", textLimit: HISTORY_TEXT_LIMIT, textOffset: 0 },
    {
      skip: !sessionId,
      // Make the UI stateless/robust: always refresh when switching sessions (even if cached).
      refetchOnMountOrArgChange: true,
      refetchOnReconnect: true,
      refetchOnFocus: true,
    },
  );

  // Keep a ref to the latest sessionId so the (long-lived) WebSocket handlers don't capture a stale one.
  const activeSessionIdRef = useRef<string | undefined>(sessionId);
  useEffect(() => {
    activeSessionIdRef.current = sessionId;
    if (sessionId) {
      // Best-effort refresh when returning to a session; RTK Query dedupes in-flight requests.
      refetchHistory();
    }
  }, [sessionId, refetchHistory]);

  // Clear messages when switching sessions (but not on draft→session to avoid blink when a new session is created from draft)
  useSessionChange(sessionId, {
    onSessionToDraft: () => {
      messagesRef.current = [];
      setAllMessages([]);
    },
    onSessionSwitch: () => {
      messagesRef.current = [];
      setAllMessages([]);
    },
  });

  // Load history when available (RTK Query handles fetching)
  useEffect(() => {
    if (history && sessionId) {
      messagesRef.current = history;
      setAllMessages(history);
    }
  }, [history, sessionId]);

  const [uploadChatFile] = useUploadFileAgenticV1ChatbotUploadPostMutation();
  const [createSession] = useCreateSessionAgenticV1ChatbotSessionPostMutation();
  const [persistSessionPrefs] = useUpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutMutation();
  // Local tick to signal attachments list to refresh after successful uploads
  const [attachmentsRefreshTick, setAttachmentsRefreshTick] = useState<number>(0);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesRef = useRef<ChatMessage[]>([]);
  const seedPrefsRef = useRef<any>(null);
  const seedSessionIdRef = useRef<string | null>(null);

  // keep state + ref in sync
  const setAllMessages = (msgs: ChatMessage[]) => {
    messagesRef.current = msgs;
    setMessages(msgs);
  };

  const defaultAgent = useMemo(() => agents[0] ?? null, [agents]);
  const [currentAgent, setCurrentAgent] = useState<AnyAgent>(agents[0] ?? ({} as AnyAgent));
  useEffect(() => {
    if (defaultAgent && (!currentAgent || !currentAgent.name)) setCurrentAgent(defaultAgent);
  }, [currentAgent, defaultAgent]);

  const [attachmentsPanelOpen, setAttachmentsPanelOpen] = useState<boolean>(false);
  const [attachmentCount, setAttachmentCount] = useState<number>(0);
  const [deepSearchEnabled, setDeepSearchEnabled] = useState<boolean>(false);

  const [waitResponse, setWaitResponse] = useState<boolean>(false);
  const waitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const waitStartedAtRef = useRef<number>(0);
  const waitSeqRef = useRef<number>(0);
  const debugLoader = useMemo(() => {
    try {
      return localStorage.getItem("chat.debugLoader") === "1";
    } catch {
      return false;
    }
  }, []);

  // --- Session preferences (authoritative) ---
  const effectiveSessionId = pendingSessionIdRef.current || sessionId || undefined;
  const prefsSessionId = effectiveSessionId;
  const {
    data: sessionPrefs,
    refetch: refetchSessionPrefs,
  } = useGetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetQuery(
    { sessionId: prefsSessionId || "" },
    {
      skip: !prefsSessionId,
      refetchOnMountOrArgChange: true,
      refetchOnReconnect: true,
      refetchOnFocus: true,
    },
  );
  useEffect(() => {
    if (!prefsSessionId) return;
    const agentName = (sessionPrefs as any)?.agent_name;
    if (typeof agentName !== "string" || !agentName.length) return;
    const found = agents.find((a) => a.name === agentName) ?? defaultAgent;
    if (found && found.name !== currentAgent?.name) setCurrentAgent(found);
  }, [agents, currentAgent?.name, defaultAgent, prefsSessionId, sessionPrefs]);

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

  // === SINGLE scroll container ref (attach to the ONLY overflow element) ===
  const scrollerRef = useRef<HTMLDivElement>(null);

  // === Hard guarantee: snap to absolute bottom after render ===
  useLayoutEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, sessionId]);

  // Clear pending session once parent propagated the real session
  useEffect(() => {
    if (sessionId && pendingSessionIdRef.current === sessionId) {
      pendingSessionIdRef.current = null;
    }
  }, [sessionId]);

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
      if (waitTimerRef.current) {
        clearTimeout(waitTimerRef.current);
        waitTimerRef.current = null;
      }
      if (webSocketRef.current && webSocketRef.current.readyState === WebSocket.OPEN) {
        console.log("[ChatBot] Closing websocket on component unmount");
        webSocketRef.current.close();
      }
      webSocketRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // mount/unmount

  const [userInputContext, setUserInputContext] = useState<any>(null);
  const handleDraftContextChange = useCallback(
    (ctx: any) => {
      // Only track draft context when there is no active session.
      if (!sessionId) {
        setUserInputContext(ctx);
      }
    },
    [sessionId],
  );

  // Draft defaults (pre-session) are handled by a shared hook; once a session exists, per-session prefs come from UserInput.
  const { prefs: initialCtx, resetToDefaults } = useInitialChatInputContext(currentAgent?.name || "default", sessionId);

  const lastSessionIdRef = useRef<string | undefined>(undefined);
  const isDraft = !sessionId;
  const isFreshSessionFromDraft = !!sessionId && !lastSessionIdRef.current;
  const isSeededSession = !!sessionId && seedSessionIdRef.current === sessionId && seedPrefsRef.current;

  // Decide which baseline prefs to pass:
  // - Draft/welcome: use current draft selections if any, else stored defaults.
  // - Newly created session (from draft): seed with draft selections.
  // - Other sessions: use stored defaults; per-session prefs hydrate in UserInput.
  const basePrefs =
    isDraft || isFreshSessionFromDraft
      ? userInputContext || initialCtx
      : isSeededSession
        ? seedPrefsRef.current || initialCtx
        : initialCtx;

  const initialDocumentLibraryIds = isDraft
    ? (userInputContext?.documentLibraryIds ?? initialCtx.documentLibraryIds)
    : basePrefs.documentLibraryIds;
  const initialPromptResourceIds = isDraft
    ? (userInputContext?.promptResourceIds ?? initialCtx.promptResourceIds)
    : basePrefs.promptResourceIds;
  const initialTemplateResourceIds = isDraft
    ? (userInputContext?.templateResourceIds ?? initialCtx.templateResourceIds)
    : basePrefs.templateResourceIds;
  const initialSearchPolicy = isDraft
    ? (userInputContext?.searchPolicy ?? initialCtx.searchPolicy ?? "semantic")
    : (basePrefs.searchPolicy ?? "semantic");
  const initialSearchRagScope = isDraft
    ? (userInputContext?.searchRagScope ?? initialCtx.searchRagScope ?? undefined)
    : (basePrefs.searchRagScope ?? undefined);
  const initialDeepSearch = isDraft
    ? typeof userInputContext?.deepSearch === "boolean"
      ? userInputContext.deepSearch
      : initialCtx.deepSearch
    : basePrefs.deepSearch;

  // Track session transitions: seed prefs when creating a session from draft; reset draft on return to welcome; clear seed when switching.
  useSessionChange(sessionId, {
    onChange: (_, curr) => {
      // Update lastSessionIdRef for isFreshSessionFromDraft calculation
      lastSessionIdRef.current = curr;
    },
    onDraftToSession: (newSessionId) => {
      // Capture draft prefs to seed this new session, then clear draft context
      seedPrefsRef.current = userInputContext || initialCtx;
      seedSessionIdRef.current = newSessionId;
      setUserInputContext(null);
      // If we navigated from draft to an existing session (not created just now), avoid leaking draft selections.
      if (pendingSessionIdRef.current !== newSessionId) setSelectedChatContextIds([]);
    },
    onSessionToDraft: () => {
      // Returning to welcome: reset draft prefs and agent to deterministic default
      resetToDefaults();
      seedPrefsRef.current = null;
      seedSessionIdRef.current = null;
      setUserInputContext(null);
      setSelectedChatContextIds([]);
    },
    onSessionSwitch: () => {
      // Switching between existing sessions: clear transient draft/seed context to avoid bleed
      seedPrefsRef.current = null;
      seedSessionIdRef.current = null;
      setUserInputContext(null);
      setSelectedChatContextIds([]);
    },
  });

  // Handle user input (text/audio)
  const handleSend = async (content: UserInputContent) => {
    // Init runtime context
    const runtimeContext: RuntimeContext = { ...(baseRuntimeContext ?? {}) };

    // Add selected chat contexts
    if (selectedChatContextIds.length) {
      runtimeContext.selected_chat_context_ids = selectedChatContextIds;
    }

    // Add selected libraries / profiles (CANONIQUES — pas de doublon)
    if (content.documentLibraryIds?.length) {
      runtimeContext.selected_document_libraries_ids = content.documentLibraryIds;
    }

    // Policy
    runtimeContext.search_policy = content.searchPolicy || "semantic";
    if (content.searchRagScope) {
      runtimeContext.search_rag_scope = content.searchRagScope;
    }
    if (typeof content.deepSearch === "boolean") {
      runtimeContext.deep_search = content.deepSearch;
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
    const existing = pendingSessionIdRef.current || sessionId;
    if (existing) return existing;
    try {
      const session = await createSession({
        createSessionPayload: { agent_name: currentAgent?.name },
      }).unwrap();
      // Seed backend preferences with current draft context so selections are preserved.
      const prefPayload: Record<string, any> = {
        chatContextIds: selectedChatContextIds,
        documentLibraryIds: basePrefs?.documentLibraryIds ?? [],
        promptResourceIds: basePrefs?.promptResourceIds ?? [],
        templateResourceIds: basePrefs?.templateResourceIds ?? [],
        searchPolicy: basePrefs?.searchPolicy ?? "semantic",
        searchRagScope: basePrefs?.searchRagScope,
        deepSearch: typeof basePrefs?.deepSearch === "boolean" ? basePrefs.deepSearch : undefined,
        agent_name: currentAgent?.name,
      };
      try {
        await persistSessionPrefs({
          sessionId: session.id,
          sessionPreferencesPayload: { preferences: prefPayload },
        }).unwrap();
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
  }, [
    basePrefs?.deepSearch,
    basePrefs?.documentLibraryIds,
    basePrefs?.promptResourceIds,
    basePrefs?.searchPolicy,
    basePrefs?.searchRagScope,
    basePrefs?.templateResourceIds,
    createSession,
    currentAgent?.name,
    selectedChatContextIds,
    sessionId,
    persistSessionPrefs,
    showError,
    onNewSessionCreated,
  ]);

  // Upload files immediately when user selects them (sequential to preserve session binding)
  const handleFilesSelected = async (files: File[]) => {
    if (!files?.length) return;
    const agentName = currentAgent.name;
    let baseSessionId = pendingSessionIdRef.current || sessionId;

    if (!baseSessionId) {
      try {
        baseSessionId = await ensureSessionId();
      } catch {
        return;
      }
    }

    for (const file of files) {
      setUploadingFiles((prev) => [...prev, file.name]);
      const formData = new FormData();
      const effectiveSessionId = pendingSessionIdRef.current || baseSessionId || "";
      formData.append("session_id", effectiveSessionId);
      formData.append("agent_name", agentName);
      formData.append("file", file);

      try {
        await uploadChatFile({
          bodyUploadFileAgenticV1ChatbotUploadPost: formData as any,
        }).unwrap();
        console.log("✅ Uploaded file:", file.name);
        // Refresh attachments view in the popover
        setAttachmentsRefreshTick((x) => x + 1);
      } catch (err: any) {
        const detail = err?.data?.detail ?? err?.data ?? err?.error;
        const errMsg =
          typeof detail === "string"
            ? detail
            : typeof detail === "object" && detail
              ? detail.message || detail.upstream || detail.code || JSON.stringify(detail)
              : (err as Error)?.message || "Unknown error";
        console.error("[CHATBOT] File upload failed:", err);
        showError({ summary: "File Upload Error", detail: `Failed to upload ${file.name}: ${errMsg}` });
      } finally {
        setUploadingFiles((prev) => prev.filter((n) => n !== file.name));
      }
    }
  };

  /**
   * Send a new user message to the chatbot agent.
   * Backend is authoritative: we DO NOT add an optimistic user bubble.
   * The server streams the authoritative user message first.
   */
  const queryChatBot = async (input: string, agent?: AnyAgent, runtimeContext?: RuntimeContext) => {
    console.debug(`[CHATBOT] Sending message: ${input}`);
    let sid = pendingSessionIdRef.current || sessionId;
    if (!sid) {
      try {
        sid = await ensureSessionId();
      } catch {
        return;
      }
    }
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
      client_exchange_id: uuidv4(),
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
      endWaiting({ immediate: true });
    }
  };

  const outputTokenCounts: number =
    messages && messages.length
      ? messages.reduce((sum, msg) => sum + (msg.metadata?.token_usage?.output_tokens || 0), 0)
      : 0;

  const inputTokenCounts: number =
    messages && messages.length
      ? messages.reduce((sum, msg) => sum + (msg.metadata?.token_usage?.input_tokens || 0), 0)
      : 0;
  const showWelcome = isNewConversation && !waitResponse && messages.length === 0;
  // Helps spot session-history fetch issues quickly in dev without adding noisy logs.
  const showHistoryLoading = !!sessionId && isHistoryFetching && messages.length === 0 && !waitResponse;
  const isSessionPrefsReady = !effectiveSessionId || !!sessionPrefs;

  const hasContext =
    !!userInputContext &&
    ((userInputContext?.files?.length ?? 0) > 0 ||
      !!userInputContext?.audioBlob ||
      (userInputContext?.documentLibraryIds?.length ?? 0) > 0 ||
      (userInputContext?.promptResourceIds?.length ?? 0) > 0 ||
      (userInputContext?.templateResourceIds?.length ?? 0) > 0);
  const agentSupportsAttachments = currentAgent?.chat_options?.attach_files === true;
  const effectiveAttachmentsPanelOpen = agentSupportsAttachments ? attachmentsPanelOpen : false;
  const showSetupButton = Boolean(
    currentAgent?.chat_options?.libraries_selection ||
      currentAgent?.chat_options?.search_policy_selection ||
      currentAgent?.chat_options?.record_audio_files,
  );
  const librariesCount = useMemo(() => {
    if (effectiveSessionId) {
      const ids = (sessionPrefs as any)?.documentLibraryIds;
      return Array.isArray(ids) ? ids.length : 0;
    }
    const draftIds = basePrefs?.documentLibraryIds;
    return Array.isArray(draftIds) ? draftIds.length : 0;
  }, [basePrefs?.documentLibraryIds, effectiveSessionId, sessionPrefs]);

  useEffect(() => {
    if (!showWelcome) return;
    setTypedGreeting(greetingText);
  }, [greetingText, showWelcome]);

  return (
    <Box width={"100%"} height="100%" display="flex" flexDirection="column" alignItems="center" sx={{ minHeight: 0 }}>
      {/* ===== Conversation header status =====
           Fred rationale:
           - Always show the conversation context so developers/users immediately
             understand if they're in a persisted session or a draft.
           - Avoid guesswork (messages length, etc.). Keep UX deterministic. */}

      {/* Chat context picker panel */}
      {/* (moved) Chat context is now in the top-right vertical toolbar */}

      {/* Conversation top-right controls (attachments + setup) */}
      <AttachmentsButton
        attachmentsPanelOpen={effectiveAttachmentsPanelOpen}
        attachmentCount={agentSupportsAttachments ? attachmentCount : 0}
        onToggle={() => setAttachmentsPanelOpen((v) => !v)}
        showAttachmentsButton
        attachmentsEnabled={isSessionPrefsReady && agentSupportsAttachments}
        showSetupButton
        setupEnabled={isSessionPrefsReady && showSetupButton}
        setupCount={librariesCount}
        onOpenSetup={(anchorEl) => {
          userInputRef.current?.openSetupPopover(anchorEl);
        }}
        topSlot={
          <>
            <ChatContextPickerPanel
              variant="icon"
              selectedChatContextIds={selectedChatContextIds}
              onChangeSelectedChatContextIds={setSelectedChatContextIdsFromUser}
            />
              <FeatureTooltip
                label={t("chatbot.deepSearch.label", "Deep Search")}
                description={t(
                "chatbot.deepSearch.tooltipDescription",
                "Delegates retrieval to a specialized agent for deeper search across your knowledge.\nAdds `deep_search` to the runtime context; may be slower but more thorough.",
              )}
              disabledReason={
                currentAgent?.chat_options?.deep_search_delegate === true
                  ? undefined
                  : t(
                      "chatbot.deepSearch.tooltipDisabled",
                      "This agent does not support deep search delegation.",
                    )
              }
            >
              <span>
                <IconButton
                  size="small"
                  aria-label="deep-search"
                  onClick={() => userInputRef.current?.setDeepSearchEnabled(!deepSearchEnabled)}
                  disabled={
                    waitResponse || !isSessionPrefsReady || currentAgent?.chat_options?.deep_search_delegate !== true
                  }
                  sx={{
                    border: `1px solid ${theme.palette.divider}`,
                    backgroundColor: deepSearchEnabled ? theme.palette.primary.main : theme.palette.background.paper,
                    color: deepSearchEnabled ? theme.palette.primary.contrastText : theme.palette.text.secondary,
                    opacity: currentAgent?.chat_options?.deep_search_delegate === true ? 1 : 0.45,
                    "&:hover": {
                      backgroundColor: deepSearchEnabled ? theme.palette.primary.dark : theme.palette.action.hover,
                    },
                  }}
                >
                  <TravelExploreOutlinedIcon fontSize="small" />
                </IconButton>
              </span>
            </FeatureTooltip>
          </>
        }
      />

      <Box
        height="100vh"
        width="100%"
        display="flex"
        flexDirection="column"
        paddingBottom={1}
        sx={{
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        {/*
          IMPORTANT: keep the scrollbar on the browser edge.
          - The scrollable container must be full-width (100%),
            while the conversation content stays centered (maxWidth).
        */}
        {showWelcome && (
          <Box
            width="80%"
            maxWidth={{ xs: "100%", md: "1200px", lg: "1400px", xl: "1750px" }}
            display="flex"
            flexDirection="column"
            alignItems="center"
              sx={{
                minHeight: 0,
                overflow: "hidden",
              pr: effectiveAttachmentsPanelOpen ? { xs: "min(92vw, 320px)", sm: "340px" } : 0,
              transition: (t) => t.transitions.create("padding-right"),
              mx: "auto",
            }}
          >
        {/* Conversation start: new conversation without message */}
          <Box
            sx={{
              minHeight: "100vh",
              width: "100%",
              px: { xs: 2, sm: 3 },
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: { xs: "flex-start", md: "center" },
              pt: { xs: 6, md: 8 },
              gap: 3,
            }}
          >
            <Box
              sx={{
                width: "100%",
                textAlign: "center",
              }}
            >
              <Typography
                variant="h3"
                sx={{
                  fontWeight: 700,
                  display: "inline-block",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  position: "relative",
                  background: theme.palette.primary.main,
                  backgroundSize: "200% 200%",
                  backgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  letterSpacing: 0.5,
                }}
              >
                {typedGreeting}
              </Typography>
            </Box>
            {/* Welcome hint */}
            <Typography variant="h5" color="text.primary" sx={{ textAlign: "center" }}>
              {t("chatbot.startNew", { name: currentAgent?.name ?? "assistant" })}
            </Typography>
            {/* Input area */}
            <Box sx={{ width: "min(900px, 100%)" }}>
              <UserInput
                ref={userInputRef}
                agentChatOptions={currentAgent.chat_options}
                isWaiting={waitResponse}
                onSend={handleSend}
                onStop={stopStreaming}
                onContextChange={handleDraftContextChange}
                sessionId={sessionId}
                effectiveSessionId={effectiveSessionId}
                uploadingFiles={uploadingFiles}
                onFilesSelected={agentSupportsAttachments ? handleFilesSelected : undefined}
                attachmentsRefreshTick={attachmentsRefreshTick}
                serverPrefs={sessionPrefs as any}
                refetchServerPrefs={refetchSessionPrefs}
                selectedChatContextIds={selectedChatContextIds}
                onSelectedChatContextIdsChange={setSelectedChatContextIdsFromHydration}
                initialDocumentLibraryIds={initialDocumentLibraryIds}
                initialPromptResourceIds={initialPromptResourceIds}
                initialTemplateResourceIds={initialTemplateResourceIds}
                initialSearchPolicy={initialSearchPolicy}
                initialSearchRagScope={initialSearchRagScope}
                initialDeepSearch={initialDeepSearch}
                currentAgent={currentAgent}
                agents={agents}
                onSelectNewAgent={setCurrentAgent}
                attachmentsPanelOpen={effectiveAttachmentsPanelOpen}
                onAttachmentsPanelOpenChange={agentSupportsAttachments ? setAttachmentsPanelOpen : undefined}
                onAttachmentCountChange={agentSupportsAttachments ? setAttachmentCount : undefined}
                onDeepSearchEnabledChange={(enabled) => setDeepSearchEnabled(enabled)}
              />
            </Box>
          </Box>
          </Box>
        )}

        {/* Ongoing conversation */}
        {!showWelcome && (
          <>
            {/* Chatbot messages area */}
            <Box
              ref={scrollerRef}
              sx={{
                flex: 1,
                minHeight: 0,
                width: "100%",
                overflowY: "auto",
                overflowX: "hidden",
                scrollbarWidth: "thin",
                "&::-webkit-scrollbar": {
                  width: "10px",
                },
                "&::-webkit-scrollbar-thumb": {
                  backgroundColor: theme.palette.divider,
                  borderRadius: "8px",
                },
                "&::-webkit-scrollbar-track": {
                  backgroundColor: "transparent",
                },
              }}
            >
              <Box
                sx={{
                  width: "80%",
                  maxWidth: { xs: "100%", md: "1200px", lg: "1400px", xl: "1750px" },
                  mx: "auto",
                  p: 2,
                  pr: effectiveAttachmentsPanelOpen ? { xs: "min(92vw, 320px)", sm: "340px" } : 0,
                  transition: (t) => t.transitions.create("padding-right"),
                  wordBreak: "break-word",
                  alignContent: "center",
                  minHeight: 0,
                }}
              >
                <MessagesArea
                  key={sessionId}
                  messages={messages}
                  agents={agents}
                  currentAgent={currentAgent}
                  isWaiting={waitResponse}
                  libraryNameById={libraryNameMap}
                  chatContextNameById={chatContextNameMap}
                />
                {showHistoryLoading && (
                  <Box mt={1} sx={{ display: "flex", justifyContent: "center" }}>
                    <CircularProgress size={18} thickness={4} sx={{ color: theme.palette.text.secondary }} />
                  </Box>
                )}
              </Box>
            </Box>

            <Box
              sx={{
                width: "80%",
                maxWidth: { xs: "100%", md: "1200px", lg: "1400px", xl: "1750px" },
                mx: "auto",
                pr: effectiveAttachmentsPanelOpen ? { xs: "min(92vw, 320px)", sm: "340px" } : 0,
                transition: (t) => t.transitions.create("padding-right"),
              }}
            >
              {/* User input area */}
              <Grid2 container width="100%" alignContent="center">
                <UserInput
                  ref={userInputRef}
                  agentChatOptions={currentAgent.chat_options}
                  isWaiting={waitResponse}
                  onSend={handleSend}
                  onStop={stopStreaming}
                  onContextChange={handleDraftContextChange}
                  sessionId={sessionId}
                  effectiveSessionId={effectiveSessionId}
                  uploadingFiles={uploadingFiles}
                  onFilesSelected={agentSupportsAttachments ? handleFilesSelected : undefined}
                  attachmentsRefreshTick={attachmentsRefreshTick}
                  serverPrefs={sessionPrefs as any}
                  refetchServerPrefs={refetchSessionPrefs}
                  selectedChatContextIds={selectedChatContextIds}
                  onSelectedChatContextIdsChange={setSelectedChatContextIdsFromHydration}
                  initialDocumentLibraryIds={initialDocumentLibraryIds}
                  initialPromptResourceIds={initialPromptResourceIds}
                  initialTemplateResourceIds={initialTemplateResourceIds}
                  initialSearchPolicy={initialSearchPolicy}
                  initialSearchRagScope={initialSearchRagScope}
                  initialDeepSearch={initialDeepSearch}
                  currentAgent={currentAgent}
                  agents={agents}
                  onSelectNewAgent={setCurrentAgent}
                  attachmentsPanelOpen={effectiveAttachmentsPanelOpen}
                  onAttachmentsPanelOpenChange={agentSupportsAttachments ? setAttachmentsPanelOpen : undefined}
                  onAttachmentCountChange={agentSupportsAttachments ? setAttachmentCount : undefined}
                  onDeepSearchEnabledChange={(enabled) => setDeepSearchEnabled(enabled)}
                />
              </Grid2>

              {/* Conversation tokens count */}
              <Grid2 container width="100%" display="flex" justifyContent="flex-end" marginTop={0.5}>
                <Tooltip
                  title={t("chatbot.tooltip.tokenUsage", {
                    input: inputTokenCounts,
                    output: outputTokenCounts,
                  })}
                >
                  <Typography fontSize="0.8rem" color={theme.palette.text.secondary} fontStyle="italic">
                    {t("chatbot.tooltip.tokenCount", {
                      total: outputTokenCounts + inputTokenCounts > 0 ? outputTokenCounts + inputTokenCounts : "...",
                    })}
                  </Typography>
                </Tooltip>
              </Grid2>
            </Box>
          </>
        )}
      </Box>

      <ChatKnowledge
        open={contextOpen}
        hasContext={hasContext}
        userInputContext={userInputContext}
        onClose={() => setContextOpen(false)}
        libraryNameMap={libraryNameMap}
        promptNameMap={promptNameMap}
        templateNameMap={templateNameMap}
      />
    </Box>
  );
};

export default ChatBot;
