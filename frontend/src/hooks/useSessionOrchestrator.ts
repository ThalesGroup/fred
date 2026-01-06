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
import { useSessionAgent } from "./usePrefs";

/**
 * Thin, predictable orchestrator over:
 * - server data (sessions, flows)
 * - local persistence (session->agent mapping via useSessionAgent)
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
    console.debug(
      "Orchestrator: useEffect triggered by sessionsFromServer change. New count:",
      sessionsFromServer?.length,
    );
    setSessions(sessionsFromServer ?? []);
  }, [sessionsFromServer]);

  // Choose initial session id:
  // - Prefer the most recently updated session if any
  // - Else use "draft"
  const defaultSessionId = useMemo(() => {
    if (!sessionsFromServer?.length) return "draft";
    const sorted = [...sessionsFromServer].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
    return sorted[0].id ?? "draft";
  }, [sessionsFromServer]);

  const [currentSessionId, setCurrentSessionId] = useState<string | null>(defaultSessionId);

  // Keep default in sync if server list changes (e.g., first load)
  useEffect(() => {
    if (!currentSessionId) setCurrentSessionId(defaultSessionId);
  }, [defaultSessionId, currentSessionId]);

  // Persistence: session -> agent mapping (+ last used agent)
  const { agentId, setAgentForSession, migrateSessionId } = useSessionAgent(currentSessionId);

  // Derived “current” objects
  const currentSession = useMemo(
    () => sessions.find((s) => s.id === currentSessionId) ?? null,
    [sessions, currentSessionId],
  );

  const currentAgent = useMemo(() => {
    if (!agentsFromServer?.length) return null;
    // If we have a stored agent for this session, prefer that flow
    const byStored = agentId ? (agentsFromServer.find((f) => f.name === agentId) ?? null) : null;
    if (byStored) return byStored;
    // Otherwise pick the first flow as a safe default
    return agentsFromServer[0] ?? null;
  }, [agentsFromServer, agentId]);

  const isCreatingNewConversation = !currentSession || currentSessionId === "draft";

  // Intentful API (page calls these)

  const selectSession = useCallback((session: SessionSchema) => {
    setCurrentSessionId(session.id);
  }, []);

  const selectAgentForCurrentSession = useCallback(
    (agent: AnyAgent) => {
      setAgentForSession(agent.name);
    },
    [setAgentForSession],
  );

  const startNewConversation = useCallback(() => {
    setCurrentSessionId("draft");
    // no need to pre-set agent: useSessionAgent will reuse lastAgent until user picks another one
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
      // “Draft” session got a real id from backend: migrate the mapping and select it
      migrateSessionId("draft", newId);
      setCurrentSessionId(newId);
    },
    [migrateSessionId],
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
