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

import { useEffect, useMemo, useState } from "react";
import { 
  AgenticFlow, 
  SessionSchema, 
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation, 
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery, 
  useGetSessionsAgenticV1ChatbotSessionsGetQuery } 
  from "../slices/agentic/agenticOpenApi";

type AgentBySessionMap = Record<string, string>;

function resolveFlowForSession(
  session: SessionSchema | null,
  flows: AgenticFlow[],
  map: AgentBySessionMap
): AgenticFlow | null {
  if (!session || flows.length === 0) return null;
  const name = map[session.id];
  return flows.find((f) => f.name === name) ?? flows[0] ?? null;
}

function loadMap(): AgentBySessionMap {
  try {
    const raw = sessionStorage.getItem("agentBySession");
    return raw ? (JSON.parse(raw) as AgentBySessionMap) : {};
  } catch {
    return {};
  }
}

function saveMap(map: AgentBySessionMap) {
  sessionStorage.setItem("agentBySession", JSON.stringify(map));
}

export function useSessionController() {
  // ---- Remote data ----
  const { data: flowsData, isLoading: flowsLoading } =
    useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();
  const {
    data: sessionsData,
    isLoading: sessionsLoading,
    refetch: refetchSessions,
  } = useGetSessionsAgenticV1ChatbotSessionsGetQuery();
  const [deleteSessionMutation] =
    useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation();

  // ---- Local state (single source of truth) ----
  const [agenticFlows, setAgenticFlows] = useState<AgenticFlow[]>([]);
  const [sessions, setSessions] = useState<SessionSchema[]>([]);

  const [agentBySession, setAgentBySession] = useState<AgentBySessionMap>(() => loadMap());

  const [currentSession, setCurrentSession] = useState<SessionSchema | null>(null);
  const [isCreatingNewConversation, setIsCreatingNewConversation] = useState(false);

  // ---- Derived: current flow for the current session ----
  const currentAgenticFlow = useMemo(
    () => resolveFlowForSession(currentSession, agenticFlows, agentBySession),
    [currentSession, agenticFlows, agentBySession]
  );

  // ---- Hydration from queries ----
  useEffect(() => {
    if (!flowsLoading && flowsData) setAgenticFlows(flowsData);
  }, [flowsLoading, flowsData]);

  useEffect(() => {
    if (!sessionsLoading && sessionsData) {
      setSessions(sessionsData);

      // Restore last opened session (if still exists)
      const saved = sessionStorage.getItem("currentChatBotSession");
      if (saved) {
        try {
          const parsed: SessionSchema = JSON.parse(saved);
          const exists = sessionsData.find((s) => s.id === parsed.id);
          setCurrentSession(exists || null);
        } catch {
          setCurrentSession(null);
        }
      }
    }
  }, [sessionsLoading, sessionsData]);

  // ---- Environmental refetch (keep sidebar fresh) ----
  useEffect(() => {
    const onFocus = () => refetchSessions();
    const onVisibility = () => {
      if (document.visibilityState === "visible") refetchSessions();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [refetchSessions]);

  // ---- Handlers (UI uses only these) ----

  // Fred rationale:
  // Switching session restores that conversation's agent (or defaults to flows[0]).
  const selectSession = (s: SessionSchema) => {
    setCurrentSession(s);
    setIsCreatingNewConversation(false);
    sessionStorage.setItem("currentChatBotSession", JSON.stringify(s));
  };

  // Fred rationale:
  // Flow selection is *session-scoped*. We bind flow.name to session.id.
  const selectAgenticFlowForCurrentSession = (flow: AgenticFlow) => {
    if (!currentSession) return;
    setAgentBySession((prev) => {
      const next = { ...prev, [currentSession.id]: flow.name };
      saveMap(next);
      return next;
    });
    // (Optional: PATCH the session with agentic_flow_name when backend supports it)
  };

  // Fred rationale:
  // “New conversation” is a transient UI state. The real session comes from the backend
  // when the first message is saved. We show a draft until then.
  const startNewConversation = () => {
    setCurrentSession(null);
    setIsCreatingNewConversation(true);
    sessionStorage.removeItem("currentChatBotSession");
  };

  // Fred rationale:
  // Bot may return a brand-new session after first message; we upsert and select it.
  const updateOrAddSession = (s: SessionSchema) => {
    let wasNew = false;
    setSessions((prev) => {
      const exists = prev.some((x) => x.id === s.id);
      wasNew = !exists;
      return exists ? prev.map((x) => (x.id === s.id ? s : x)) : [s, ...prev];
    });

    if (wasNew && agenticFlows[0]) {
      // Assign default agent to first-seen sessions (predictable UX)
      setAgentBySession((prev) => {
        if (prev[s.id]) return prev;
        const next = { ...prev, [s.id]: agenticFlows[0].name };
        saveMap(next);
        return next;
      });
      // Keep backend-authoritative ordering/metadata
      refetchSessions();
    }

    // Ensure UI focuses that session
    if (!currentSession || currentSession.id !== s.id) {
      selectSession(s);
    }
  };

  // Fred rationale:
  // Deleting a session must also drop its agent binding (avoid stale keys).
  const deleteSession = async (s: SessionSchema) => {
    await deleteSessionMutation({ sessionId: s.id }).unwrap();
    setSessions((prev) => prev.filter((x) => x.id !== s.id));
    if (currentSession?.id === s.id) {
      setCurrentSession(null);
      sessionStorage.removeItem("currentChatBotSession");
    }
    setAgentBySession((prev) => {
      const { [s.id]: _gone, ...rest } = prev;
      saveMap(rest);
      return rest;
    });
    refetchSessions();
  };

  const loading = flowsLoading || sessionsLoading;

  return {
    // state
    loading,
    agenticFlows,
    sessions,
    currentSession,
    currentAgenticFlow,
    isCreatingNewConversation,

    // handlers
    selectSession,
    selectAgenticFlowForCurrentSession,
    startNewConversation,
    updateOrAddSession,
    deleteSession,
    refetchSessions, // exposed for rare manual refreshes
  };
}
