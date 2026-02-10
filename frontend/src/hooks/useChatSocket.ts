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

import { useCallback, useEffect, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

import { getConfig } from "../common/config";
import { mergeAuthoritative, toWsUrl, upsertOne } from "../components/chatbot/ChatBotUtils";
import { KeyCloakService } from "../security/KeycloakService";

import { AnyAgent } from "../common/agent";
import type {
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
  currentAgent: AnyAgent;
  onUpdateOrAddSession?: (s: SessionSchema) => void;
  onBindDraftAgentToSessionId?: (sessionId: string) => void;
}) {
  const { currentSession, currentAgent, onUpdateOrAddSession, onBindDraftAgentToSessionId } = params;

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
  const replaceAllMessages = useCallback(
    (serverMessages: ChatMessage[]) => {
      setAll(serverMessages);
    },
    [setAll],
  );

  // --- Connect / Close ---

  const connect = useCallback(async (): Promise<WebSocket> => {
    await KeyCloakService.ensureFreshToken(30);
    const token = KeyCloakService.GetToken();

    const existing = webSocketRef.current;
    // Reconnect whenever Keycloak rotates the access token so backend calls use the fresh identity.
    const tokenChanged = Boolean(token && wsTokenRef.current && wsTokenRef.current !== token);

    if (existing) {
      if (existing.readyState === WebSocket.OPEN && !tokenChanged) {
        return existing;
      }

      try {
        existing.close();
      } catch (err) {
        console.warn("[ChatSocket] error closing stale WebSocket:", err);
      } finally {
        webSocketRef.current = null;
      }
    }

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
        wsTokenRef.current = null;
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
    wsTokenRef.current = null;
  }, []);

  useEffect(() => {
    // auto-connect on mount
    connect().catch((e) => console.error("[ChatSocket] connect failed:", e));
    return () => close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Send ---

  const send = useCallback(
    async (
      message: string,
      runtimeContext?: RuntimeContext,
      overrides?: { agent?: AnyAgent; session?: SessionSchema },
    ) => {
      const socket = await connect();
      if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error("WebSocket not open");

      const agent = overrides?.agent ?? currentAgent;
      const session = overrides?.session ?? currentSession;

      const base: ChatAskInput = {
        message,
        agent_id: agent.id,
        session_id: session?.id,
        runtime_context: runtimeContext,
      };
      const event: ChatAskInput = { ...base, client_exchange_id: uuidv4() };

      setWaitResponse(true);
      socket.send(JSON.stringify(event));
    },
    [connect, currentAgent, currentSession],
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
