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

import React, { memo, useEffect, useRef, useState } from 'react';
import Message from "./MessageCard.tsx";
import Thoughts from "./Thoughts.tsx";
import { AgenticFlow } from "../../pages/Chat.tsx";
import Sources from "./Sources.tsx";
import { ChatMessagePayload, FredMetadata } from '../../slices/chatApiStructures.ts';

function Area(
    {
        messages,
        agenticFlows,
    }: {
        messages: ChatMessagePayload[],
        agenticFlows: AgenticFlow[]

    }) {

    // Reference for the message container
    const messagesEndRef = useRef<HTMLDivElement | null>(null);

    const [events, setEvents] = useState<React.ReactNode[]>([]);

    // Function to scroll to the bottom of the messages
    //TODO - Fix the timeout issue
    const scrollToBottom = () => {
        if (messagesEndRef.current) {
            setTimeout(() => {
                messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            }, 300); // Adjust the timeout as needed
        }
    };

    // Automatically scroll to the bottom when messages update
    useEffect(() => {
        const elements: (Record<string, ChatMessagePayload[]> | ChatMessagePayload)[] = []

        messages.forEach((message, index) => {
            // Skip messages with no content
            if (!message.content) return

            // Get the last element added to the render queue
            const last = elements.length > 0 ? elements[elements.length - 1] : null

            // Determine the type of the last element to understand grouping context
            // If it has a `type` field, it's a single message (not a grouped task/thought)
            // If not, it's a thoughts group (like { taskName: [messages] })
            const lastType = last && "type" in last ? last.type : "thoughts"

            // Extract the message's semantic subtype and agentic task metadata
            const subtype = message.subtype;
            const fred = message.metadata?.fred as FredMetadata | undefined;

            // 🧠 Start a new group of thoughts for a specific task
            // Only when the current message is a plan and follows a user message
            if (subtype === "plan" && lastType === "human") {
                elements.push({ [fred?.task || "Plan"]: [message] });

                // 🧠🛠️ Append to the current group of thoughts/tool results if already in a group
            } else if (["thought", "execution", "tool_result"].includes(subtype || "") && lastType === "thoughts") {
                const task = fred?.task || "Task";
                if (last && typeof last === "object" && !("type" in last)) {
                    if (last[task]) last[task].push(message);
                    else last[task] = [message];
                }
                // 🧠🛠️ Start a new group if no existing group is open
            } else if (["thought", "execution", "tool_result"].includes(subtype || "")) {
                const task = fred?.task || "Task";
                elements.push({ [task]: [message] });
                // 💬 Fallback: treat as a standalone message (user or assistant final answer)
            } else if (subtype === "final" && index === messages.length - 1) {
                // ✅ Show only the very last final message in the main chat view
                elements.push(message);
            } else if (!["plan", "execution", "thought", "tool_result", "final"].includes(subtype || "")) {
                // ✅ Show human or simple assistant/system messages
                elements.push(message);
            } else {
                // ❌ Ignore intermediate final messages from earlier steps
                // (they are captured in grouped thoughts)
            }
        })


        const rendered = elements.map((el, index) => {
            if (!("type" in el)) {
                return (
                    <Thoughts
                        key={`thoughts-${index}`}
                        messages={el}
                        expandThoughts={index === elements.length - 1}
                        enableThoughts={true}
                    />
                );
            }
            const message = el as ChatMessagePayload;
            const agenticFlow = agenticFlows.find(flow => flow.name === message.metadata?.agentic_flow);
            const sources = message.metadata?.sources;

            return (
                <React.Fragment
                    key={`message-${el.id}-${message.metadata?.partial ? 'stream' : 'final'}`}>
                    {sources && (
                        <Sources
                            sources={sources}
                            enableSources={true}
                            expandSources={index === elements.length - 1}
                        />
                    )}
                    <Message
                        message={message}
                        agenticFlow={agenticFlow}
                        side={el.sender === "user" ? "right" : "left"}
                        enableCopy={true}
                        enableThumbs={true}
                        enableAudio={true}
                    />
                </React.Fragment>
            );
        });
        setEvents(rendered);
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