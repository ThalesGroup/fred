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

        for (const message of messages) {
            if (!message.content) continue
            const last = elements.length > 0 ? elements[elements.length - 1] : null
            const lastType = last && "type" in last ? last.type : "thoughts"
            const isThought = message.metadata?.thought
            const isTool = message.type === "tool"
            const fred = message.metadata?.fred as FredMetadata | undefined;

            if (isThought && fred?.node === "plan" && lastType === "human") {
                elements.push({ [fred.task]: [message] });
            } else if (isThought && lastType === "thoughts") {
                const task = fred?.task;
                if (task && last && typeof last === "object" && !(last as ChatMessagePayload).type) {
                    if (last[task]) last[task].push(message);
                    else last[task] = [message];
                }
            } else if (isTool && lastType === "thoughts") {
                const task = fred?.task;
                if (task && last && typeof last === "object" && !("type" in last)) {
                    const lastMap = last as Record<string, ChatMessagePayload[]>;
                    if (lastMap[task]) {
                        lastMap[task].push(message);
                    } else {
                        lastMap[task] = [message];
                    }
                }
            } else if (isTool) {
                const task = (message.metadata?.task || message.metadata?.name || "ToolTask") as string;
                elements.push({ [task]: [message] });
            } else {
                elements.push(message);
            }
        }
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

export const MessagesArea = memo(Area);