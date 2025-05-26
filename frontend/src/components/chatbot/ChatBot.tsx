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


import { useEffect, useRef, useState } from 'react';
import { Box, Grid2, Typography, useTheme } from '@mui/material';
import { AgenticFlow } from "../../pages/Chat.tsx";
import { usePostTranscribeAudioMutation } from "../../frugalit/slices/api.tsx";
import { useToast } from "../ToastProvider.tsx";
import UserInput, { UserInputContent } from "./UserInput.tsx";
import DotsLoader from "../../common/DotsLoader.tsx";
import { v4 as uuidv4 } from "uuid"; // If not already imported
import { MessagesArea } from "./MessagesArea.tsx";
import { getAgentBadge } from '../../utils/avatar.tsx';
import { getConfig } from "../../common/config.tsx";
import { useGetChatBotMessagesMutation } from '../../slices/chatApi.tsx';
import { KeyCloakService } from '../../security/KeycloakService.ts';
import { StreamEvent, ChatMessagePayload, SessionSchema, FinalEvent } from '../../slices/chatApiStructures.ts';

export interface ChatBotError {
    session_id: string | null;
    content: string;
}

export interface ChatBotEventSend {
    user_id: string;
    session_id?: string;
    message: string;
    agent_name: string;
}

interface TranscriptionResponse {
    text?: string; // 'text' might be optional
}

const ChatBot = (
    {
        currentChatBotSession,
        currentAgenticFlow,
        agenticFlows,
        onUpdateOrAddSession,
        isCreatingNewConversation,
    }: {
        currentChatBotSession: SessionSchema,
        currentAgenticFlow: AgenticFlow,
        agenticFlows: AgenticFlow[],
        onUpdateOrAddSession: (session: SessionSchema) => void,
        isCreatingNewConversation: boolean,
    }
) => {

    const theme = useTheme();
    const { showInfo, showError } = useToast();
    const webSocketRef = useRef<WebSocket | null>(null);
    const [getChatBotMessages] = useGetChatBotMessagesMutation();
    const [postTranscribeAudio] = usePostTranscribeAudioMutation();
    const [webSocket, setWebSocket] = useState<WebSocket | null>(null);

    const [messages, setMessages] = useState<ChatMessagePayload[]>([]);
    const messagesRef = useRef<ChatMessagePayload[]>([]);
    // Append new messages to the state
    const addMessage = (msg: ChatMessagePayload) => {
        messagesRef.current = [...messagesRef.current, msg];
        setMessages(messagesRef.current);
    };
    // Update existing messages in the state. This resets the messagesRef to the new state
    const setAllMessages = (msgs: ChatMessagePayload[]) => {
        messagesRef.current = msgs;
        setMessages(msgs);
    };

    const [waitResponse, setWaitResponse] = useState<boolean>(false);

    const setupWebSocket = async (): Promise<WebSocket | null> => {
        const current = webSocketRef.current;

        if (current && current.readyState === WebSocket.OPEN) {
            return webSocketRef.current;
        }
        if (current && (current.readyState === WebSocket.CLOSING || current.readyState === WebSocket.CLOSED)) {
            console.warn("[🔄 ChatBot] WebSocket was closed or closing. Resetting...");
            webSocketRef.current = null;
        }
        console.debug("[📩 ChatBot] initiate new connection:");

        return new Promise((resolve, reject) => {
            const wsUrl = `${getConfig().backend_url_api || 'ws://localhost'}/fred/chatbot/query/ws`;
            const socket = new WebSocket(wsUrl);

            socket.onopen = () => {
                console.log("[✅ ChatBot] WebSocket connected");
                webSocketRef.current = socket;
                setMessages([]); // reset temporary buffer
                resolve(socket);
            };

            socket.onmessage = (event) => {
                try {
                    const response = JSON.parse(event.data);
                    switch (response.type) {
                        case "stream": {
                            const streamed = response as StreamEvent;
                            const msg = streamed.message;
                            console.log(`STREAM ${msg.session_id}-${msg.exchange_id}- ${msg.rank} content: ${msg.content.slice(0, 50)}...`);
                            addMessage(msg);
                            break;
                        }
                        case "final": {
                            const finalEvent = response as FinalEvent;
                            const streamedKeys = new Set(messagesRef.current.map(
                                m => `${m.session_id}-${m.exchange_id}-${m.rank}`
                            ));
                            const finalKeys = new Set(finalEvent.messages.map(
                                m => `${m.session_id}-${m.exchange_id}-${m.rank}`
                            ));

                            const missing = [...finalKeys].filter(k => !streamedKeys.has(k));
                            const unexpected = [...streamedKeys].filter(k => !finalKeys.has(k));

                            console.log("[FINAL EVENT SUMMARY]");
                            console.log("→ Messages in streamed but missing from final:", unexpected);
                            console.log("→ Messages in final but not in streamed:", missing);

                            console.log("FinalEvent messages:", finalEvent.messages);
                            if (response.session.id !== currentChatBotSession?.id) {
                                onUpdateOrAddSession(response.session);
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
                    }
                } catch (err) {
                    // Only close on fatal parsing error
                    console.error("[❌ ChatBot] Failed to parse message:", err);
                    showError({
                        summary: "Parsing Error",
                        detail: "Assistant response could not be processed."
                    });
                    setWaitResponse(false);
                    socket.close(); // ✅ Close only if the message is unreadable
                }
            };

            socket.onerror = (err) => {
                console.error("[❌ ChatBot] WebSocket error:", err);
                showError({
                    summary: "Connection Error",
                    detail: "Chat connection failed."
                });
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
        let socket: WebSocket | null = webSocket; // Track the current instance
        return () => {
            if (socket && socket.readyState === WebSocket.OPEN) {
                showInfo({
                    summary: "Closed",
                    detail: "Chat connection closed after unmount."
                });
                console.debug("Closing WebSocket before unmounting...");
                socket.close();
            }
            setWebSocket(null);
        };
    }, []);

    // Set up the WebSocket connection when the component mounts
    useEffect(() => {
        setupWebSocket();
        return () => {
            if (webSocketRef.current && webSocketRef.current.readyState === WebSocket.OPEN) {
                webSocketRef.current.close();
            }
            webSocketRef.current = null;
        };
    }, []);

    // Fetch messages from the server when the session changes. In particular, when the user selects a new session in the sidebar
    // or when the user starts a new conversation.
    useEffect(() => {
        if (currentChatBotSession?.id) {
            // 👇 Reset internal buffer as well. 
            setAllMessages([]);
            getChatBotMessages({ session_id: currentChatBotSession.id }).then((response) => {
                if (response.data) {
                    const serverMessages = response.data as ChatMessagePayload[];
                    console.group(`[📥 ChatBot] Loaded messages for session: ${currentChatBotSession.id}`);
                    console.log(`Total: ${serverMessages.length}`);
                    for (const msg of serverMessages) {
                        console.log({
                            id: msg.exchange_id, // Unique identifier for the message
                            type: msg.type, // e.g. "human", "assistant", "system"
                            subtype: msg.subtype, // e.g. "thought", "execution", "tool_result"
                            sender: msg.sender, // e.g. "user", "assistant"
                            task: msg.metadata?.fred?.task || null,
                            content: msg.content?.slice(0, 120),
                        });
                    }
                    console.groupEnd();
                    setAllMessages(serverMessages);
                }
            });
        }
    }, [currentChatBotSession?.id]);



    // Catch the user input
    const handleSend = async (content: UserInputContent) => {
        // Currently the logic is to send the first non-null content in the order of text, audio and file
        const userId = KeyCloakService.GetUserMail();
        const sessionId = currentChatBotSession?.id;
        const agentName = currentAgenticFlow.name;
        if (content.files && content.files.length > 0) {
            for (const file of content.files) {
                const formData = new FormData();
                formData.append("user_id", userId);
                formData.append("session_id", sessionId || "");  // "" if undefined
                formData.append("agent_name", agentName);
                formData.append("file", file);

                try {
                    const response = await fetch(`${getConfig().backend_url_api}/fred/chatbot/upload`, {
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
                    showInfo({
                        summary: "File Upload",
                        detail: `File ${file.name} uploaded successfully.`,
                    });
                } catch (err) {
                    console.error("❌ File upload failed:", err);
                    showError({
                        summary: "File Upload Error",
                        detail: (err as Error).message,
                    });
                }
            }
        }

        if (content.text) {
            queryChatBot(content.text.trim());
        } else if (content.audio) {
            setWaitResponse(true);
            const audioFile: File = new File([content.audio], "audio.mp3", { type: content.audio.type });
            postTranscribeAudio({ file: audioFile }).then((response) => {
                if (response.data) {
                    const message: TranscriptionResponse = response.data as TranscriptionResponse;
                    if (message.text) {
                        queryChatBot(message.text);
                    }
                }
            });
        } else {
            console.warn("No content to send.");
        }
    }

    // Query the chatbot
    const queryChatBot = async (input: string, agent?: AgenticFlow) => {
        console.log(`[📤 ChatBot] Sending message: ${input}`);
        const timestamp = new Date().toISOString();

        const userMessage: ChatMessagePayload = {
            exchange_id: uuidv4(),
            type: "human",
            sender: "user",
            content: input,
            timestamp,
            session_id: currentChatBotSession?.id || "unknown",
            rank: -1, // -1 for user messages the rank is assigned by the backend
            subtype: "final", // Default to final for user messages
            metadata: {}
        };
        addMessage(userMessage);
        console.log("[📤 ChatBot] About to send, session_id =", currentChatBotSession?.id);
        const event: ChatBotEventSend = {
            user_id: KeyCloakService.GetUserMail(),
            message: input,
            agent_name: agent ? agent.name : currentAgenticFlow.name,
            session_id: currentChatBotSession?.id
        };

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
            showError({
                summary: "Connection Error",
                detail: "Could not send your message — connection failed."
            });
            setWaitResponse(false);
        }
    };

    // Reset the messages when the user starts a new conversation.
    useEffect(() => {
        if (!currentChatBotSession && isCreatingNewConversation) {
            setAllMessages([]);
        }
        console.log("isCreatingNewConversation", isCreatingNewConversation);
    }, [isCreatingNewConversation]);

    return (
        messages?.length ?
            <Grid2 container display="flex" justifyContent="center" height="100vh">
                {/* Chatbot messages area */}
                <Grid2
                    display="flex"
                    flexDirection='column'
                    flex='1'
                    size={{ xs: 8, md: 8, lg: 7 }} m={2} marginBottom={0} p={2} minHeight="80%" maxHeight="80%"
                    sx={{
                        overflowY: 'scroll',
                        overflowX: 'hidden',
                        scrollbarWidth: "none",
                        wordBreak: 'break-word',
                        position: "fixed", // Fix UserInput at the bottom of the viewport
                        alignContent: "center"

                    }}>
                    <MessagesArea
                        key={currentChatBotSession?.id}
                        messages={messages}
                        agenticFlows={agenticFlows}
                        currentAgenticFlow={currentAgenticFlow} />
                    {waitResponse && (
                        <Grid2 size='grow' marginTop={5}>
                            <DotsLoader dotColor={theme.palette.text.primary} />
                        </Grid2>
                    )}
                </Grid2>
                {/* User input area */}
                <Grid2
                    container
                    size={{ xs: 8, md: 8, lg: 7 }} m={2} p={2} mb={-2}
                    sx={{
                        position: "fixed", // Fix UserInput at the bottom of the viewport
                        bottom: "3%", // 2% from the bottom of the viewport
                        alignContent: "center"
                    }}
                >
                    <UserInput
                        enableFilesAttachment={true}
                        enableAudioAttachment={true}
                        isWaiting={waitResponse}
                        onSend={handleSend}
                    />
                </Grid2>
            </Grid2> :
            <Grid2 container display="flex" flexDirection="column" justifyContent="center" height="100vh"
                alignItems="center" gap={2}>
                {/* User input area */}
                <Grid2 container display="flex" alignItems="center" gap={2}>
                    <Box display='flex' flexDirection='row' alignItems='center'>
                        <Typography variant="h4" paddingRight={1}>Start a new conversation with {currentAgenticFlow.nickname}</Typography>
                        {getAgentBadge(currentAgenticFlow.nickname)}
                    </Box>
                </Grid2>
                <Typography variant="h5">{currentAgenticFlow.role}.</Typography>
                <Typography>You can select another assistant in the settings panel.</Typography>
                <Grid2 size={{ xs: 12, md: 10, lg: 6 }} m={2} marginTop={0} minHeight="15%" display="flex"
                    alignItems="start">
                    <UserInput
                        enableFilesAttachment={true}
                        enableAudioAttachment={true}
                        isWaiting={waitResponse}
                        onSend={handleSend}
                    />
                </Grid2>
            </Grid2>

    );
};

export default ChatBot;

