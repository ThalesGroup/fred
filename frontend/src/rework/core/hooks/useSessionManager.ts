// Copyright Thales 2026
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

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { v4 as uuidv4 } from "uuid";
import {
  useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery,
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation,
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation,
} from "../../../slices/controlPlane/controlPlaneOpenApi";

interface UseSessionManagerParams {
  teamId: string;
  agentInstanceId: string;
}

export interface SessionManager {
  sessionId: string | null;
  sessionTitle: string | null;
  bindSessionId: (sid: string) => void;
  createAndBindSession: (title: string) => string;
  patchTitle: (title: string) => void;
  patchUpdatedAt: () => void;
  startNewConversation: () => void;
}

export function useSessionManager({ teamId, agentInstanceId }: UseSessionManagerParams): SessionManager {
  const [searchParams, setSearchParams] = useSearchParams();
  const sessionId = searchParams.get("session");

  const [sessionTitle, setSessionTitle] = useState<string | null>(null);

  const { data: sessionData } = useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery(
    { teamId, sessionId: sessionId ?? "" },
    { skip: !teamId || !sessionId },
  );

  const [registerSession] = usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation();
  const [refreshSession] = usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation();

  useEffect(() => {
    if (sessionData?.title != null) setSessionTitle(sessionData.title);
  }, [sessionData]);

  // Reset title when navigating away from a session.
  useEffect(() => {
    setSessionTitle(null);
  }, [sessionId]);

  const bindSessionId = useCallback(
    (sid: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("session", sid);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const createAndBindSession = useCallback(
    (title: string): string => {
      const sid = uuidv4();
      bindSessionId(sid);
      registerSession({
        teamId,
        createSessionRequest: {
          session_id: sid,
          agent_instance_id: agentInstanceId,
          title: title.slice(0, 120),
        },
      }).catch(() => {});
      return sid;
    },
    [teamId, agentInstanceId, bindSessionId, registerSession],
  );

  const patchTitle = useCallback(
    (title: string) => {
      if (!sessionId) return;
      setSessionTitle(title);
      refreshSession({ teamId, sessionId, updateSessionRequest: { title } }).catch(() => {});
    },
    [teamId, sessionId, refreshSession],
  );

  const patchUpdatedAt = useCallback(() => {
    if (!sessionId) return;
    refreshSession({
      teamId,
      sessionId,
      updateSessionRequest: { updated_at: new Date().toISOString() },
    }).catch(() => {});
  }, [teamId, sessionId, refreshSession]);

  const startNewConversation = useCallback(() => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("session");
        return next;
      },
      { replace: true },
    );
  }, [setSearchParams]);

  return {
    sessionId,
    sessionTitle,
    bindSessionId,
    createAndBindSession,
    patchTitle,
    patchUpdatedAt,
    startNewConversation,
  };
}
