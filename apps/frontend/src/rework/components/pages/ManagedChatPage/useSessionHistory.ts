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

import { useEffect, useRef, useState } from "react";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type { ChatMessage } from "../../../../slices/agentic/agenticOpenApi";
import { usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation } from "../../../../slices/controlPlane/controlPlaneOpenApi";

interface UseSessionHistoryArgs {
  sessionId: string | null;
  teamId: string | undefined;
  agentInstanceId: string | undefined;
  onLoaded: (messages: ChatMessage[]) => void;
}

function expandMessagesUrl(template: string, sessionId: string): string {
  return template.replace("{session_id}", encodeURIComponent(sessionId));
}

export function useSessionHistory({ sessionId, teamId, agentInstanceId, onLoaded }: UseSessionHistoryArgs) {
  const [isLoading, setIsLoading] = useState(false);
  const loadedRef = useRef<string | null>(null);

  const [prepareExecution] =
    usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation();

  useEffect(() => {
    if (!sessionId || !teamId || !agentInstanceId) return;
    if (loadedRef.current === sessionId) return;
    loadedRef.current = sessionId;

    const load = async () => {
      setIsLoading(true);
      try {
        await KeyCloakService.ensureFreshToken(30);
        const token = KeyCloakService.GetToken() ?? "";
        const prep = await prepareExecution({ teamId, agentInstanceId }).unwrap();
        const url = new URL(expandMessagesUrl(prep.messages_url_template, sessionId), window.location.origin);
        const resp = await fetch(url.toString(), { headers: { Authorization: `Bearer ${token}` } });
        if (!resp.ok) return;
        const msgs: ChatMessage[] = await resp.json();
        if (msgs.length > 0) onLoaded(msgs);
      } catch {
        // History load failure is non-fatal — user continues with empty view.
      } finally {
        setIsLoading(false);
      }
    };

    load();
  }, [sessionId, teamId, agentInstanceId, prepareExecution, onLoaded]);

  return { isLoading };
}
