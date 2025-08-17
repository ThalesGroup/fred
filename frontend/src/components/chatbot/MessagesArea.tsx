// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

import React, { memo, useEffect, useRef, useState } from "react";
import Message from "./MessageCard.tsx";
import Thoughts from "./Thoughts.tsx";
import Sources from "./Sources.tsx";
import { AgenticFlow } from "../../pages/Chat.tsx";
import { ChatMessagePayload } from "../../slices/agentic/agenticOpenApi.ts";

type Props = {
  messages: ChatMessagePayload[];
  agenticFlows: AgenticFlow[];
  currentAgenticFlow: AgenticFlow;
};

function Area({ messages, agenticFlows, currentAgenticFlow }: Props) {
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const [events, setEvents] = useState<React.ReactNode[]>([]);

  // Add a helper to find the scrollable container (the parent Grid2 with overflowY: "scroll")
function getScrollableParent(el: HTMLElement | null): HTMLElement | null {
  let node: HTMLElement | null = el;
  while (node) {
    const style = window.getComputedStyle(node);
    const oy = style.overflowY;
    if (oy === "auto" || oy === "scroll") return node;
    node = node.parentElement;
  }
  return null;
}

function isNearBottom(container: HTMLElement, threshold = 96): boolean {
  const { scrollTop, scrollHeight, clientHeight } = container;
  return scrollHeight - (scrollTop + clientHeight) <= threshold;
}

const scrollToBottomIfSticking = () => {
  if (!messagesEndRef.current) return;
  const scrollable = getScrollableParent(messagesEndRef.current);
  if (!scrollable) return;

  if (isNearBottom(scrollable)) {
    // Only auto-scroll if the user is already near the bottom
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }, 50);
  }
};


  // Helper: resolve agentic flow for a message using new schema
  const resolveAgenticFlow = (msg: ChatMessagePayload): AgenticFlow => {
    const agentName = msg.metadata?.agent_name ?? currentAgenticFlow.name;
    return agenticFlows.find((flow) => flow.name === agentName) ?? currentAgenticFlow;
  };

  // Helper: resolve task name from new schema
  const getTaskName = (msg: ChatMessagePayload): string => {
    // new schema: metadata.fred?.task (kept generic on backend)
    const task = (msg.metadata?.fred as Record<string, any> | undefined)?.task;
    if (typeof task === "string" && task.trim().length > 0) return task.trim();
    return "Task";
  };

  useEffect(() => {
    // We expect messages already sorted by `rank` from ChatBot; still sort defensively
    const sorted = [...messages].sort((a, b) => a.rank - b.rank);

    // Group by (session_id, exchange_id)
    const grouped = new Map<string, ChatMessagePayload[]>();
    for (const msg of sorted) {
      const key = `${msg.session_id}-${msg.exchange_id}`;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(msg);
    }

    const elements: React.ReactNode[] = [];

    for (const [, group] of grouped.entries()) {
      const thoughtsByTask: Record<string, ChatMessagePayload[]> = {};
      let userMessage: ChatMessagePayload | undefined;
      const finalMessages: ChatMessagePayload[] = [];
      const otherMessages: ChatMessagePayload[] = [];

      for (const msg of group) {
        const { type, subtype } = msg;

        if (type === "human") {
          userMessage = msg;
          continue;
        }

        if (subtype === "injected_context") {
          // hide backend-injected context from the main flow
          continue;
        }

        // Intermediate messages: plan / execution / thought / tool_result (and "final" with a task)
        const isThoughty =
          subtype === "plan" ||
          subtype === "execution" ||
          subtype === "thought" ||
          subtype === "tool_result";

        if (isThoughty) {
          const task = getTaskName(msg);
          if (!thoughtsByTask[task]) thoughtsByTask[task] = [];
          thoughtsByTask[task].push(msg);
          continue;
        }

        if (subtype === "final") {
          const hasTask = Boolean((msg.metadata?.fred as Record<string, any> | undefined)?.task);
          if (hasTask) {
            // treat task-scoped final as part of thoughts accordion
            const task = getTaskName(msg);
            if (!thoughtsByTask[task]) thoughtsByTask[task] = [];
            thoughtsByTask[task].push(msg);
          } else {
            // top-level final → standalone answer card
            finalMessages.push(msg);
          }
          continue;
        }

        // Fallback bucket (rare)
        otherMessages.push(msg);
      }

      // Render user message (right side)
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

      // Render grouped thoughts (accordion), if any
      if (Object.keys(thoughtsByTask).length > 0) {
        elements.push(
          <Thoughts
            key={`thoughts-${group[0].session_id}-${group[0].exchange_id}`}
            messages={thoughtsByTask}
            isOpenByDefault={true}
          />,
        );
      }

      // Render any "other" messages (rare fallback)
      for (const msg of otherMessages) {
        const agenticFlow = resolveAgenticFlow(msg);
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

      // Render top-level finals (left side, sources expanded)
      for (const msg of finalMessages) {
        const agenticFlow = resolveAgenticFlow(msg);
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
  }, [messages, agenticFlows, currentAgenticFlow]);

  useEffect(() => {
    scrollToBottomIfSticking();
  }, [messages]);

  return (
    <div>
      {events}
      <div ref={messagesEndRef} />
    </div>
  );
}

export const MessagesArea = memo(Area);
