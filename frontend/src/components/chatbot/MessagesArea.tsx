// MessagesArea.tsx
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

import React, { memo, useMemo } from "react";
import { AnyAgent } from "../../common/agent";
import { ChatMessage } from "../../slices/agentic/agenticOpenApi";
import { getExtras, hasNonEmptyText } from "./ChatBotUtils";
import MessageCard from "./MessageCard";
import ReasoningStepsAccordion from "./ReasoningStepsAccordion";
import Sources from "./Sources";

type Props = {
  messages: ChatMessage[];
  agents: AnyAgent[];
  currentAgent: AnyAgent;

  // id -> label maps
  libraryNameById?: Record<string, string>;
  chatContextNameById?: Record<string, string>;
};

function Area({
  messages,
  agents,
  currentAgent,

  libraryNameById,
  chatContextNameById,
}: Props) {
  // Hover highlight in Sources (syncs with [n] markers inside MessageCard)
  const [highlightUid, setHighlightUid] = React.useState<string | null>(null);

  const resolveAgent = (msg: ChatMessage): AnyAgent => {
    const agentName = msg.metadata?.agent_name ?? currentAgent.name;
    return agents.find((agent) => agent.name === agentName) ?? currentAgent;
  };

  const content = useMemo(() => {
    const sorted = [...messages].sort((a, b) => a.rank - b.rank);

    const grouped = new Map<string, ChatMessage[]>();
    for (const msg of sorted) {
      const key = `${msg.session_id}-${msg.exchange_id}`;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(msg);
    }

    const elements: React.ReactNode[] = [];

    for (const [, group] of grouped.entries()) {
      const reasoningSteps: ChatMessage[] = [];
      const finals: ChatMessage[] = [];
      const others: ChatMessage[] = [];
      let userMessage: ChatMessage | undefined;
      let keptSources: any[] | undefined;

      for (const msg of group) {
        if (msg.role === "user" && msg.channel === "final") {
          userMessage = msg;
          continue;
        }

        // Skip empty intermediary observations unless they carry sources
        if (
          msg.channel === "observation" &&
          !hasNonEmptyText(msg) &&
          !(msg.metadata?.sources && (msg.metadata.sources as any[])?.length)
        ) {
          continue;
        }

        const extras = getExtras(msg);
        if (
          extras?.node === "grade_documents" &&
          Array.isArray(msg.metadata?.sources) &&
          msg.metadata!.sources!.length
        ) {
          keptSources = msg.metadata!.sources as any[];
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
          continue;
        }

        if (msg.role === "assistant" && msg.channel === "final") {
          finals.push(msg);
          continue;
        }

        others.push(msg);
      }

      if (userMessage) {
        elements.push(
          <MessageCard
            key={`user-${userMessage.session_id}-${userMessage.exchange_id}-${userMessage.rank}`}
            message={userMessage}
            agent={currentAgent}
            side="right"
            enableCopy
            enableThumbs
            suppressText={false}
            libraryNameById={libraryNameById}
            chatContextNameById={chatContextNameById}
            onCitationHover={(uid) => setHighlightUid(uid)}
            onCitationClick={(uid) => setHighlightUid(uid)}
          />,
        );
      }

      if (reasoningSteps.length) {
        elements.push(
          <ReasoningStepsAccordion
            key={`trace-${group[0].session_id}-${group[0].exchange_id}`}
            steps={reasoningSteps}
            isOpenByDefault
            resolveAgent={resolveAgent}
          />,
        );
      }

      // If we already have a curated set and there is no final yet, show it early
      if (keptSources?.length && finals.length === 0) {
        elements.push(
          <Sources
            key={`sources-${group[0].session_id}-${group[0].exchange_id}`}
            sources={keptSources}
            enableSources
            expandSources={false}
            highlightUid={highlightUid ?? undefined}
          />,
        );
      }

      // ---------- intermediary assistant/user messages ----------
      for (const msg of others) {
        // const agenticFlow = resolveAgent(msg);
        const inlineSrc = msg.metadata?.sources;

        elements.push(
          <React.Fragment key={`other-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}>
            {!keptSources && inlineSrc?.length && (
              <Sources
                sources={inlineSrc as any[]}
                enableSources
                expandSources={false}
                highlightUid={highlightUid ?? undefined}
              />
            )}

            <MessageCard
              key={`final-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
              message={msg}
              agent={currentAgent}
              side={msg.role === "user" ? "right" : "left"}
              enableCopy
              enableThumbs
              suppressText={false}
              libraryNameById={libraryNameById}
              chatContextNameById={chatContextNameById}
              onCitationHover={(uid) => setHighlightUid(uid)}
              onCitationClick={(uid) => setHighlightUid(uid)}
            />
          </React.Fragment>,
        );
      }

      // ---------- final assistant message ----------
      for (const msg of finals) {
        // const agenticFlow = resolveAgent(msg);
        const finalSources = keptSources ?? (msg.metadata?.sources as any[] | undefined);

        // 1) Sources first (expanded)
        if (finalSources?.length) {
          elements.push(
            <Sources
              key={`sources-final-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
              sources={finalSources}
              enableSources
              expandSources={false}
              highlightUid={highlightUid ?? undefined}
            />,
          );
        }
        const agent = resolveAgent(msg);
        // 2) Single MessageCard (always markdown, inline [n] handled inside)

        // 2) Final message card
        elements.push(
          <MessageCard
            key={`final-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
            message={msg}
            agent={agent}
            side="left"
            enableCopy
            enableThumbs
            suppressText={false}
            libraryNameById={libraryNameById}
            chatContextNameById={chatContextNameById}
            onCitationHover={(uid) => setHighlightUid(uid)}
            onCitationClick={(uid) => setHighlightUid(uid)}
          />,
        );
      }
    }

    return elements;
  }, [messages, agents, currentAgent, highlightUid, libraryNameById, chatContextNameById]);

  return (
    <div style={{ display: "flex", flexDirection: "column", flexGrow: 1, minHeight: 0 }}>
      {content}
      <div style={{ height: "1px", marginTop: "8px" }} />
    </div>
  );
}

export const MessagesArea = memo(Area);
