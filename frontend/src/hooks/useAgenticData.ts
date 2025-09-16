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

//
// Purpose:
//   Minimal data source for the Chat page.
//   - Fetch agentic flows and sessions from backend
//   - Upsert sessions locally (for WS "final" events) without fighting RTK cache
//   - Delete a session and refetch
//
// This hook *does not* decide which session/agent is selected or how preferences are persisted.
// Keep those concerns in useSessionAgent / useAgentPrefs / useUserPrefs.

import { useMemo, useState } from "react";
import {
  AgenticFlow,
  SessionSchema,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
  useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
} from "../slices/agentic/agenticOpenApi";

type SessionMap = Record<string, SessionSchema>;

export function useAgenticData() {
  // --- Remote sources (RTK-Query) ---
  const { data: flowsData, isLoading: flowsLoading } =
    useGetAgenticFlowsAgenticV1ChatbotAgenticflowsGetQuery();

  const {
    data: sessionsData,
    isLoading: sessionsLoading,
    refetch: refetchSessions,
  } = useGetSessionsAgenticV1ChatbotSessionsGetQuery();

  const [deleteSessionMutation] =
    useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation();

  // --- Local overlay for sessions (authoritative updates pushed via WS) ---
  // Why: RTK caches server state; WS "final" events or POST responses can arrive out-of-band.
  // We overlay per-id changes here (simple and robust).
  const [overlay, setOverlay] = useState<SessionMap>({});

  const flows: AgenticFlow[] = flowsData ?? [];

  const sessions: SessionSchema[] = useMemo(() => {
    const base = sessionsData ?? [];
    const map = new Map<string, SessionSchema>(base.map((s) => [s.id, s]));
    for (const s of Object.values(overlay)) map.set(s.id, s);
    // Optional: keep a stable, useful order (last updated first)
    return Array.from(map.values()).sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
  }, [sessionsData, overlay]);

  // --- Mutations exposed to UI ---

  /** Upsert a session coming from WebSocket "final" event or any POST response. */
  const updateOrAddSession = (s: SessionSchema) => {
    setOverlay((prev) => ({ ...prev, [s.id]: s }));
  };

  /** Delete a session (server) then refresh local view. */
  const deleteSession = async (s: SessionSchema) => {
    await deleteSessionMutation({ sessionId: s.id }).unwrap();
    setOverlay((prev) => {
      const { [s.id]: _gone, ...rest } = prev;
      return rest;
    });
    // Keep sidebar fresh
    refetchSessions();
  };

  return {
    // data
    loading: flowsLoading || sessionsLoading,
    flows,
    sessions,

    // helpers
    updateOrAddSession,
    deleteSession,
    refetchSessions,
  };
}
