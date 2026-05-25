import { useCallback, useMemo, useState } from "react";
import { AnyAgent } from "../common/agent";
import { ChatMessage } from "../slices/agentic/agenticOpenApi";
import { useSessionChange } from "./useSessionChange";

// Simple hook to help with agent selection.
export function useAgentSelector(
  agents: AnyAgent[],
  isNewConversation: boolean,
  history?: ChatMessage[],
  sessionId?: string,
) {
  // Track manually selected agent (overrides default logic)
  const [manuallySelectedAgentId, setManuallySelectedAgentId] = useState<string | null>(null);

  // Reset manual selection when session changes
  useSessionChange(sessionId, {
    onChange: () => setManuallySelectedAgentId(null),
  });

  const currentAgent = useMemo(() => {
    // If user manually selected an agent, use that
    if (manuallySelectedAgentId) {
      const manualAgent = agents.find((a) => a.id === manuallySelectedAgentId);
      if (manualAgent) return manualAgent;
    }

    // For existing sessions: use the last agent from history that exists in available agents
    // (iterate backwards to skip sub-agents that might not be in the main agents list)
    if (!isNewConversation && history?.length) {
      for (let i = history.length - 1; i >= 0; i--) {
        const agentName = history[i].metadata?.agent_id;
        if (agentName) {
          const sessionAgent = agents.find((a) => a.id === agentName);
          if (sessionAgent) return sessionAgent;
        }
      }
    }

    // Fallback to first agent in the list
    return agents[0] ?? null;
  }, [agents, history, isNewConversation, manuallySelectedAgentId]);

  const setCurrentAgent = useCallback(
    (agent: AnyAgent) => {
      // Set as manually selected agent (overrides default logic)
      setManuallySelectedAgentId(agent.id);
    },
    [setManuallySelectedAgentId],
  );

  return { currentAgent, setCurrentAgent };
}
