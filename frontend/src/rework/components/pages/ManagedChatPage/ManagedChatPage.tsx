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

import { KeyboardEvent, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { useToast } from "../../../../components/ToastProvider";
import { useChatSse, ChatSseCallbacks } from "../../../../hooks/useChatSse";
import type { AwaitingHumanEvent, ChatMessage } from "../../../../slices/agentic/agenticOpenApi";
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

  const { showError } = useToast();

  const [pendingHitl, setPendingHitl] = useState<AwaitingHumanEvent | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const sseCallbacks: ChatSseCallbacks = {
    onBindDraftAgentToSessionId: (sid) => setSessionId(sid),
    onAwaitingHuman: (event) => setPendingHitl(event),
    onError: (msg) => showError({ summary: "Agent error", detail: msg }),
  };

  const { messages, waitResponse, send, sendHitlResume, reset } = useChatSse({
    agentInstanceId: agentInstanceId ?? "",
    teamId: teamId ?? "",
    ...sseCallbacks,
  });

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
    send(text, sessionId);
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
          onClick={() => {
            reset();
            setSessionId(null);
            setPendingHitl(null);
          }}
        >
          New conversation
        </Button>
      </header>

      <div className={styles.messages} role="log" aria-live="polite" aria-label="Conversation">
        {messages.length === 0 && !waitResponse && (
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
          disabled={waitResponse}
          rows={2}
          placeholder="Press Enter to send, Shift+Enter for newline"
        />
        <Button
          color="primary"
          variant="filled"
          size="medium"
          disabled={!input.trim() || waitResponse}
          onClick={handleSend}
        >
          Send
        </Button>
      </footer>
    </div>
  );
}
