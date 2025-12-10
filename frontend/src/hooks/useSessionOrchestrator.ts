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

import { useCallback, useEffect, useMemo, useState } from "react";
import { AnyAgent } from "../common/agent";
import type { SessionSchema, SessionWithFiles } from "../slices/agentic/agenticOpenApi";
import { useLocalStorageState } from "./useLocalStorageState";

/**
 * Thin, predictable orchestrator over server data (sessions, flows).
 * Session selection is now managed via URL routing.
 *
 * It does NOT fetch anything; you pass sessions/flows in from your RTK hooks.
 */
export function useSessionOrchestrator(params: {
  sessionsFromServer: SessionWithFiles[];
  agents: AnyAgent[];
  loading: boolean;
  sessionId?: string; // from URL parameter
}) {
  const { sessionsFromServer, agents, loading, sessionId } = params;

  // Local mirror so we can upsert/delete without fighting server pagination/timing.
  const [sessions, setSessions] = useState<SessionWithFiles[]>([]);
  useEffect(() => {
    console.log(
      "Orchestrator: useEffect triggered by sessionsFromServer change. New count:",
      sessionsFromServer?.length,
    );
    setSessions(sessionsFromServer ?? []);
  }, [sessionsFromServer]);

  // Derive currentSessionId from URL: if no sessionId param, we're in "draft" mode
  const currentSessionId = sessionId || "draft";
  console.log("currentSessionId: ", currentSessionId);

  // Track manually selected agent (overrides default logic)
  const [manuallySelectedAgentId, setManuallySelectedAgentId] = useState<string | null>(null);

  // Store last agent used for new conversations in localStorage
  const [lastNewConversationAgent, setLastNewConversationAgent] = useLocalStorageState<string | null>(
    "chat.lastNewConversationAgent",
    null,
  );

  // Derived "current" objects
  // Only match real sessions, not "draft"
  const currentSession = useMemo(
    () => (currentSessionId === "draft" ? null : (sessions.find((s) => s.id === currentSessionId) ?? null)),
    [sessions, currentSessionId],
  );
  console.log("[SESS] currentSession", currentSession);

  // Reset manual selection when session changes
  useEffect(() => {
    setManuallySelectedAgentId(null);
  }, [currentSessionId]);

  const currentAgent = useMemo(() => {
    if (!agents?.length) return null;

    // If user manually selected an agent, use that
    if (manuallySelectedAgentId) {
      const manualAgent = agents.find((a) => a.name === manuallySelectedAgentId);
      if (manualAgent) return manualAgent;
    }

    // For existing sessions: use the first agent from the session's agents array
    if (currentSession?.agents?.length) {
      const sessionAgentName = currentSession.agents[0];
      const sessionAgent = agents.find((a) => a.name === sessionAgentName);
      if (sessionAgent) return sessionAgent;
    }

    // For new conversations (draft): use last agent from localStorage
    if (!currentSession || currentSessionId === "draft") {
      if (lastNewConversationAgent) {
        const lastAgent = agents.find((a) => a.name === lastNewConversationAgent);
        if (lastAgent) return lastAgent;
      }
    }

    // Fallback to first agent in the list
    return agents[0] ?? null;
  }, [agents, currentSession, currentSessionId, lastNewConversationAgent, manuallySelectedAgentId]);

  const isCreatingNewConversation = currentSessionId === "draft";

  // Intentful API (page calls these)

  const selectAgentForCurrentSession = useCallback(
    (agent: AnyAgent) => {
      // Set as manually selected agent (overrides default logic)
      setManuallySelectedAgentId(agent.name);

      // Also save to localStorage if we're in a new conversation
      if (!currentSession || currentSessionId === "draft") {
        setLastNewConversationAgent(agent.name);
      }
    },
    [currentSession, currentSessionId, setLastNewConversationAgent],
  );

  const updateOrAddSession = useCallback((session: SessionWithFiles | SessionSchema | Partial<SessionWithFiles>) => {
    setSessions((prev) => {
      const idx = prev.findIndex((s) => s.id === session.id);
      if (idx >= 0) {
        const next = [...prev];
        // Merge with existing session to preserve fields like 'agents' that might not be in the update
        next[idx] = { ...next[idx], ...session };
        return next;
      }
      // When adding a new session, ensure it has default values for optional fields
      const newSession: SessionWithFiles = {
        ...(session as SessionWithFiles),
        agents: (session as SessionWithFiles).agents ?? [],
        file_names: (session as SessionWithFiles).file_names ?? [],
        attachments: (session as SessionWithFiles).attachments ?? [],
      };
      return [newSession, ...prev];
    });
  }, []);

  return {
    // data
    loading,
    sessions,
    currentSession,
    currentAgent,
    isCreatingNewConversation,

    // actions
    selectAgentForCurrentSession,
    updateOrAddSession,
  };
}
