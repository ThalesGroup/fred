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

import React, { memo, useEffect, useRef, useState } from "react";
import Message from "./MessageCard.tsx";
import Thoughts from "./Thoughts.tsx";
import { AgenticFlow } from "../../pages/Chat.tsx";
import Sources from "./Sources.tsx";
import { ChatMessagePayload, FredMetadata } from "../../slices/chatApiStructures.ts";

function Area({
  messages,
  agenticFlows,
  currentAgenticFlow,
}: {
  messages: ChatMessagePayload[];
  agenticFlows: AgenticFlow[];
  currentAgenticFlow: AgenticFlow;
}) {
  // Reference for the message container
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const [events, setEvents] = useState<React.ReactNode[]>([]);

  // Function to scroll to the bottom of the messages
  //TODO - Fix the timeout issue
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 300); // Adjust the timeout as needed
    }
  };

  // Automatically scroll to the bottom when messages update
  useEffect(() => {
    const sorted = [...messages].sort((a, b) => a.rank - b.rank);
    const grouped = new Map<string, ChatMessagePayload[]>();

    for (const msg of sorted) {
      const key = `${msg.session_id}-${msg.exchange_id}`;
      if (!grouped.has(key)) {
        grouped.set(key, []);
      }
      grouped.get(key)!.push(msg);
    }

    const elements: React.ReactNode[] = [];

    for (const [, group] of grouped.entries()) {
      const thoughtsByTask: Record<string, ChatMessagePayload[]> = {};
      let userMessage: ChatMessagePayload | undefined;
      let finalMessages: ChatMessagePayload[] = [];
      let otherMessages: ChatMessagePayload[] = [];

      for (const msg of group) {
        const { session_id, exchange_id, rank, type, subtype, sender, content } = msg;
        const task = (msg.metadata?.fred as FredMetadata)?.task || "Task";

        console.groupCollapsed(
          `%c📦 Message %s | %s-%s | rank=%d | subtype=%s | task=%s`,
          "color: gray",
          session_id,
          exchange_id,
          type,
          rank,
          subtype || "–",
          task,
        );
        console.log("Sender:", sender);
        console.log("Content preview:", content?.slice(0, 120));
        console.log("Metadata:", msg.metadata);
        console.groupEnd();

        if (type === "human") {
          console.log("👉 Classified as: USER");
          userMessage = msg;
        } else if (["plan", "execution", "thought", "tool_result"].includes(subtype || "")) {
          if (!thoughtsByTask[task]) thoughtsByTask[task] = [];
          thoughtsByTask[task].push(msg);
          console.log("🧠 Classified as: THOUGHT under task:", task);
        } else if (subtype === "final") {
          if (msg.metadata?.fred?.task) {
            // Intermediate result for a task — belongs inside the Thoughts block
            if (!thoughtsByTask[task]) thoughtsByTask[task] = [];
            thoughtsByTask[task].push(msg);
            console.log("🧠 Classified as: INTERMEDIATE FINAL in task:", task);
          } else {
            // Only top-level final message goes as standalone
            finalMessages.push(msg);
            console.log("✅ Classified as: FINAL RESPONSE");
          }
        } else {
          otherMessages.push(msg);
          console.warn("⚠️ Classified as: OTHER (fallback)");
        }
      }

      if (userMessage) {
        elements.push(
          <Message
            key={`msg-${userMessage.session_id}-${userMessage.exchange_id}-${userMessage.rank}`}
            message={userMessage}
            currentAgenticFlow={currentAgenticFlow}
            agenticFlow={currentAgenticFlow}
            side="right"
            enableCopy
            enableThumbs
            enableAudio
          />,
        );
      }

      if (Object.keys(thoughtsByTask).length > 0) {
        elements.push(
          <Thoughts
            key={`thoughts-${group[0].exchange_id}`}
            messages={thoughtsByTask}
            expandThoughts={true}
            enableThoughts={true}
          />,
        );
      }
      for (const msg of otherMessages) {
        const agenticFlow = agenticFlows.find((flow) => flow.name === msg.metadata?.agentic_flow);
        const sources = msg.metadata?.sources;
        elements.push(
          <React.Fragment key={`msg-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}>
            {sources && <Sources sources={sources} enableSources={true} expandSources={false} />}
            <Message
              message={msg}
              agenticFlow={agenticFlow}
              currentAgenticFlow={currentAgenticFlow}
              side={msg.sender === "user" ? "right" : "left"}
              enableCopy
              enableThumbs
              enableAudio
            />
          </React.Fragment>,
        );
      }

      for (const msg of finalMessages) {
        const agenticFlow = agenticFlows.find((flow) => flow.name === msg.metadata?.agentic_flow);
        const sources = msg.metadata?.sources;
        elements.push(
          <React.Fragment key={`final-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}>
            {sources && <Sources sources={sources} enableSources={true} expandSources={true} />}
            <Message
              message={msg}
              agenticFlow={agenticFlow}
              currentAgenticFlow={currentAgenticFlow}
              side="left"
              enableCopy
              enableThumbs
              enableAudio
            />
          </React.Fragment>,
        );
      }
    }

    setEvents(elements);
  }, [messages]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <div>
      {events}
      <div ref={messagesEndRef} />
      {/* Debug output: display the raw messages JSON */}
      {/*  <pre>{JSON.stringify(messages, null, 2)}</pre> */}
    </div>
  );
}

/*
  ────────────────────────────────────────────────────────────────────────
  🧠 Message Grouping Logic (for Thoughts, Plans, Tool Results, etc.)
  ────────────────────────────────────────────────────────────────────────

  This section transforms the flat list of ChatMessagePayloads into a mix of:

    1. Individual messages — like user inputs and final assistant responses
    2. Grouped messages — sequences of related assistant thoughts, plans, tool outputs,
       etc., grouped by `fred.task` and rendered together using the <Thoughts> component

  Each "group" is represented in this format:
      {
        "Analyze Data": [
          { subtype: "plan", content: "1. Parse CSV\n2. Summarize values" },
          { subtype: "execution", content: "Parsing CSV complete" },
          { subtype: "tool_result", content: "Found 4 columns, 200 rows" }
        ]
      }

  These grouped entries are pushed into the `elements[]` array and detected by checking
  if the object does **not** have a `.type` field (i.e., it's not a regular message).
  We render them using <Thoughts messages={...} />.

  The grouping rules are based on the `subtype` field of each message:
    - "plan" starts a group if following a user message
    - "thought", "execution", "tool_result" are added to the current group if it's open
    - Otherwise, they start a new group under their task
    - All other messages are treated as individual and rendered with <Message />

  This design allows the UI to cleanly separate final answers from intermediate reasoning.

*/
export const MessagesArea = memo(Area);
