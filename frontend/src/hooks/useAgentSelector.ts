import { useCallback, useMemo, useState } from "react";
import { AnyAgent } from "../common/agent";
import { ChatMessage } from "../slices/agentic/agenticOpenApi";
import { useLocalStorageState } from "./useLocalStorageState";
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

  // Store last agent used for new conversations in localStorage
  const [lastNewConversationAgent, setLastNewConversationAgent] = useLocalStorageState<string | null>(
    "chat.lastNewConversationAgent",
    null,
  );

  // Reset manual selection when session changes
  useSessionChange(sessionId, {
    onChange: () => setManuallySelectedAgentId(null),
  });

  const currentAgent = useMemo(() => {
    // If user manually selected an agent, use that
    if (manuallySelectedAgentId) {
      const manualAgent = agents.find((a) => a.name === manuallySelectedAgentId);
      if (manualAgent) return manualAgent;
    }

    // For existing sessions: use the last agent from history that exists in available agents
    // (iterate backwards to skip sub-agents that might not be in the main agents list)
    if (!isNewConversation && history?.length) {
      for (let i = history.length - 1; i >= 0; i--) {
        const agentName = history[i].metadata?.agent_name;
        if (agentName) {
          const sessionAgent = agents.find((a) => a.name === agentName);
          if (sessionAgent) return sessionAgent;
        }
      }
    }

    // For new conversations (draft): use last agent from localStorage
    if (isNewConversation && lastNewConversationAgent) {
      const lastAgent = agents.find((a) => a.name === lastNewConversationAgent);
      if (lastAgent) return lastAgent;
    }

    // Fallback to first agent in the list
    return agents[0] ?? null;
  }, [agents, history, isNewConversation, lastNewConversationAgent, manuallySelectedAgentId]);

  const setCurrentAgent = useCallback(
    (agent: AnyAgent) => {
      // Set as manually selected agent (overrides default logic)
      setManuallySelectedAgentId(agent.name);

      // Also save to localStorage if we're in a new conversation
      if (isNewConversation) {
        setLastNewConversationAgent(agent.name);
      }
    },
    [isNewConversation, setManuallySelectedAgentId, setLastNewConversationAgent],
  );

  return { currentAgent, setCurrentAgent };
}
