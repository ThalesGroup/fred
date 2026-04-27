// Copyright Thales 2026
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

// Temporary component — Phase 6A will replace this with UserMessage / AssistantMessage / AssistantTurn.

import type { ChatMessage } from "../../../../../slices/agentic/agenticOpenApi";
import styles from "./MessageBubble.module.css";

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

interface MessageBubbleProps {
  msg: ChatMessage;
}

export function MessageBubble({ msg }: MessageBubbleProps) {
  const text = textOf(msg);
  const isUser = msg.role === "user";
  const isDelta = (msg.metadata?.extras as { streaming_delta?: boolean } | undefined)?.streaming_delta === true;

  if (!text && msg.channel !== "tool_call" && msg.channel !== "tool_result") return null;

  return (
    <div className={`${styles.bubble} ${isUser ? styles.user : styles.agent}`} aria-label={`${roleLabel(msg)} message`}>
      <span className={styles.role}>{roleLabel(msg)}</span>
      {msg.channel === "tool_call" || msg.channel === "tool_result" ? (
        <span className={styles.tool}>
          {msg.channel === "tool_call" ? "⚙ Tool call" : "✓ Tool result"}
          {text ? `: ${text}` : ""}
        </span>
      ) : (
        <p className={`${styles.text} ${isDelta ? styles.streaming : ""}`}>{text}</p>
      )}
    </div>
  );
}
