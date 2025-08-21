import React, { memo, useMemo, useRef, useEffect } from "react";
import Message from "./MessageCard";
import Sources from "./Sources";
import { AgenticFlow, ChatMessage } from "../../slices/agentic/agenticOpenApi";
import { getExtras, hasNonEmptyText } from "./ChatBotUtils";
import ReasoningStepsAccordion from "./ReasoningStepsAccordion";

type Props = {
  messages: ChatMessage[];
  agenticFlows: AgenticFlow[];
  currentAgenticFlow: AgenticFlow;
};

function Area({ messages, agenticFlows, currentAgenticFlow }: Props) {
  // ⬇️ Old-pattern: bottom anchor we scroll into view after render
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = () => {
        if (messagesEndRef.current) {
            setTimeout(() => {
                messagesEndRef.current?.scrollIntoView({behavior: 'smooth'});
            }, 300); // Adjust the timeout as needed
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
        if (extras?.node === "grade_documents" && Array.isArray(msg.metadata?.sources) && msg.metadata!.sources!.length) {
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
          />,
        );
      }

      for (const msg of others) {
        const agenticFlow = resolveAgenticFlow(msg);
        const inlineSrc = msg.metadata?.sources;
        elements.push(
          <React.Fragment key={`other-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}>
            {!keptSources && inlineSrc?.length && (
              <Sources sources={inlineSrc as any[]} enableSources expandSources={false} />
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

      for (const msg of finals) {
        const agenticFlow = resolveAgenticFlow(msg);
        const finalSources = keptSources ?? (msg.metadata?.sources as any[] | undefined);

        if (finalSources?.length) {
          elements.push(
            <Sources
              key={`sources-final-${msg.session_id}-${msg.exchange_id}-${msg.rank}`}
              sources={finalSources}
              enableSources
              expandSources
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

  // Always scroll to bottom when content changes (new msg or loaded history)
  useEffect(() => {
        scrollToBottom();
    }, [messages]);

  // Container + bottom anchor—no extra styling required here;
  return (
    <div style={{ display: "flex", flexDirection: "column", flexGrow: 1 }}>
      {content}
      <div ref={messagesEndRef} style={{ height: '1px', marginTop: '8px' }} />
    </div>
  );
}

export const MessagesArea = memo(Area);
