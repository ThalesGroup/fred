// src/hooks/usePrefs.ts
import { useCallback, useMemo, useState } from "react";
import { load, save, updateMap, renameKeyInMap } from "../common/persist";
import type { AgentPrefs, SessionPrefs, UserPrefs } from "../types/prefs";
import { SearchPolicyName } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

const K_USER = "UserPrefs";      // UserPrefs
const K_AGENT = "agentPrefs";      // Record<agentId, AgentPrefs>
const K_SESSION = "sessionMeta";   // Record<sessionId, SessionMeta>
const K_LAST_AGENT = "lastAgentId";// string | null

// -------- Global profile (system prompt) --------
export function useUserPrefs() {
  const [profile, setProfile] = useState<UserPrefs>(() =>
    load<UserPrefs>(K_USER, { systemPrompt: "" }),
  );

  const setSystemPrompt = useCallback((systemPrompt: string) => {
    const next = { systemPrompt };
    setProfile(next);
    save<UserPrefs>(K_USER, next);
  }, []);

  return { profile, setSystemPrompt };
}

// -------- Per-agent preferences --------
const DEFAULT_AGENT_PREFS: AgentPrefs = {
  search_policy: "hybrid",
  selected_document_libraries_ids: [],
  selected_prompt_ids: null,
  selected_template_ids: null,
};

export function useAgentPrefs(agentId: string | null) {
  const [map, setMap] = useState<Record<string, AgentPrefs>>(() =>
    load<Record<string, AgentPrefs>>(K_AGENT, {}),
  );

  const prefs = useMemo<AgentPrefs>(() => {
    if (agentId && map[agentId]) return map[agentId];
    return DEFAULT_AGENT_PREFS;
  }, [agentId, map]);

  const updatePrefs = useCallback((patch: Partial<AgentPrefs>) => {
    if (!agentId) return;
    const next = updateMap<AgentPrefs>(K_AGENT, agentId, patch);
    setMap(next);
  }, [agentId]);

  // Optional helpers for common fields (nice DX)
  const setSearchPolicy = useCallback(
    (p: SearchPolicyName) => updatePrefs({ search_policy: p }),
    [updatePrefs],
  );
  const setLibraries = useCallback(
    (ids: string[]) => updatePrefs({ selected_document_libraries_ids: ids }),
    [updatePrefs],
  );

  return { prefs, updatePrefs, setSearchPolicy, setLibraries };
}

// -------- Per-session selected agent + last-used fallback --------
export function useSessionAgent(sessionId: string | null) {
  const [metaMap, setMetaMap] = useState<Record<string, SessionPrefs>>(() =>
    load<Record<string, SessionPrefs>>(K_SESSION, {}),
  );
  const [lastAgent, setLastAgent] = useState<string | null>(() =>
    load<string | null>(K_LAST_AGENT, null),
  );

  // Which agent should be active for this session?
  const agentId = useMemo<string | null>(() => {
    if (sessionId && metaMap[sessionId]?.agentId) return metaMap[sessionId].agentId;
    return lastAgent;
  }, [sessionId, metaMap, lastAgent]);

  const setAgentForSession = useCallback((nextAgentId: string) => {
    if (sessionId) {
      const next = updateMap<SessionPrefs>(K_SESSION, sessionId, { agentId: nextAgentId });
      setMetaMap(next);
    }
    setLastAgent(nextAgentId);
    save<string | null>(K_LAST_AGENT, nextAgentId);
  }, [sessionId]);

  // When a "draft" session gets a real id, migrate the stored mapping.
  const migrateSessionId = useCallback((oldId: string, newId: string) => {
    const next = renameKeyInMap<SessionPrefs>(K_SESSION, oldId, newId);
    setMetaMap(next);
  }, []);

  return { agentId, setAgentForSession, migrateSessionId };
}
