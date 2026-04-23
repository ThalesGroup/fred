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

import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { v4 as uuidv4 } from "uuid";

import { useToast } from "../../../../components/ToastProvider";
import { useChatSse, ChatSseCallbacks } from "../../../../hooks/useChatSse";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type { AwaitingHumanEvent, ChatMessage } from "../../../../slices/agentic/agenticOpenApi";
import {
  usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import Button from "@shared/atoms/Button/Button";
import TextArea from "@shared/atoms/TextArea/TextArea";

import styles from "./ManagedChatPage.module.css";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function textOf(msg: ChatMessage): string {
  return (msg.parts ?? [])
    .filter((p) => p.type === "text")
    .map((p) => (p as { type: "text"; text: string }).text)
    .join("");
}

function roleLabel(msg: ChatMessage): string {
  if (msg.role === "user") return "You";
  if (msg.role === "tool") return "Tool";
  return "Agent";
}

/** Expand a RFC 6570 Level 1 URI template for a single {session_id} variable. */
function expandMessagesUrl(template: string, sessionId: string): string {
  return template.replace("{session_id}", encodeURIComponent(sessionId));
}

// ---------------------------------------------------------------------------
// HITL inline prompt
// ---------------------------------------------------------------------------

interface HitlPromptProps {
  event: AwaitingHumanEvent;
  onAnswer: (answer: string | boolean, freeText?: string) => void;
}

function HitlPrompt({ event, onAnswer }: HitlPromptProps) {
  const payload = event.payload as {
    title?: string | null;
    question?: string | null;
    choices?: { id: string; label: string }[] | null;
    free_text?: boolean | null;
  };

  const [freeText, setFreeText] = useState("");

  return (
    <div className={styles.hitlCard} role="group" aria-label="Agent is waiting for your input">
      {payload.title && <p className={styles.hitlTitle}>{payload.title}</p>}
      {payload.question && <p className={styles.hitlQuestion}>{payload.question}</p>}

      {payload.choices && payload.choices.length > 0 && (
        <div className={styles.hitlChoices}>
          {payload.choices.map((c) => (
            <Button
              key={c.id}
              color="secondary"
              variant="outlined"
              size="small"
              onClick={() => onAnswer(c.id)}
            >
              {c.label}
            </Button>
          ))}
        </div>
      )}

      {payload.free_text && (
        <div className={styles.hitlFreeText}>
          <TextArea
            label="Your answer"
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            rows={2}
          />
          <Button
            color="primary"
            variant="filled"
            size="small"
            disabled={!freeText.trim()}
            onClick={() => onAnswer(undefined, freeText)}
          >
            Send
          </Button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------

interface MessageBubbleProps {
  msg: ChatMessage;
}

function MessageBubble({ msg }: MessageBubbleProps) {
  const text = textOf(msg);
  const isUser = msg.role === "user";
  const isDelta =
    (msg.metadata?.extras as { streaming_delta?: boolean } | undefined)?.streaming_delta === true;

  if (!text && msg.channel !== "tool_call" && msg.channel !== "tool_result") return null;

  return (
    <div
      className={`${styles.bubble} ${isUser ? styles.bubbleUser : styles.bubbleAgent}`}
      aria-label={`${roleLabel(msg)} message`}
    >
      <span className={styles.bubbleRole}>{roleLabel(msg)}</span>
      {msg.channel === "tool_call" || msg.channel === "tool_result" ? (
        <span className={styles.bubbleTool}>
          {msg.channel === "tool_call" ? "⚙ Tool call" : "✓ Tool result"}
          {text ? `: ${text}` : ""}
        </span>
      ) : (
        <p className={`${styles.bubbleText} ${isDelta ? styles.streaming : ""}`}>{text}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ManagedChatPage() {
  const { teamId, agentInstanceId } = useParams<{
    teamId: string;
    agentInstanceId: string;
  }>();
  const [searchParams, setSearchParams] = useSearchParams();

  const { showError } = useToast();

  const [pendingHitl, setPendingHitl] = useState<AwaitingHumanEvent | null>(null);
  // sessionId is kept in URL query params (?session=<uuid>) for persistence across refreshes.
  const [sessionId, setSessionId] = useState<string | null>(() => searchParams.get("session"));
  const [input, setInput] = useState("");
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const historyLoadedRef = useRef<string | null>(null);

  const [prepareExecution] =
    usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation();
  const [registerSession] =
    usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation();

  const bindSessionId = useCallback(
    (sid: string) => {
      setSessionId(sid);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("session", sid);
        return next;
      }, { replace: true });
    },
    [setSearchParams],
  );

  const sseCallbacks: ChatSseCallbacks = {
    onBindDraftAgentToSessionId: bindSessionId,
    onAwaitingHuman: (event) => setPendingHitl(event),
    onError: (msg) => showError({ summary: "Agent error", detail: msg }),
  };

  const { messages, waitResponse, send, sendHitlResume, reset, replaceAllMessages } = useChatSse({
    agentInstanceId: agentInstanceId ?? "",
    teamId: teamId ?? "",
    ...sseCallbacks,
  });

  // Load history from runtime when the page mounts with a known sessionId.
  useEffect(() => {
    const sid = sessionId;
    if (!sid || !teamId || !agentInstanceId) return;
    if (historyLoadedRef.current === sid) return;
    historyLoadedRef.current = sid;

    const loadHistory = async () => {
      setIsLoadingHistory(true);
      try {
        await KeyCloakService.ensureFreshToken(30);
        const token = KeyCloakService.GetToken() ?? "";
        const prep = await prepareExecution({ teamId, agentInstanceId }).unwrap();
        const historyUrl = new URL(
          expandMessagesUrl(prep.messages_url_template, sid),
          window.location.origin,
        );
        const resp = await fetch(historyUrl.toString(), {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!resp.ok) return;
        const msgs: ChatMessage[] = await resp.json();
        if (msgs.length > 0) {
          replaceAllMessages(msgs);
        }
      } catch {
        // History load failure is non-fatal — user continues with empty view.
      } finally {
        setIsLoadingHistory(false);
      }
    };

    loadHistory();
  }, [sessionId, teamId, agentInstanceId, prepareExecution, replaceAllMessages]);

  // Scroll to bottom on new messages.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  if (!teamId || !agentInstanceId) {
    return (
      <div className={styles.error}>
        Missing <code>teamId</code> or <code>agentInstanceId</code> in URL.
      </div>
    );
  }

  const handleSend = () => {
    const text = input.trim();
    if (!text || waitResponse) return;
    setInput("");
    setPendingHitl(null);

    // Generate session_id upfront so the runtime receives it from the first turn.
    // The turn_persisted event will confirm the binding via onBindDraftAgentToSessionId.
    let sid = sessionId;
    if (!sid) {
      sid = uuidv4();
      bindSessionId(sid);
      // Register session metadata in control-plane (fire-and-forget — non-fatal).
      registerSession({
        teamId: teamId,
        createSessionRequest: {
          session_id: sid,
          agent_instance_id: agentInstanceId ?? undefined,
        },
      }).catch(() => {
        // Session registration failure is non-fatal; chat execution continues.
      });
    }

    send(text, sid);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleHitlAnswer = (answer: string | boolean, freeText?: string) => {
    if (!pendingHitl) return;
    setPendingHitl(null);
    sendHitlResume(pendingHitl, answer, freeText);
  };

  const handleNewConversation = () => {
    reset();
    setSessionId(null);
    setPendingHitl(null);
    historyLoadedRef.current = null;
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("session");
      return next;
    }, { replace: true });
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <span className={styles.headerTitle}>Managed Agent Chat</span>
        <span className={styles.headerMeta}>
          instance: <code>{agentInstanceId}</code>
        </span>
        <Button
          color="on-surface"
          variant="text"
          size="small"
          onClick={handleNewConversation}
        >
          New conversation
        </Button>
      </header>

      <div className={styles.messages} role="log" aria-live="polite" aria-label="Conversation">
        {isLoadingHistory && <p className={styles.thinking}>Loading conversation history…</p>}
        {!isLoadingHistory && messages.length === 0 && !waitResponse && (
          <p className={styles.empty}>Send a message to start the conversation.</p>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={`${msg.session_id}|${msg.exchange_id}|${msg.rank}|${msg.role}|${msg.channel}|${i}`} msg={msg} />
        ))}
        {waitResponse && <p className={styles.thinking}>Agent is thinking…</p>}
        {pendingHitl && <HitlPrompt event={pendingHitl} onAnswer={handleHitlAnswer} />}
        <div ref={bottomRef} />
      </div>

      <footer className={styles.footer}>
        <TextArea
          label="Message"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={waitResponse || isLoadingHistory}
          rows={2}
          placeholder="Press Enter to send, Shift+Enter for newline"
        />
        <Button
          color="primary"
          variant="filled"
          size="medium"
          disabled={!input.trim() || waitResponse || isLoadingHistory}
          onClick={handleSend}
        >
          Send
        </Button>
      </footer>
    </div>
  );
}
