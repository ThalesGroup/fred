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
import { AnyAgent } from "../common/agent";
import {
  SessionSchema,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useListAgentsAgenticV1AgentsGetQuery,
} from "../slices/agentic/agenticOpenApi";
import { normalizeAgenticFlows } from "../utils/agenticFlows";

type AgentBySessionMap = Record<string, string>;

const L = {
  group: (title: string, data?: unknown) => {
    console.groupCollapsed(`🧭 ${title}`);
    if (data !== undefined) console.log(data);
    console.groupEnd();
  },
  info: (msg: string, data?: unknown) => console.log(`🧭 ${msg}`, data ?? ""),
  warn: (msg: string, data?: unknown) => console.warn(`🧭 ${msg}`, data ?? ""),
  error: (msg: string, data?: unknown) => console.error(`🧭 ${msg}`, data ?? ""),
};

function loadMap(): AgentBySessionMap {
  try {
    const raw = sessionStorage.getItem("agentBySession");
    const parsed = raw ? (JSON.parse(raw) as AgentBySessionMap) : {};
    L.group("loadMap(agentBySession)", parsed);
    return parsed;
  } catch (e) {
    L.error("loadMap failed", e);
    return {};
  }
}

function saveMap(map: AgentBySessionMap) {
  L.group("saveMap(agentBySession)", map);
  sessionStorage.setItem("agentBySession", JSON.stringify(map));
}

export function useSessionController() {
  // ---- Remote data ----
  const { data: flowsData, isLoading: flowsLoading } = useListAgentsAgenticV1AgentsGetQuery({});
  const {
    data: sessionsData,
    isLoading: sessionsLoading,
    refetch: refetchSessions,
  } = useGetSessionsAgenticV1ChatbotSessionsGetQuery();
  const [deleteSessionMutation] = useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation();

  // ---- Local state (single source of truth) ----
  const [agents, setAgents] = useState<AnyAgent[]>([]);
  const [sessions, setSessions] = useState<SessionSchema[]>([]);

  const [agentBySession, setAgentBySession] = useState<AgentBySessionMap>(() => loadMap());

  const [currentSession, setCurrentSession] = useState<SessionSchema | null>(null);
  const [isCreatingNewConversation, setIsCreatingNewConversation] = useState(false);
  const [draftAgenticFlow, setDraftAgenticFlow] = useState<AnyAgent | null>(null);

  const currentAgent = useMemo(() => {
    if (agents.length === 0) {
      L.warn("resolveFlow: no flows available");
      return null;
    }

    if (!currentSession) {
      const chosen = draftAgenticFlow ?? agents[0];
      L.info("resolveFlow: NO session → using", {
        source: draftAgenticFlow ? "draft" : "default[0]",
        name: chosen?.id,
      });
      return chosen;
    }

    const mappedName = agentBySession[currentSession.id];
    const resolved = mappedName ? agents.find((f) => f.id === mappedName) : null;

    const finalFlow = resolved ?? agents[0] ?? null;

    L.info("resolveFlow: WITH session", {
      sessionId: currentSession.id,
      mappedName,
      resolved: resolved ? { name: resolved.id, nickname: resolved.id } : null,
      fallback: !resolved && agents[0] ? { name: agents[0].id, nickname: agents[0].id } : null,
      final: finalFlow ? { name: finalFlow.id, nickname: finalFlow.id } : null,
    });

    return finalFlow;
  }, [currentSession, agents, agentBySession, draftAgenticFlow]);

  // ---- Hydration from queries ----
  useEffect(() => {
    if (!flowsLoading && flowsData) {
      const normalizedAgents = normalizeAgenticFlows(flowsData);
      setAgents(normalizedAgents);
      L.group(
        "HYDRATE flows",
        normalizedAgents.map((f) => ({ name: f.id, role: f.tuning.role })),
      );
    }
  }, [flowsLoading, flowsData]);

  useEffect(() => {
    if (!sessionsLoading && sessionsData) {
      setSessions(sessionsData);
      L.group(
        "HYDRATE sessions",
        sessionsData.map((s) => ({ id: s.id, title: s.title, updated_at: s.updated_at })),
      );

      const saved = sessionStorage.getItem("currentChatBotSession");
      if (saved) {
        try {
          const parsed: SessionSchema = JSON.parse(saved);
          const exists = sessionsData.find((s) => s.id === parsed.id);
          setCurrentSession(exists || null);
          L.info("restore currentSession from sessionStorage", { restored: exists?.id, title: exists?.title });
        } catch (e) {
          L.warn("restore currentSession failed", e);
          setCurrentSession(null);
        }
      } else {
        L.info("no currentSession in sessionStorage");
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

  const selectAgenticFlowForCurrentSession = (flow: AnyAgent) => {
    if (!currentSession) {
      L.info("selectAgent: NO session → stage draft", { name: flow.id });
      setDraftAgenticFlow(flow);
      return;
    }
    L.info("selectAgent: WITH session → bind to session", { sessionId: currentSession.id, name: flow.id });
    setAgentBySession((prev) => {
      const defaultName = agents[0]?.id;
      const existing = prev[currentSession.id];
      // allow overriding default with explicit user click
      const nextName = existing && defaultName && existing === defaultName ? flow.id : flow.id;
      const next = { ...prev, [currentSession.id]: nextName };
      saveMap(next);
      return next;
    });
  };

  // Fred rationale:
  // “New conversation” is a transient UI state. The real session comes from the backend
  // when the first message is saved. We show a draft until then.
  const startNewConversation = () => {
    L.info("startNewConversation");
    setCurrentSession(null);
    setIsCreatingNewConversation(true);
    sessionStorage.removeItem("currentChatBotSession");
  };

  const updateOrAddSession = (s: SessionSchema) => {
    L.info("updateOrAddSession: incoming", { id: s.id, title: s.title });

    // Upsert the session (no agent mapping writes here!)
    setSessions((prev) => {
      const exists = prev.some((x) => x.id === s.id);
      L.info("updateOrAddSession: upsert", { wasNew: !exists });
      return exists ? prev.map((x) => (x.id === s.id ? s : x)) : [s, ...prev];
    });

    // Focus that session in UI
    if (!currentSession || currentSession.id !== s.id) {
      L.info("selectSession (focus new/updated)", { id: s.id, title: s.title });
      selectSession(s);
    }

    // ⛔ IMPORTANT: do NOT bind agent here and do NOT consume the draft here.
    // Binding is done exclusively by bindDraftAgentToSessionId(), called from ChatBot
    // when the first session_id is known (final event or history load).
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

  const bindDraftAgentToSessionId = (sessionId: string) => {
    console.log("🧭 bindDraftAgentToSessionId", { sessionId, draft: draftAgenticFlow?.id });

    setAgentBySession((prev) => {
      const already = prev[sessionId];
      const defaultName = agents[0]?.id;
      const draftName = draftAgenticFlow?.id;

      // If someone pre-bound the default (e.g., Fred), allow overriding it with user's draft
      if (already) {
        if (draftName && defaultName && already === defaultName && draftName !== already) {
          const next = { ...prev, [sessionId]: draftName };
          saveMap(next);
          console.log("🧭 bindDraftAgentToSessionId: override default → draft", {
            sessionId,
            from: already,
            to: draftName,
          });
          return next;
        }
        console.log("🧭 bindDraftAgentToSessionId: already bound → keep", { sessionId, bound: already });
        return prev;
      }

      // No mapping yet → bind draft or default
      const chosen = draftName ?? defaultName;
      if (!chosen) {
        console.warn("🧭 bindDraftAgentToSessionId: no draft and no default");
        return prev;
      }
      const next = { ...prev, [sessionId]: chosen };
      saveMap(next);
      console.log("🧭 bindDraftAgentToSessionId: bound", { sessionId, chosen });
      return next;
    });

    // Consume draft only here (not in updateOrAddSession)
    if (draftAgenticFlow) {
      console.log("🧭 bindDraftAgentToSessionId: consume draft", { draft: draftAgenticFlow.id });
      setDraftAgenticFlow(null);
    }
  };

  const loading = flowsLoading || sessionsLoading;

  return {
    // state
    loading,
    agents,
    sessions,
    currentSession,
    currentAgent,
    isCreatingNewConversation,

    // handlers
    selectSession,
    selectAgenticFlowForCurrentSession,
    startNewConversation,
    updateOrAddSession,
    deleteSession,
    refetchSessions, // exposed for rare manual refreshes
    bindDraftAgentToSessionId, // exposed to anchor draft to first real session ID
  };
}
