// src/controllers/useChatSocket.ts
// Copyright Thales 2025
// Apache-2.0

import { useCallback, useEffect, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

import { getConfig } from "../common/config";
import { KeyCloakService } from "../security/KeycloakService";
import { toWsUrl, mergeAuthoritative, upsertOne } from "../components/chatbot/ChatBotUtils";

import type {
  AgenticFlow,
  ChatAskInput,
  ChatMessage,
  FinalEvent,
  RuntimeContext,
  SessionSchema,
  StreamEvent,
} from "../slices/agentic/agenticOpenApi";

/**
 * WebSocket transport extracted from ChatBot.
 * Owns: connect/close, streaming, finalization, error mapping.
 * Exposes: messages state, wait flag, send(), reset(), replaceAllMessages().
 */
export function useChatSocket(params: {
  currentSession: SessionSchema | null;
  currentAgenticFlow: AgenticFlow;
  onUpdateOrAddSession?: (s: SessionSchema) => void;
  onBindDraftAgentToSessionId?: (sessionId: string) => void;
}) {
  const { currentSession, currentAgenticFlow, onUpdateOrAddSession, onBindDraftAgentToSessionId } = params;

  const webSocketRef = useRef<WebSocket | null>(null);
  const wsTokenRef = useRef<string | null>(null);

  // authoritative message state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const messagesRef = useRef<ChatMessage[]>([]);
  const [waitResponse, setWaitResponse] = useState(false);

  const setAll = useCallback((next: ChatMessage[]) => {
    messagesRef.current = next;
    setMessages(next);
  }, []);

  const reset = useCallback(() => setAll([]), [setAll]);
  const replaceAllMessages = useCallback((serverMessages: ChatMessage[]) => {
    setAll(serverMessages);
  }, [setAll]);

  // --- Connect / Close ---

  const connect = useCallback(async (): Promise<WebSocket> => {
    const existing = webSocketRef.current;
    if (existing && existing.readyState === WebSocket.OPEN) return existing;

    if (existing && (existing.readyState === WebSocket.CLOSING || existing.readyState === WebSocket.CLOSED)) {
      webSocketRef.current = null;
    }

    await KeyCloakService.ensureFreshToken(30);
    const token = KeyCloakService.GetToken();

    const rawWs = toWsUrl(getConfig().backend_url_api, "/agentic/v1/chatbot/query/ws");
    const url = new URL(rawWs);
    if (token) url.searchParams.set("token", token);

    return new Promise<WebSocket>((resolve, reject) => {
      const socket = new WebSocket(url.toString());
      wsTokenRef.current = token || null;

      socket.onopen = () => {
        webSocketRef.current = socket;
        resolve(socket);
      };

      socket.onerror = (err) => {
        reject(err);
      };

      socket.onclose = () => {
        webSocketRef.current = null;
        setWaitResponse(false);
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as StreamEvent | FinalEvent | { type: "error"; content: string };

          switch (payload.type) {
            case "stream": {
              const streamed = payload as StreamEvent;
              const msg = streamed.message as ChatMessage;

              // guard other sessions
              if (currentSession?.id && msg.session_id !== currentSession.id) return;

              messagesRef.current = upsertOne(messagesRef.current, msg);
              setMessages(messagesRef.current);
              break;
            }

            case "final": {
              const final = payload as FinalEvent;

              messagesRef.current = mergeAuthoritative(messagesRef.current, final.messages);
              setMessages(messagesRef.current);

              const sid = final.session.id;
              if (sid) onBindDraftAgentToSessionId?.(sid);
              if (!currentSession || final.session.id !== currentSession.id) {
                onUpdateOrAddSession?.(final.session);
              }
              setWaitResponse(false);
              break;
            }

            case "error": {
              console.error("[ChatSocket] error:", payload);
              setWaitResponse(false);
              break;
            }

            default:
              console.warn("[ChatSocket] unknown payload:", payload);
              setWaitResponse(false);
          }
        } catch (e) {
          console.error("[ChatSocket] parse error:", e);
          setWaitResponse(false);
          socket.close();
        }
      };
    });
  }, [currentSession?.id, onBindDraftAgentToSessionId, onUpdateOrAddSession]);

  const close = useCallback(() => {
    const ws = webSocketRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.close();
    webSocketRef.current = null;
  }, []);

  useEffect(() => {
    // auto-connect on mount
    connect().catch((e) => console.error("[ChatSocket] connect failed:", e));
    return () => close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Send ---

  const send = useCallback(
    async (message: string, runtimeContext?: RuntimeContext, overrides?: { agent?: AgenticFlow; session?: SessionSchema }) => {
      const socket = await connect();
      if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error("WebSocket not open");

      const agent = overrides?.agent ?? currentAgenticFlow;
      const session = overrides?.session ?? currentSession;

      const base: ChatAskInput = {
        message,
        agent_name: agent.name,
        session_id: session?.id,
        runtime_context: runtimeContext,
      };
      const event: ChatAskInput = { ...base, client_exchange_id: uuidv4() };

      setWaitResponse(true);
      socket.send(JSON.stringify(event));
    },
    [connect, currentAgenticFlow, currentSession],
  );

  return {
    // state
    messages,
    waitResponse,

    // actions
    send,
    reset,
    replaceAllMessages,

    // lifecycle
    connect,
    close,
  };
}
