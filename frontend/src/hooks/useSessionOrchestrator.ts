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
import type { SessionSchema } from "../slices/agentic/agenticOpenApi";

/**
 * Thin, predictable orchestrator over server data (sessions, flows).
 * Session selection is now managed via URL routing.
 *
 * It does NOT fetch anything; you pass sessions/flows in from your RTK hooks.
 */
export function useSessionOrchestrator(params: {
  sessionsFromServer: SessionSchema[];
  agentsFromServer: AnyAgent[];
  loading: boolean;
}) {
  const { sessionsFromServer, agentsFromServer, loading } = params;

  // Local mirror so we can upsert/delete without fighting server pagination/timing.
  const [sessions, setSessions] = useState<SessionSchema[]>([]);
  useEffect(() => {
    console.log(
      "Orchestrator: useEffect triggered by sessionsFromServer change. New count:",
      sessionsFromServer?.length,
    );
    setSessions(sessionsFromServer ?? []);
  }, [sessionsFromServer]);

  // Track current session (managed by parent via selectSession)
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  // Track current agent for the session
  const [currentAgentId, setCurrentAgentId] = useState<string | null>(null);

  // Derived "current" objects
  const currentSession = useMemo(
    () => sessions.find((s) => s.id === currentSessionId) ?? null,
    [sessions, currentSessionId],
  );

  const currentAgent = useMemo(() => {
    if (!agentsFromServer?.length) return null;
    // If we have a selected agent for this session, use that
    const bySelected = currentAgentId ? (agentsFromServer.find((f) => f.name === currentAgentId) ?? null) : null;
    if (bySelected) return bySelected;
    // Otherwise pick the first agent as default
    return agentsFromServer[0] ?? null;
  }, [agentsFromServer, currentAgentId]);

  const isCreatingNewConversation = !currentSession || currentSessionId === "draft";

  // Intentful API (page calls these)

  const selectSession = useCallback((session: SessionSchema) => {
    setCurrentSessionId(session.id);
  }, []);

  const selectAgentForCurrentSession = useCallback(
    (agent: AnyAgent) => {
      setCurrentAgentId(agent.name);
    },
    [],
  );

  const startNewConversation = useCallback(() => {
    setCurrentSessionId("draft");
  }, []);

  const updateOrAddSession = useCallback((session: SessionSchema) => {
    setSessions((prev) => {
      const idx = prev.findIndex((s) => s.id === session.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = session;
        return next;
      }
      return [session, ...prev];
    });
  }, []);

  const deleteSession = useCallback(
    (session: SessionSchema) => {
      console.log("Orchestrator: deleteSession called for session:", session.id);
      setSessions((prev) => {
        console.log("Orchestrator: Previous local state count:", prev.length);
        const next = prev.filter((s) => s.id !== session.id);
        console.log("Orchestrator: New local state count after filter:", next.length);
        return next;
      });
      // If we just deleted the active one, bounce to draft
      if (session.id === currentSessionId) {
        setCurrentSessionId("draft");
      }
    },
    [currentSessionId],
  );

  const bindDraftAgentToSessionId = useCallback(
    (newId: string) => {
      // "Draft" session got a real id from backend: select it
      setCurrentSessionId(newId);
    },
    [],
  );

  return {
    // data
    loading,
    agenticFlows: agentsFromServer,
    sessions,
    currentSession,
    currentAgent,
    isCreatingNewConversation,

    // actions
    selectSession,
    selectAgentForCurrentSession,
    startNewConversation,
    updateOrAddSession,
    deleteSession,
    bindDraftAgentToSessionId,
  };
}
