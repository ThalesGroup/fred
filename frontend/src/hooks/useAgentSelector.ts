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

    // For existing sessions: use the first agent from the session's agents array
    if (!isNewConversation && history?.length) {
      const lastAgentId = history[history.length - 1].metadata?.agent_name;
      const sessionAgent = agents.find((a) => a.name === lastAgentId);
      if (sessionAgent) return sessionAgent;
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
