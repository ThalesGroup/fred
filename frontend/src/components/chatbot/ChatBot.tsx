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
import { useEffect, useRef, useState, useLayoutEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { v4 as uuidv4 } from "uuid";
import { getConfig } from "../../common/config.tsx";
import DotsLoader from "../../common/DotsLoader.tsx";
import { usePostTranscribeAudioMutation } from "../../frugalit/slices/api.tsx";
import { KeyCloakService } from "../../security/KeycloakService.ts";
import {
  AgenticFlow,
  ChatAskInput,
  ChatMessage,
  FinalEvent,
  RuntimeContext,
  SessionSchema,
  StreamEvent,
  useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery,
} from "../../slices/agentic/agenticOpenApi.ts";
import { getAgentBadge } from "../../utils/avatar.tsx";
import { useToast } from "../ToastProvider.tsx";
import { MessagesArea } from "./MessagesArea.tsx";
import UserInput, { UserInputContent } from "./UserInput.tsx";
import { keyOf, mergeAuthoritative, sortMessages, toWsUrl, upsertOne } from "./ChatBotUtils.tsx";
import {
  TagType,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import ChatKnowledge from "./ChatKnowledge.tsx";

export interface ChatBotError {
  session_id: string | null;
  content: string;
}

interface TranscriptionResponse {
  text?: string;
}

export interface ChatBotProps {
  currentChatBotSession: SessionSchema;
  currentAgenticFlow: AgenticFlow;
  agenticFlows: AgenticFlow[];
  onUpdateOrAddSession: (session: SessionSchema) => void;
  isCreatingNewConversation: boolean;
  runtimeContext?: RuntimeContext;
}

const ChatBot = ({
  currentChatBotSession,
  currentAgenticFlow,
  agenticFlows,
  onUpdateOrAddSession,
  isCreatingNewConversation,
  runtimeContext: baseRuntimeContext,
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
  const [postTranscribeAudio] = usePostTranscribeAudioMutation();
  const [webSocket, setWebSocket] = useState<WebSocket | null>(null);

  // Noms des libs / prompts / templates
  const { data: docLibs = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" as TagType });
  const { data: promptResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "prompt" });
  const { data: templateResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "template" });

  const libraryNameMap = useMemo(
    () => Object.fromEntries((docLibs as any[]).map((x: any) => [x.id, x.name])),
    [docLibs],
  );
  const promptNameMap = useMemo(
    () => Object.fromEntries((promptResources as any[]).map((x: any) => [x.id, x.name ?? x.id])),
    [promptResources],
  );
  const templateNameMap = useMemo(
    () => Object.fromEntries((templateResources as any[]).map((x: any) => [x.id, x.name ?? x.id])),
    [templateResources],
  );

  // Lazy messages fetcher
  const [fetchHistory] = useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesRef = useRef<ChatMessage[]>([]);

  // keep state + ref in sync
  const setAllMessages = (msgs: ChatMessage[]) => {
    messagesRef.current = msgs;
    setMessages(msgs);
  };

  const [waitResponse, setWaitResponse] = useState<boolean>(false);

  // === SINGLE scroll container ref (attach to the ONLY overflow element) ===
  const scrollerRef = useRef<HTMLDivElement>(null);

  // === Hard guarantee: snap to absolute bottom after render ===
  useLayoutEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, currentChatBotSession?.id]);

  const setupWebSocket = async (): Promise<WebSocket | null> => {
    const current = webSocketRef.current;

    if (current && current.readyState === WebSocket.OPEN) {
      return current;
    }
    if (current && (current.readyState === WebSocket.CLOSING || current.readyState === WebSocket.CLOSED)) {
      console.warn("[🔄 ChatBot] WebSocket was closed or closing. Resetting...");
      webSocketRef.current = null;
    }
    console.debug("[📩 ChatBot] initiate new connection:");

    return new Promise((resolve, reject) => {
      const wsUrl = toWsUrl(getConfig().backend_url_api, "/agentic/v1/chatbot/query/ws");
      const socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        console.log("[✅ ChatBot] WebSocket connected");
        
        // Send authentication token for OAuth2 Token Exchange
        const userToken = KeyCloakService.GetToken();
        if (userToken) {
          socket.send(JSON.stringify({
            type: "auth",
            token: userToken
          }));
          console.debug("[🔐 ChatBot] Sent authentication token for OAuth2 Token Exchange");
        }
        
        webSocketRef.current = socket;
        setWebSocket(socket); // ensure unmount cleanup closes the right instance
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
    if (!id) return;

    setAllMessages([]); // clear view while fetching

    fetchHistory({ sessionId: id })
      .unwrap()
      .then((serverMessages) => {
        console.group(`[📥 ChatBot] Loaded messages for session: ${id}`);
        console.log(`Total: ${serverMessages.length}`);
        for (const msg of serverMessages) console.log(msg);
        console.groupEnd();

        setAllMessages(sortMessages(serverMessages)); // layout effect will scroll
      })
      .catch((e) => {
        console.error("[❌ ChatBot] Failed to load messages:", e);
      });
  }, [currentChatBotSession?.id, fetchHistory]);

  // Chat knowledge persistance
  const storageKey = useMemo(() => {
    const uid = KeyCloakService.GetUserId?.() || "anon";
    const agent = currentAgenticFlow?.name || "default";
    return `chatctx:${uid}:${agent}`;
  }, [currentAgenticFlow?.name]);

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
    const sessionId = currentChatBotSession?.id;
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

  // Handle user input (text/audio/files)
  const handleSend = async (content: UserInputContent) => {
    const userId = KeyCloakService.GetUserId();
    const sessionId = currentChatBotSession?.id;
    const agentName = currentAgenticFlow.name;

    // Init runtime context
    const runtimeContext: RuntimeContext = { ...baseRuntimeContext };

    // Add selected libraries/templates
    if (content.documentLibraryIds?.length) {
      runtimeContext.selected_document_libraries_ids = content.documentLibraryIds;
    }
    if (content.promptResourceIds?.length) {
      runtimeContext.selected_prompt_ids = content.promptResourceIds;
    }
    if (content.templateResourceIds?.length) {
      runtimeContext.selected_template_ids = content.templateResourceIds;
    }

    // Files upload
    if (content.files?.length) {
      for (const file of content.files) {
        const formData = new FormData();
        formData.append("user_id", userId);
        formData.append("session_id", sessionId || "");
        formData.append("agent_name", agentName);
        formData.append("file", file);

        try {
          const response = await fetch(`${getConfig().backend_url_api}/agentic/v1/chatbot/upload`, {
            method: "POST",
            body: formData,
          });

          if (!response.ok) {
            showError({
              summary: "File Upload Error",
              detail: `Failed to upload ${file.name}: ${response.statusText}`,
            });
            throw new Error(`Failed to upload ${file.name}`);
          }

          const result = await response.json();
          console.log("✅ Uploaded file:", result);
          showInfo({ summary: "File Upload", detail: `File ${file.name} uploaded successfully.` });
        } catch (err) {
          console.error("❌ File upload failed:", err);
          showError({ summary: "File Upload Error", detail: (err as Error).message });
        }
      }
    }

    if (content.text) {
      queryChatBot(content.text.trim(), undefined, runtimeContext);
    } else if (content.audio) {
      setWaitResponse(true);
      const audioFile: File = new File([content.audio], "audio.mp3", { type: content.audio.type });
      postTranscribeAudio({ file: audioFile }).then((response) => {
        if (response.data) {
          const message: TranscriptionResponse = response.data as TranscriptionResponse;
          if (message.text) {
            queryChatBot(message.text, undefined, runtimeContext);
          }
        }
      });
    } else {
      console.warn("No content to send.");
    }
  };

  /**
   * Send a new user message to the chatbot agent.
   * Backend is authoritative: we DO NOT add an optimistic user bubble.
   * The server streams the authoritative user message first.
   */
  const queryChatBot = async (input: string, agent?: AgenticFlow, runtimeContext?: RuntimeContext) => {
    console.log(`[📤 ChatBot] Sending message: ${input}`);

    const eventBase: ChatAskInput = {
      user_id: KeyCloakService.GetUserId(), // TODO: backend should infer from JWT; front sends for now
      message: input,
      agent_name: agent ? agent.name : currentAgenticFlow.name,
      session_id: currentChatBotSession?.id,
      runtime_context: runtimeContext,
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
            {/* Hero header */}
            <Box
              sx={{
                width: "min(900px, 100%)",
                borderRadius: 3,
                border: (t) => `1px solid ${t.palette.divider}`,
                background: (t) =>
                  `linear-gradient(180deg, ${t.palette.heroBackgroundGrad.gradientFrom}, ${t.palette.heroBackgroundGrad.gradientTo})`,
                boxShadow: (t) =>
                  t.palette.mode === "light" ? "0 1px 2px rgba(0,0,0,0.06)" : "0 1px 2px rgba(0,0,0,0.25)",
                px: { xs: 2, sm: 3 },
                py: { xs: 2, sm: 2.5 },
              }}
            >
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 1.25,
                  textAlign: "center",
                  flexWrap: "nowrap",
                }}
              >
                {getAgentBadge(currentAgenticFlow.nickname)}
                <Typography variant="h5" sx={{ fontWeight: 600, letterSpacing: 0.2 }}>
                  {t("chatbot.startNew", { name: currentAgenticFlow.nickname })}
                </Typography>
              </Box>

              <Box
                sx={{
                  mt: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 1.25,
                  color: "text.secondary",
                  textAlign: "center",
                  flexWrap: "wrap",
                }}
              >
                <Typography variant="body2" sx={{ fontStyle: "italic" }}>
                  {currentAgenticFlow.role}
                </Typography>

                <Box
                  sx={{
                    width: 1,
                    height: 14,
                    borderLeft: (t) => `1px solid ${t.palette.divider}`,
                    opacity: 0.6,
                  }}
                />
                <Typography variant="body2">{t("chatbot.changeAssistant")}</Typography>
              </Box>
            </Box>

            {/* Input area */}
            <Box sx={{ width: "min(900px, 100%)" }}>
              <UserInput
                enableFilesAttachment
                enableAudioAttachment
                isWaiting={waitResponse}
                onSend={handleSend}
                onContextChange={setUserInputContext}
                sessionId={currentChatBotSession?.id}
                initialDocumentLibraryIds={initialCtx.documentLibraryIds}
                initialPromptResourceIds={initialCtx.promptResourceIds}
                initialTemplateResourceIds={initialCtx.templateResourceIds}
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
                agenticFlows={agenticFlows}
                currentAgenticFlow={currentAgenticFlow}
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
                enableFilesAttachment={true}
                enableAudioAttachment={true}
                isWaiting={waitResponse}
                onSend={handleSend}
                onContextChange={setUserInputContext}
                sessionId={currentChatBotSession?.id}
                initialDocumentLibraryIds={initialCtx.documentLibraryIds}
                initialPromptResourceIds={initialCtx.promptResourceIds}
                initialTemplateResourceIds={initialCtx.templateResourceIds}
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
