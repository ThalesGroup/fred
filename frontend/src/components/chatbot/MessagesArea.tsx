import React, { memo, useMemo, useRef, useEffect } from "react";
import MessageCard from "./MessageCard";
import Sources from "./Sources";
import { AgenticFlow, ChatMessage } from "../../slices/agentic/agenticOpenApi";
import { getExtras, hasNonEmptyText } from "./ChatBotUtils";
import ReasoningStepsAccordion from "./ReasoningStepsAccordion";
import { buildCitationMap, renderTextWithCitations } from "./citations";

type Props = {
  messages: ChatMessage[];
  agenticFlows: AgenticFlow[];
  currentAgenticFlow: AgenticFlow;
};

function Area({ messages, agenticFlows, currentAgenticFlow }: Props) {
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  // Hover highlight + click-to-open
  const [highlightUid, setHighlightUid] = React.useState<string | null>(null);

  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 300);
    }
  };

  const resolveAgenticFlow = (msg: ChatMessage): AgenticFlow => {
    const agentName = msg.metadata?.agent_name ?? currentAgenticFlow.name;
    return agenticFlows.find((flow) => flow.name === agentName) ?? currentAgenticFlow;
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
            currentAgenticFlow={currentAgenticFlow}
            agenticFlow={currentAgenticFlow}
            side="right"
            enableCopy
            enableThumbs
            enableAudio
          />,
        );
      }

      if (reasoningSteps.length) {
        elements.push(
          <ReasoningStepsAccordion
            key={`trace-${group[0].session_id}-${group[0].exchange_id}`}
            steps={reasoningSteps}
            isOpenByDefault
            resolveAgent={resolveAgenticFlow}
          />,
        );
      }

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
        const agenticFlow = resolveAgenticFlow(msg);
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

      // ---------- final assistant message ----------
      for (const msg of finals) {
        const agenticFlow = resolveAgenticFlow(msg);
        const finalSources = keptSources ?? (msg.metadata?.sources as any[] | undefined);

        // 1) Sources first (expanded)
        if (finalSources?.length) {
          elements.push(
            <Sources
              key={`sources-final-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
              sources={finalSources}
              enableSources
              expandSources
              highlightUid={highlightUid ?? undefined}
            />,
          );
        }

        // 2) Inline text with hoverable & clickable [n] markers
        const textParts = (msg.parts || []).filter((p: any) => p?.type === "text");
        if (textParts.length) {
          const citeMap = buildCitationMap(msg);
          elements.push(
            <div
              key={`final-inline-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
              style={{ padding: "8px 12px", margin: "4px 0", whiteSpace: "pre-wrap" }}
            >
              {textParts.map((p: any, i: number) => (
                <div key={i}>
                  {renderTextWithCitations(
                    p.text || "",
                    citeMap,
                    // hover
                    (uid) => setHighlightUid(uid),
                    // metaMap is optional (tooltips already improved in MessageCard path)
                    undefined,
                  )}
                </div>
              ))}
            </div>,
          );
        }

        // 3) Render non-text parts only
        elements.push(
          <MessageCard
            key={`final-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
            message={msg}
            agenticFlow={agenticFlow}
            currentAgenticFlow={currentAgenticFlow}
            side="left"
            enableCopy
            enableThumbs
            enableAudio
            suppressText
          />,
        );
      }
    }

    return elements;
  }, [messages, agenticFlows, currentAgenticFlow, highlightUid]); // include states as deps

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <div style={{ display: "flex", flexDirection: "column", flexGrow: 1 }}>
      {content}
      <div ref={messagesEndRef} style={{ height: "1px", marginTop: "8px" }} />
    </div>
  );
}

export const MessagesArea = memo(Area);
