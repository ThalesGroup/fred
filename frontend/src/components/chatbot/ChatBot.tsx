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

import { Box, Grid2, Tooltip, Typography, useTheme } from "@mui/material";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { v4 as uuidv4 } from "uuid";
import { AnyAgent } from "../../common/agent.ts";
import { getConfig } from "../../common/config.tsx";
import DotsLoader from "../../common/DotsLoader.tsx";
import { KeyCloakService } from "../../security/KeycloakService.ts";
import {
  ChatAskInput,
  ChatMessage,
  FinalEvent,
  RuntimeContext,
  SessionSchema,
  StreamEvent,
  useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery,
  useUploadFileAgenticV1ChatbotUploadPostMutation,
} from "../../slices/agentic/agenticOpenApi.ts";
import {
  TagType,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider.tsx";
import { keyOf, mergeAuthoritative, sortMessages, toWsUrl, upsertOne } from "./ChatBotUtils.tsx";
import ChatKnowledge from "./ChatKnowledge.tsx";
import { MessagesArea } from "./MessagesArea.tsx";
import UserInput, { UserInputContent } from "./user_input/UserInput.tsx";

export interface ChatBotError {
  session_id: string | null;
  content: string;
}

// interface TranscriptionResponse {
//   text?: string;
// }

export interface ChatBotProps {
  currentChatBotSession: SessionSchema;
  currentAgent: AnyAgent;
  agents: AnyAgent[];
  onSelectNewAgent: (flow: AnyAgent) => void;
  onUpdateOrAddSession: (session: SessionSchema) => void;
  isCreatingNewConversation: boolean;
  runtimeContext?: RuntimeContext;
  onBindDraftAgentToSessionId?: (sessionId: string) => void;
}

const ChatBot = ({
  currentChatBotSession,
  currentAgent,
  agents,
  onSelectNewAgent,
  onUpdateOrAddSession,
  isCreatingNewConversation,
  runtimeContext: baseRuntimeContext,
  onBindDraftAgentToSessionId,
}: ChatBotProps) => {
  const theme = useTheme();
  const { t } = useTranslation();

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

  const { showInfo, showError } = useToast();
  const webSocketRef = useRef<WebSocket | null>(null);
  const [webSocket, setWebSocket] = useState<WebSocket | null>(null);
  const wsTokenRef = useRef<string | null>(null);
  // When backend creates a session during first file upload, keep it locally
  // so the immediate next message uses the same session id.
  const pendingSessionIdRef = useRef<string | null>(null);
  // Track files being uploaded right now to surface inline progress in the input bar
  const [uploadingFiles, setUploadingFiles] = useState<string[]>([]);

  // Noms des libs / prompts / templates / chat-context
  const { data: docLibs = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" as TagType });
  const { data: promptResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "prompt" });
  const { data: templateResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "template" });
  const { data: chatContextResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({
    kind: "chat-context",
  });

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

  // Lazy messages fetcher
  const [fetchHistory] = useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery();
  const [uploadChatFile] = useUploadFileAgenticV1ChatbotUploadPostMutation();
  // Local tick to signal attachments list to refresh after successful uploads
  const [attachmentsRefreshTick, setAttachmentsRefreshTick] = useState<number>(0);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesRef = useRef<ChatMessage[]>([]);

  // keep state + ref in sync
  const setAllMessages = (msgs: ChatMessage[]) => {
    messagesRef.current = msgs;
    setMessages(msgs);
  };

  const [waitResponse, setWaitResponse] = useState<boolean>(false);
  const stopStreaming = () => {
    const socket = webSocketRef.current;
    if (!socket) {
      setWaitResponse(false);
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
      setWebSocket(null);
      setWaitResponse(false);
    }
  };

  // === SINGLE scroll container ref (attach to the ONLY overflow element) ===
  const scrollerRef = useRef<HTMLDivElement>(null);

  // === Hard guarantee: snap to absolute bottom after render ===
  useLayoutEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, currentChatBotSession?.id]);

  // Clear pending session once parent propagated the real session
  useEffect(() => {
    if (currentChatBotSession?.id && pendingSessionIdRef.current === currentChatBotSession.id) {
      pendingSessionIdRef.current = null;
    }
  }, [currentChatBotSession?.id]);

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

    return new Promise((resolve, reject) => {
      const rawWsUrl = toWsUrl(getConfig().backend_url_api, "/agentic/v1/chatbot/query/ws");
      const url = new URL(rawWsUrl);
      if (token) url.searchParams.set("token", token); // ⚠️ nécessite WSS en prod + logs sans query

      const socket = new WebSocket(url.toString());
      wsTokenRef.current = token || null; // mémo pour détection simple de changement

      socket.onopen = () => {
        console.log("[✅ ChatBot] WebSocket connected");
        webSocketRef.current = socket;
        setWebSocket(socket);
        resolve(socket);
      };
      socket.onmessage = (event) => {
        try {
          const response = JSON.parse(event.data);

          switch (response.type) {
            case "stream": {
              const streamed = response as StreamEvent;
              const msg = streamed.message as ChatMessage;

              // Ignore streams for another session than the one being viewed
              if (currentChatBotSession?.id && msg.session_id !== currentChatBotSession.id) {
                console.warn("Ignoring stream for another session:", msg.session_id);
                break;
              }

              // Upsert streamed message and keep order stable
              messagesRef.current = upsertOne(messagesRef.current, msg);
              setMessages(messagesRef.current);
              // ⛔ no scrolling logic here — the layout effect handles it post-render
              break;
            }

            case "final": {
              const finalEvent = response as FinalEvent;

              // Optional debug summary
              const streamedKeys = new Set(messagesRef.current.map((m) => keyOf(m)));
              const finalKeys = new Set(finalEvent.messages.map((m) => keyOf(m)));
              const missing = [...finalKeys].filter((k) => !streamedKeys.has(k));
              const unexpected = [...streamedKeys].filter((k) => !finalKeys.has(k));
              console.log("[FINAL EVENT SUMMARY]", { missing, unexpected });

              // Merge authoritative finals (includes citations/metadata)
              messagesRef.current = mergeAuthoritative(messagesRef.current, finalEvent.messages);
              setMessages(messagesRef.current);

              const sid = finalEvent.session.id;
              if (sid) {
                console.log("[🔗 ChatBot] Binding draft agent to session id from final event:", sid);
                onBindDraftAgentToSessionId?.(sid);
              }
              // Accept session update if backend created/switched it
              if (finalEvent.session.id !== currentChatBotSession?.id) {
                onUpdateOrAddSession(finalEvent.session);
              }
              setWaitResponse(false);
              break;
            }

            case "error": {
              showError({ summary: "Error", detail: response.content });
              console.error("[RCV ERROR ChatBot] WebSocket error:", response);
              setWaitResponse(false);
              break;
            }

            default: {
              console.warn("[⚠️ ChatBot] Unknown message type:", response.type);
              showError({
                summary: "Unknown Message",
                detail: `Received unknown message type: ${response.type}`,
              });
              setWaitResponse(false);
              break;
            }
          }
        } catch (err) {
          console.error("[❌ ChatBot] Failed to parse message:", err);
          showError({ summary: "Parsing Error", detail: "Assistant response could not be processed." });
          setWaitResponse(false);
          socket.close(); // Close only if the payload is unreadable
        }
      };

      socket.onerror = (err) => {
        console.error("[❌ ChatBot] WebSocket error:", err);
        showError({ summary: "Connection Error", detail: "Chat connection failed." });
        setWaitResponse(false);
        reject(err);
      };

      socket.onclose = () => {
        console.warn("[❌ ChatBot] WebSocket closed");
        webSocketRef.current = null;
        wsTokenRef.current = null;
        setWebSocket(null);
        setWaitResponse(false);
      };
    });
  };

  // Close the WebSocket connection when the component unmounts
  useEffect(() => {
    const socket: WebSocket | null = webSocket;
    return () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        showInfo({ summary: "Closed", detail: "Chat connection closed after unmount." });
        console.debug("Closing WebSocket before unmounting...");
        socket.close();
      }
      setWebSocket(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // mount/unmount

  // Set up the WebSocket connection when the component mounts
  useEffect(() => {
    setupWebSocket();
    return () => {
      if (webSocketRef.current && webSocketRef.current.readyState === WebSocket.OPEN) {
        webSocketRef.current.close();
      }
      webSocketRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // mount/unmount

  // Fetch messages when the session changes
  useEffect(() => {
    const id = currentChatBotSession?.id;

    if (!id) {
      messagesRef.current = [];
      setAllMessages([]);
      return;
    }

    const existingForSession = messagesRef.current.filter((msg) => msg.session_id === id);
    if (existingForSession.length > 0) {
      const sortedExisting = sortMessages(existingForSession);
      messagesRef.current = sortedExisting;
      setAllMessages(sortedExisting);
    } else if (messagesRef.current.length > 0) {
      messagesRef.current = [];
      setAllMessages([]);
    }

    fetchHistory({ sessionId: id })
      .unwrap()
      .then((serverMessages) => {
        console.group(`[📥 ChatBot] Loaded messages for session: ${id}`);
        console.log(`Total: ${serverMessages.length}`);
        for (const msg of serverMessages) console.log(msg);
        console.groupEnd();

        const sorted = sortMessages(serverMessages);
        messagesRef.current = sorted;
        setAllMessages(sorted); // layout effect will scroll
        // NEW — If this is the first time we "see" this id, bind draft now.
        console.log("[🔗 ChatBot] Binding draft agent to session id from history load:", id);
        onBindDraftAgentToSessionId?.(id);
      })
      .catch((e) => {
        console.error("[❌ ChatBot] Failed to load messages:", e);
      });
  }, [currentChatBotSession?.id, fetchHistory]);

  // Chat knowledge persistance
  const storageKey = useMemo(() => {
    const uid = KeyCloakService.GetUserId?.() || "anon";
    const agent = currentAgent?.name || "default";
    return `chatctx:${uid}:${agent}`;
  }, [currentAgent?.name]);

  // Init values (réhydratation)
  const [initialCtx, setInitialCtx] = useState<{
    documentLibraryIds: string[];
    promptResourceIds: string[];
    templateResourceIds: string[];
  }>({
    documentLibraryIds: [],
    promptResourceIds: [],
    templateResourceIds: [],
  });

  // load from local storage
  // Load defaults for a brand-new convo (no session yet). These act as initial* props for UserInput.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) {
        const parsed = JSON.parse(raw);
        setInitialCtx({
          documentLibraryIds: parsed.documentLibraryIds ?? [],
          promptResourceIds: parsed.promptResourceIds ?? [],
          templateResourceIds: parsed.templateResourceIds ?? [],
        });
      } else {
        setInitialCtx({ documentLibraryIds: [], promptResourceIds: [], templateResourceIds: [] });
      }
    } catch (e) {
      console.warn("Local context load failed:", e);
    }
  }, [storageKey]);

  const [userInputContext, setUserInputContext] = useState<any>(null);

  // IMPORTANT:
  // Save per-agent defaults *only before a session exists* (pre-session seeding).
  // Once a session exists, UserInput persists per-session selections itself.
  useEffect(() => {
    if (!userInputContext) return;
    const sessionId = pendingSessionIdRef.current || currentChatBotSession?.id;
    if (sessionId) return; // session exists -> do NOT save per-agent defaults here

    try {
      const payload = {
        documentLibraryIds: userInputContext.documentLibraryIds ?? [],
        promptResourceIds: userInputContext.promptResourceIds ?? [],
        templateResourceIds: userInputContext.templateResourceIds ?? [],
      };
      localStorage.setItem(storageKey, JSON.stringify(payload));
    } catch (e) {
      console.warn("Local context save failed:", e);
    }
  }, [
    userInputContext?.documentLibraryIds,
    userInputContext?.promptResourceIds,
    userInputContext?.templateResourceIds,
    storageKey,
    currentChatBotSession?.id, // guard: only save when undefined
  ]);

  // Handle user input (text/audio)
  const handleSend = async (content: UserInputContent) => {
    // Init runtime context
    const runtimeContext: RuntimeContext = { ...(baseRuntimeContext ?? {}) };

    // Add selected libraries / profiles (CANONIQUES — pas de doublon)
    if (content.documentLibraryIds?.length) {
      runtimeContext.selected_document_libraries_ids = content.documentLibraryIds;
    }

    // Policy
    runtimeContext.search_policy = content.searchPolicy || "semantic";

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

  // Upload files immediately when user selects them (sequential to preserve session binding)
  const handleFilesSelected = async (files: File[]) => {
    if (!files?.length) return;
    const sessionId = currentChatBotSession?.id;
    const agentName = currentAgent.name;

    for (const file of files) {
      setUploadingFiles((prev) => [...prev, file.name]);
      const formData = new FormData();
      const effectiveSessionId = pendingSessionIdRef.current || sessionId || "";
      formData.append("session_id", effectiveSessionId);
      formData.append("agent_name", agentName);
      formData.append("file", file);

      try {
        const res = await uploadChatFile({
          bodyUploadFileAgenticV1ChatbotUploadPost: formData as any,
        }).unwrap();
        const sid = (res as any)?.session_id as string | undefined;
        if (!sessionId && sid && pendingSessionIdRef.current !== sid) {
          onBindDraftAgentToSessionId?.(sid);
          pendingSessionIdRef.current = sid;
        }
        console.log("✅ Uploaded file:", file.name);
        // Refresh attachments view in the popover
        setAttachmentsRefreshTick((x) => x + 1);
      } catch (err: any) {
        const errMsg = err?.data?.detail || err?.error || (err as Error)?.message || "Unknown error";
        console.error("❌ File upload failed:", err);
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
    console.log(`[📤 ChatBot] Sending message: ${input}`);
    // Get tokens for backend use. This proacively allows the backend to perform
    // user-authenticated operations (e.g., vector search) on behalf of the user.
    // The backend is then responsible for refreshing tokens as needed. Which will rarely be needed
    // because tokens are refreshed often on the frontend.
    const refreshToken = KeyCloakService.GetRefreshToken();
    const accessToken = KeyCloakService.GetToken();
    const eventBase: ChatAskInput = {
      message: input,
      agent_name: agent ? agent.name : currentAgent.name,
      session_id: pendingSessionIdRef.current || currentChatBotSession?.id,
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
        setWaitResponse(true);
        socket.send(JSON.stringify(event));
        console.log("[📤 ChatBot] Sent message:", event);
      } else {
        throw new Error("WebSocket not open");
      }
    } catch (err) {
      console.error("[❌ ChatBot] Failed to send message:", err);
      showError({ summary: "Connection Error", detail: "Could not send your message — connection failed." });
      setWaitResponse(false);
    }
  };

  // Reset the messages when the user starts a new conversation.
  useEffect(() => {
    if (!currentChatBotSession && isCreatingNewConversation) {
      setAllMessages([]);
    }
    console.log("isCreatingNewConversation", isCreatingNewConversation);
  }, [isCreatingNewConversation, currentChatBotSession]);

  const outputTokenCounts: number =
    messages && messages.length
      ? messages.reduce((sum, msg) => sum + (msg.metadata?.token_usage?.output_tokens || 0), 0)
      : 0;

  const inputTokenCounts: number =
    messages && messages.length
      ? messages.reduce((sum, msg) => sum + (msg.metadata?.token_usage?.input_tokens || 0), 0)
      : 0;
  // After your state declarations
  const effectiveSessionId = pendingSessionIdRef.current || currentChatBotSession?.id || undefined;
  const showWelcome = !waitResponse && (isCreatingNewConversation || messages.length === 0);

  const hasContext =
    !!userInputContext &&
    ((userInputContext?.files?.length ?? 0) > 0 ||
      !!userInputContext?.audioBlob ||
      (userInputContext?.documentLibraryIds?.length ?? 0) > 0 ||
      (userInputContext?.promptResourceIds?.length ?? 0) > 0 ||
      (userInputContext?.templateResourceIds?.length ?? 0) > 0);

  return (
    <Box width={"100%"} height="100%" display="flex" flexDirection="column" alignItems="center" sx={{ minHeight: 0 }}>
      {/* ===== Conversation header status =====
           Fred rationale:
           - Always show the conversation context so developers/users immediately
             understand if they’re in a persisted session or a draft.
           - Avoid guesswork (messages length, etc.). Keep UX deterministic. */}

      <Box
        width="80%"
        maxWidth="768px"
        display="flex"
        height="100vh"
        flexDirection="column"
        alignItems="center"
        paddingBottom={1}
        sx={{ minHeight: 0, overflow: "hidden" }}
      >
        {/* Conversation start: new conversation without message */}
        {showWelcome && (
          <Box
            sx={{
              minHeight: "100vh",
              width: "100%",
              px: { xs: 2, sm: 3 },
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 2.5,
            }}
          >
            {/* Welcome hint */}
            <Typography variant="h5" color="text.primary" sx={{ textAlign: "center" }}>
              {t("chatbot.startNew", { name: currentAgent?.name ?? "assistant" })}
            </Typography>
            {/* Input area */}
            <Box sx={{ width: "min(900px, 100%)" }}>
              <UserInput
                agentChatOptions={currentAgent.chat_options}
                isWaiting={waitResponse}
                onSend={handleSend}
                onStop={stopStreaming}
                onContextChange={setUserInputContext}
                sessionId={currentChatBotSession?.id}
                effectiveSessionId={effectiveSessionId}
                uploadingFiles={uploadingFiles}
                onFilesSelected={handleFilesSelected}
                attachmentsRefreshTick={attachmentsRefreshTick}
                initialDocumentLibraryIds={initialCtx.documentLibraryIds}
                initialPromptResourceIds={initialCtx.promptResourceIds}
                initialTemplateResourceIds={initialCtx.templateResourceIds}
                currentAgent={currentAgent}
                agents={agents}
                onSelectNewAgent={onSelectNewAgent}
              />
            </Box>
          </Box>
        )}

        {/* Ongoing conversation */}
        {!showWelcome && (
          <>
            {/* Chatbot messages area */}
            <Grid2
              ref={scrollerRef}
              display="flex"
              flexDirection="column"
              flex="1"
              width="100%"
              p={2}
              sx={{
                overflowY: "auto",
                overflowX: "hidden",
                scrollbarWidth: "none",
                wordBreak: "break-word",
                alignContent: "center",
              }}
            >
              <MessagesArea
                key={currentChatBotSession?.id}
                messages={messages}
                agents={agents}
                currentAgent={currentAgent}
                libraryNameById={libraryNameMap}
                chatContextNameById={chatContextNameMap}
              />
              {waitResponse && (
                <Box mt={1} sx={{ alignSelf: "flex-start" }}>
                  <DotsLoader dotColor={theme.palette.text.primary} />
                </Box>
              )}
            </Grid2>

            {/* User input area */}
            <Grid2 container width="100%" alignContent="center">
              <UserInput
                agentChatOptions={currentAgent.chat_options}
                isWaiting={waitResponse}
                onSend={handleSend}
                onStop={stopStreaming}
                onContextChange={setUserInputContext}
                sessionId={currentChatBotSession?.id}
                effectiveSessionId={effectiveSessionId}
                uploadingFiles={uploadingFiles}
                onFilesSelected={handleFilesSelected}
                attachmentsRefreshTick={attachmentsRefreshTick}
                initialDocumentLibraryIds={initialCtx.documentLibraryIds}
                initialPromptResourceIds={initialCtx.promptResourceIds}
                initialTemplateResourceIds={initialCtx.templateResourceIds}
                currentAgent={currentAgent}
                agents={agents}
                onSelectNewAgent={onSelectNewAgent}
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
