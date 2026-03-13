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

import { Box, Grid } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import React, { memo, useMemo } from "react";
import { AnyAgent } from "../../common/agent";
import { AgentChipMini } from "../../common/AgentChip";
import DotsLoader from "../../common/DotsLoader";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";
import { AwaitingHumanEvent, ChatMessage } from "../../slices/agentic/agenticOpenApi";
import { getExtras, hasNonEmptyText } from "./ChatBotUtils";
import HitlInlineCard from "./HitlInlineCard";
import MessageCard from "./MessageCard";
import ReasoningStepsAccordion from "./ReasoningStepsAccordion";
import Sources from "./Sources";

type Props = {
  messages: ChatMessage[];
  agents: AnyAgent[];
  currentAgent: AnyAgent;
  isWaiting?: boolean;

  // id -> label maps
  libraryNameById?: Record<string, string>;
  chatContextNameById?: Record<string, string>;
  hiddenUserExchangeIds?: Set<string>;
  hitlEvent?: AwaitingHumanEvent | null;
  onHitlSubmit?: (choiceId?: string, freeText?: string) => void;
  onHitlCancel?: () => void;
};

function TypingIndicatorRow({ agent }: { agent: AnyAgent }) {
  const theme = useTheme();
  return (
    <Grid container marginBottom={1} sx={{ position: "relative" }}>
      <Grid size="auto" paddingTop={2}>
        <SimpleTooltip title={`${agent.id}: ${agent.tuning.role}`}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
            <AgentChipMini agent={agent} />
            <Box sx={{ display: "flex", alignItems: "center", transform: "translateY(1px) scale(0.9)" }}>
              <DotsLoader dotSize="4px" dotColor={theme.palette.text.secondary} />
            </Box>
          </Box>
        </SimpleTooltip>
      </Grid>
    </Grid>
  );
}

function Area({
  messages,
  agents,
  currentAgent,
  isWaiting = false,

  libraryNameById,
  chatContextNameById,
  hiddenUserExchangeIds,
  hitlEvent,
  onHitlSubmit,
  onHitlCancel,
}: Props) {
  // Hover highlight in Sources (syncs with [n] markers inside MessageCard)
  const [highlightUid, setHighlightUid] = React.useState<string | null>(null);

  const resolveAgent = (msg: ChatMessage): AnyAgent => {
    const agentName = msg.metadata?.agent_id ?? currentAgent.id;
    return agents.find((agent) => agent.id === agentName) ?? currentAgent;
  };

  const content = useMemo(() => {
    const sorted = [...messages].sort((a, b) => a.rank - b.rank);
    const activeExchangeKey =
      isWaiting && sorted.length
        ? `${sorted[sorted.length - 1].session_id}-${sorted[sorted.length - 1].exchange_id}`
        : null;

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
      const userMessages: ChatMessage[] = [];
      let keptSources: any[] | undefined;
      const groupKey = `${group[0].session_id}-${group[0].exchange_id}`;
      const isActiveExchange = !!activeExchangeKey && groupKey === activeExchangeKey;

      for (const msg of group) {
        if (msg.role === "user" && msg.channel === "final") {
          userMessages.push(msg);
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

      const visibleUserMessages = userMessages.filter((msg, idx) => {
        const hidePrimary = idx === 0 && hiddenUserExchangeIds?.has(msg.exchange_id);
        const hideInternalCapability = idx === 0 && typeof getExtras(msg)?.internal_capability === "string";
        return !hidePrimary && !hideInternalCapability;
      });
      const primaryUserVisible = visibleUserMessages[0];
      const renderPrimaryUserBeforeTrace = Boolean(primaryUserVisible) && userMessages[0] === primaryUserVisible;

      if (renderPrimaryUserBeforeTrace && primaryUserVisible) {
        elements.push(
          <MessageCard
            key={`user-${primaryUserVisible.session_id}-${primaryUserVisible.exchange_id}-${primaryUserVisible.rank}`}
            message={primaryUserVisible}
            agent={currentAgent}
            side="right"
            enableCopy
            enableThumbs
            pending={isActiveExchange && visibleUserMessages.length === 1}
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

      // ---------- dialogue messages after trace (chronological within exchange) ----------
      const trailingUserMessages = renderPrimaryUserBeforeTrace ? visibleUserMessages.slice(1) : visibleUserMessages;
      const timelineMessages = [...trailingUserMessages, ...others, ...finals].sort((a, b) => {
        if (a.rank !== b.rank) return a.rank - b.rank;
        return String(a.timestamp ?? "").localeCompare(String(b.timestamp ?? ""));
      });
      const lastVisibleUser = visibleUserMessages[visibleUserMessages.length - 1];

      for (const msg of timelineMessages) {
        const inlineSrc = msg.metadata?.sources as any[] | undefined;
        const isAssistantFinal = msg.role === "assistant" && msg.channel === "final";

        elements.push(
          <React.Fragment key={`timeline-${msg.session_id}-${msg.exchange_id}-${msg.rank}-${msg.role}-${msg.channel}`}>
            {isAssistantFinal && (keptSources ?? inlineSrc)?.length ? (
              <Sources
                key={`sources-final-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
                sources={(keptSources ?? inlineSrc) as any[]}
                enableSources
                expandSources={false}
                highlightUid={highlightUid ?? undefined}
              />
            ) : !isAssistantFinal && !keptSources && inlineSrc?.length ? (
              <Sources
                key={`sources-inline-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
                sources={inlineSrc as any[]}
                enableSources
                expandSources={false}
                highlightUid={highlightUid ?? undefined}
              />
            ) : null}

            <MessageCard
              key={`msg-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
              message={msg}
              agent={msg.role === "assistant" ? resolveAgent(msg) : currentAgent}
              side={msg.role === "user" ? "right" : "left"}
              enableCopy
              enableThumbs
              pending={
                msg.role === "user"
                  ? isActiveExchange && msg === lastVisibleUser
                  : isActiveExchange && isWaiting && msg.role === "assistant" && !hasNonEmptyText(msg)
              }
              suppressText={false}
              libraryNameById={libraryNameById}
              chatContextNameById={chatContextNameById}
              onCitationHover={(uid) => setHighlightUid(uid)}
              onCitationClick={(uid) => setHighlightUid(uid)}
            />
          </React.Fragment>,
        );
      }

      // Inline HITL card (awaiting human) for this exchange — render after the exchange messages
      if (hitlEvent && hitlEvent.session_id === group[0].session_id && hitlEvent.exchange_id === group[0].exchange_id) {
        elements.push(
          <HitlInlineCard key={`hitl-${groupKey}`} event={hitlEvent} onSubmit={onHitlSubmit} onCancel={onHitlCancel} />,
        );
      }

      // Typing indicator should sit after the latest content of the active exchange
      if (isActiveExchange && isWaiting) {
        const indicatorAgent = resolveAgent(userMessages[0] ?? group[group.length - 1]);
        elements.push(<TypingIndicatorRow key={`typing-${groupKey}`} agent={indicatorAgent} />);
      }
    }

    return elements;
  }, [
    messages,
    agents,
    currentAgent,
    highlightUid,
    libraryNameById,
    chatContextNameById,
    hiddenUserExchangeIds,
    isWaiting,
    hitlEvent,
    onHitlSubmit,
    onHitlCancel,
  ]);

  return (
    <div style={{ display: "flex", flexDirection: "column", flexGrow: 1, minHeight: 0 }}>
      {content}
      {isWaiting && messages.length === 0 && <TypingIndicatorRow agent={currentAgent} />}
      <div style={{ height: "1px", marginTop: "8px" }} />
    </div>
  );
}

export const MessagesArea = memo(Area);
