// Copyright Thales 2025
// Licensed under the Apache License, Version 2.0

import React, { memo, useEffect, useMemo, useRef } from "react";
import Message from "./MessageCard";
import ReasoningTrace from "./ReasoningTrace";
import Sources from "./Sources";
import { AgenticFlow, ChatMessage } from "../../slices/agentic/agenticOpenApi";
import { getExtras, hasNonEmptyText, isToolCall, isToolResult, toolId } from "./ChatBotUtils";

type Props = {
  messages: ChatMessage[];
  agenticFlows: AgenticFlow[];
  currentAgenticFlow: AgenticFlow;
};

function Area({ messages, agenticFlows, currentAgenticFlow }: Props) {
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Find the scrollable container (parent Grid2 with overflowY: "scroll")
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
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
      }, 50);
    }
  };

  const resolveAgenticFlow = (msg: ChatMessage): AgenticFlow => {
    const agentName = msg.metadata?.agent_name ?? currentAgenticFlow.name;
    return agenticFlows.find((flow) => flow.name === agentName) ?? currentAgenticFlow;
  };

  const content = useMemo(() => {
    // 1) stable order (you already sorted by rank; keep it)
    const sorted = [...messages].sort((a, b) => a.rank - b.rank);

    // 2) group by (session_id, exchange_id)
    const grouped = new Map<string, ChatMessage[]>();
    for (const msg of sorted) {
      const key = `${msg.session_id}-${msg.exchange_id}`;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(msg);
    }

    const elements: React.ReactNode[] = [];

    for (const [, group] of grouped.entries()) {
      // Per-exchange working state
      const toolPairs: Record<string, { call?: ChatMessage; result?: ChatMessage }> = {};
      const reasoningSteps: ChatMessage[] = [];
      const finals: ChatMessage[] = [];
      const others: ChatMessage[] = [];

      let userMessage: ChatMessage | undefined;
      let keptSources: any[] | undefined; // authoritative list from grade_documents

      // 3) first pass: collect, pair, and detect kept sources
      for (const msg of group) {
        // (a) user bubble
        if (msg.role === "user" && msg.channel === "final") {
          userMessage = msg;
          continue;
        }

        // (b) skip blank observations (no text AND no sources)
        if (
          msg.channel === "observation" &&
          !hasNonEmptyText(msg) &&
          !(msg.metadata?.sources && (msg.metadata.sources as any[])?.length)
        ) {
          continue;
        }

        // (c) kept sources from grading (authoritative)
        const extras = getExtras(msg);
        if (
          extras?.node === "grade_documents" &&
          Array.isArray(msg.metadata?.sources) &&
          msg.metadata!.sources!.length
        ) {
          keptSources = msg.metadata!.sources as any[];
        }

        // (d) tool pairing
        if (isToolCall(msg)) {
          const id = toolId(msg);
          if (id) toolPairs[id] = { ...(toolPairs[id] || {}), call: msg };
        }
        if (isToolResult(msg)) {
          const id = toolId(msg);
          if (id) toolPairs[id] = { ...(toolPairs[id] || {}), result: msg };
        }

        const TRACE_CHANNELS = [
          "plan",
          "thought",
          "observation",
          "tool_call",
          "tool_result",
          "system_note",
          "error",
        ] as const;
        if (TRACE_CHANNELS.includes(msg.channel as any)) {
          reasoningSteps.push(msg);
          continue; // prevent them entering "others"
        }

        // (f) finals
        if (msg.role === "assistant" && msg.channel === "final") {
          finals.push(msg);
          continue;
        }

        // (g) everything else
        others.push(msg);
      }

      // 4) render user bubble (right)
      if (userMessage) {
        elements.push(
          <Message
            key={`user-${userMessage.session_id}-${userMessage.exchange_id}-${userMessage.rank}`}
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

      // 5) Reasoning accordion (grouped by task label if you like; here we just pass flat list)
      if (reasoningSteps.length) {
        elements.push(
          <ReasoningTrace
            key={`trace-${group[0].session_id}-${group[0].exchange_id}`}
            messages={reasoningSteps} // ✅ pass the flat array
            isOpenByDefault
            resolveAgent={resolveAgenticFlow}
            // includeObservationsWithText           // optional toggle
          />,
        );
      }

      // 6) Tool call/result cards (in order of first appearance), live while waiting for result

      // 7) Live sources panel: show as soon as keptSources exists (even before final)
      if (keptSources?.length && finals.length === 0) {
  elements.push(
    <Sources
      key={`sources-${group[0].session_id}-${group[0].exchange_id}`}
      sources={keptSources}
      enableSources={true}
      expandSources={false}
    />,
  );
}

      // 8) Other messages that slipped through (rare)
      for (const msg of others) {
        const agenticFlow = resolveAgenticFlow(msg);
        const inlineSrc = msg.metadata?.sources;
        elements.push(
          <React.Fragment key={`other-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}>
            {!keptSources && inlineSrc?.length && (
              <Sources sources={inlineSrc as any[]} enableSources={true} expandSources={false} />
            )}
            <Message
              message={msg}
              agenticFlow={agenticFlow}
              currentAgenticFlow={currentAgenticFlow}
              side={msg.role === "user" ? "right" : "left"}
              enableCopy
              enableThumbs
              enableAudio
            />
          </React.Fragment>,
        );
      }

      // 9) Finals: prefer the keptSources; otherwise use final.metadata.sources
      for (const msg of finals) {
        const agenticFlow = resolveAgenticFlow(msg);
        const finalSources = keptSources ?? (msg.metadata?.sources as any[] | undefined);

        if (finalSources?.length) {
          elements.push(
            <Sources
              key={`sources-final-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
              sources={finalSources}
              enableSources={true}
              expandSources={true}
            />,
          );
        }

        elements.push(
          <Message
            key={`final-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
            message={msg}
            agenticFlow={agenticFlow}
            currentAgenticFlow={currentAgenticFlow}
            side="left"
            enableCopy
            enableThumbs
            enableAudio
          />,
        );
      }
    }

    return elements;
  }, [messages, agenticFlows, currentAgenticFlow]);

  useEffect(() => {
    scrollToBottomIfSticking();
  }, [messages]);

  return (
    <div>
      {content}
      <div ref={messagesEndRef} />
    </div>
  );
}

export const MessagesArea = memo(Area);
