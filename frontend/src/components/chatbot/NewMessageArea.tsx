import React, { memo, useRef, useEffect, useState } from "react";
import MessageCard from "./MessageCard";
import Sources from "./Sources";
import { AgenticFlow, ChatMessage } from "../../slices/agentic/agenticOpenApi";
import ReasoningStepsAccordion from "./ReasoningStepsAccordion";
import { useGroupedMessages } from "../../hooks/useGroupMessages";

type Props = {
  messages: ChatMessage[];
  agenticFlows: AgenticFlow[];
  currentAgenticFlow: AgenticFlow;
};

function Area({ messages, agenticFlows, currentAgenticFlow }: Props) {
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const [highlightUid, setHighlightUid] = useState<string | null>(null);

  // Use the new hook to get a pre-processed data structure
  const exchanges = useGroupedMessages(messages);

  const resolveAgenticFlow = (msg: ChatMessage): AgenticFlow => {
    const agentName = msg.metadata?.agent_name ?? currentAgenticFlow.name;
    return agenticFlows.find((flow) => flow.name === agentName) ?? currentAgenticFlow;
  };

  // The scroll-to-bottom logic remains here as it's a UI concern
  useEffect(() => {
    if (messagesEndRef.current) {
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      }, 300);
    }
  }, [messages]); // Trigger on message change

  // Now, we simply render based on the structured data from the hook
  const renderContent = () => {
    return exchanges.map((exchange, index) => (
      <React.Fragment key={`exchange-${index}`}>
        {/* User bubble */}
        {exchange.userMessage && (
          <MessageCard
            message={exchange.userMessage}
            currentAgenticFlow={currentAgenticFlow}
            agenticFlow={currentAgenticFlow}
            side="right"
            enableCopy
            enableThumbs
            enableAudio
          />
        )}

        {/* Reasoning steps accordion */}
        {exchange.reasoningSteps.length > 0 && (
          <ReasoningStepsAccordion
            key={`trace-${index}`}
            steps={exchange.reasoningSteps}
            isOpenByDefault
            resolveAgent={resolveAgenticFlow}
          />
        )}

        {/* Sources (if available and no final message yet) */}
        {exchange.keptSources?.length && exchange.finals.length === 0 && (
          <Sources
            key={`sources-${index}`}
            sources={exchange.keptSources}
            enableSources
            expandSources={false}
            highlightUid={highlightUid ?? undefined}
          />
        )}

        {/* Intermediary assistant messages and other messages */}
        {exchange.otherMessages.map((msg, msgIndex) => {
          const agenticFlow = resolveAgenticFlow(msg);
          const inlineSrc = msg.metadata?.sources;

          return (
            <React.Fragment key={`other-${index}-${msgIndex}`}>
              {!exchange.keptSources && inlineSrc?.length && (
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
                onCitationHover={(uid) => setHighlightUid(uid)}
                onCitationClick={(uid) => setHighlightUid(uid)}
              />
            </React.Fragment>
          );
        })}

        {/* Final assistant message and its sources */}
        {exchange.finals.map((msg, msgIndex) => {
          const agenticFlow = resolveAgenticFlow(msg);
          const finalSources = exchange.keptSources ?? (msg.metadata?.sources as any[] | undefined);

          return (
            <React.Fragment key={`final-${index}-${msgIndex}`}>
              {finalSources?.length && (
                <Sources
                  sources={finalSources}
                  enableSources
                  expandSources
                  highlightUid={highlightUid ?? undefined}
                />
              )}
              <MessageCard
                message={msg}
                agenticFlow={agenticFlow}
                currentAgenticFlow={currentAgenticFlow}
                side="left"
                enableCopy
                enableThumbs
                enableAudio
                suppressText={false}
                onCitationHover={(uid) => setHighlightUid(uid)}
                onCitationClick={(uid) => setHighlightUid(uid)}
              />
            </React.Fragment>
          );
        })}
      </React.Fragment>
    ));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", flexGrow: 1 }}>
      {renderContent()}
      <div ref={messagesEndRef} style={{ height: "1px", marginTop: "8px" }} />
    </div>
  );
}

export const NewMessagesArea = memo(Area);