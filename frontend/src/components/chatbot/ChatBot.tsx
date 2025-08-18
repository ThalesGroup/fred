// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

import { Box, Grid2, Tooltip, Typography, useTheme } from "@mui/material";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { v4 as uuidv4 } from "uuid";
import { getConfig } from "../../common/config.tsx";
import DotsLoader from "../../common/DotsLoader.tsx";
import { usePostTranscribeAudioMutation } from "../../frugalit/slices/api.tsx";
import { KeyCloakService } from "../../security/KeycloakService.ts";
import {
  AgenticFlow,
  ChatAskInput,
  ChatMessagePayload,
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

  const { showInfo, showError } = useToast();
  const webSocketRef = useRef<WebSocket | null>(null);
  const [postTranscribeAudio] = usePostTranscribeAudioMutation();
  const [webSocket, setWebSocket] = useState<WebSocket | null>(null);

  // Lazy messages fetcher
  const [fetchHistory] =
    useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery();

  const [messages, setMessages] = useState<ChatMessagePayload[]>([]);
  const messagesRef = useRef<ChatMessagePayload[]>([]);

  // State mutators that keep the ref in sync (prevents stale closures)
  const setAllMessages = (msgs: ChatMessagePayload[]) => {
    messagesRef.current = msgs;
    setMessages(msgs);
  };

  const [waitResponse, setWaitResponse] = useState<boolean>(false);

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
              const msg = streamed.message as ChatMessagePayload;

              // Ignore streams for another session than the one being viewed
              if (currentChatBotSession?.id && msg.session_id !== currentChatBotSession.id) {
                console.warn("Ignoring stream for another session:", msg.session_id);
                break;
              }

              // Upsert streamed message and keep order stable
              messagesRef.current = upsertOne(messagesRef.current, msg);
              setMessages(messagesRef.current);

              console.log(
                `STREAM ${msg.session_id}-${msg.exchange_id}-${msg.rank} : ${msg.content?.slice(0, 80)}...`,
              );
              break;
            }

            case "final": {
              const finalEvent = response as FinalEvent;

              // Debug summary (optional)
              const streamedKeys = new Set(messagesRef.current.map((m) => keyOf(m)));
              const finalKeys = new Set(finalEvent.messages.map((m) => keyOf(m)));
              const missing = [...finalKeys].filter((k) => !streamedKeys.has(k));
              const unexpected = [...streamedKeys].filter((k) => !finalKeys.has(k));
              console.log("[FINAL EVENT SUMMARY]");
              console.log("→ in streamed but not final:", unexpected);
              console.log("→ in final but not streamed:", missing);

              // Merge authoritative finals (includes citations/metadata)
              messagesRef.current = mergeAuthoritative(messagesRef.current, finalEvent.messages);
              setMessages(messagesRef.current);

              // If backend created/switched session, accept it
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

  // Fetch messages from the server when the session changes
  useEffect(() => {
    const id = currentChatBotSession?.id;
    if (!id) return;

    // Clear view while fetching the authoritative history
    setAllMessages([]);

    fetchHistory({ sessionId: id })
      .unwrap()
      .then((serverMessages) => {
        console.group(`[📥 ChatBot] Loaded messages for session: ${id}`);
        console.log(`Total: ${serverMessages.length}`);
        for (const msg of serverMessages) {
          console.log({
            id: msg.exchange_id,
            type: msg.type,
            subtype: msg.subtype,
            sender: msg.sender,
            task: msg.metadata?.fred?.task || null,
            content: msg.content?.slice(0, 120),
          });
        }
        console.groupEnd();

        // Normalize order using the same sorter as stream/final
        setAllMessages(sortMessages(serverMessages));
      })
      .catch((e) => {
        console.error("[❌ ChatBot] Failed to load messages:", e);
      });
  }, [currentChatBotSession?.id, fetchHistory]);

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

    // Add only the client-side correlation id for this exchange.
    // Remove the cast once your OpenAPI types include client_exchange_id.
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

  return (
    <Box width={"100%"} height="100%" display="flex" flexDirection="column" alignItems="center">
      <Box
        width="80%"
        maxWidth="768px"
        display="flex"
        height="100vh"
        flexDirection="column"
        alignItems="center"
        paddingBottom={1}
      >
        {/* Conversation start: new conversation without message */}
        {isCreatingNewConversation && messages.length === 0 && (
          <Box
            display="flex"
            flexDirection="column"
            justifyContent="center"
            height="100vh"
            alignItems="center"
            gap={2}
            width="100%"
          >
            {/* User input area */}
            <Grid2 container display="flex" alignItems="center" gap={2}>
              <Box display="flex" flexDirection="row" alignItems="center">
                <Typography variant="h4" paddingRight={1}>
                  {t("chatbot.startNew", { name: currentAgenticFlow.nickname })}
                </Typography>
                {getAgentBadge(currentAgenticFlow.nickname)}
              </Box>
            </Grid2>
            <Typography variant="h5">{currentAgenticFlow.role}.</Typography>
            <Typography>{t("chatbot.changeAssistant")}</Typography>
            <Box display="flex" alignItems="start" width="100%">
              <UserInput
                enableFilesAttachment={true}
                enableAudioAttachment={true}
                isWaiting={waitResponse}
                onSend={handleSend}
              />
            </Box>
          </Box>
        )}

        {/* Ongoing conversation */}
        {(messages.length > 0 || !isCreatingNewConversation) && (
          <>
            {/* Chatbot messages area */}
            <Grid2
              display="flex"
              flexDirection="column"
              flex="1"
              width="100%"
              p={2}
              sx={{
                overflowY: "scroll",
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
                <Grid2 size="grow" marginTop={5}>
                  <DotsLoader dotColor={theme.palette.text.primary} />
                </Grid2>
              )}
            </Grid2>

            {/* User input area */}
            <Grid2 container width="100%" alignContent="center">
              <UserInput
                enableFilesAttachment={true}
                enableAudioAttachment={true}
                isWaiting={waitResponse}
                onSend={handleSend}
              />
            </Grid2>

            {/* Conversation tokens count */}
            <Grid2 container width="100%" display="fex" justifyContent="flex-end" marginTop={0.5}>
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
    </Box>
  );
};

export default ChatBot;
