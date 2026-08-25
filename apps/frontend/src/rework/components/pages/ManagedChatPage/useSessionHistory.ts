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
import type { ChatMessage } from "../../../../slices/runtime/runtimeOpenApi";
import { usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { getCachedSessionHistory, setCachedSessionHistory } from "./sessionHistoryCache";

interface UseSessionHistoryArgs {
  sessionId: string | null;
  teamId: string | undefined;
  agentInstanceId: string | undefined;
  onLoaded: (messages: ChatMessage[]) => void;
  // True while a streamed turn is in progress. A history response — cached or
  // fetched — must never replace a live turn: history necessarily lacks the
  // in-flight exchange, so applying it would visibly eat the user's message.
  isTurnActive: () => boolean;
}

function expandMessagesUrl(template: string, sessionId: string): string {
  return template.replace("{session_id}", encodeURIComponent(sessionId));
}

export function useSessionHistory({
  sessionId,
  teamId,
  agentInstanceId,
  onLoaded,
  isTurnActive,
}: UseSessionHistoryArgs) {
  const [isLoading, setIsLoading] = useState(false);
  // Session whose fetch this mount has already started — keeps an effect
  // re-fire (a dep identity change, not a genuine switch) from re-fetching.
  const startedForRef = useRef<string | null>(null);
  // Always the CURRENTLY active session id, refreshed every render. A fetch
  // that resolves after the user switched away must neither render its
  // messages under the new session nor overwrite the new session's cache
  // entry — the async closure's own `sessionId` is frozen at call time, so
  // staleness can only be detected against a ref.
  const activeSessionIdRef = useRef(sessionId);
  activeSessionIdRef.current = sessionId;

  const [prepareExecution] =
    usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation();

  useEffect(() => {
    if (!sessionId || !teamId || !agentInstanceId) return;

    // #2239 instant switch: a previously opened conversation renders straight
    // from the cache — synchronously, no spinner, composer stays enabled —
    // while the fetch below revalidates against the runtime (the source of
    // truth) in the background and swaps in the fresh history when it lands.
    const cached = getCachedSessionHistory(sessionId);
    if (cached !== undefined && cached.length > 0 && !isTurnActive()) onLoaded(cached);

    if (startedForRef.current === sessionId) return;
    startedForRef.current = sessionId;

    const load = async () => {
      // A cache hit downgrades the fetch to a silent background revalidation:
      // isLoading stays false so the UI never regresses to a spinner over an
      // already-rendered thread.
      if (cached === undefined) setIsLoading(true);
      try {
        await KeyCloakService.ensureFreshToken(30);
        const token = KeyCloakService.GetToken() ?? "";
        const prep = await prepareExecution({ teamId, agentInstanceId }).unwrap();
        const url = new URL(expandMessagesUrl(prep.messages_url_template, sessionId), window.location.origin);
        const resp = await fetch(url.toString(), { headers: { Authorization: `Bearer ${token}` } });
        if (!resp.ok) return;
        const msgs: ChatMessage[] = await resp.json();
        // Guards, in order:
        // - stale response: the user switched sessions while this fetch was
        //   in flight — applying would render session A's history under
        //   session B and poison the cache;
        // - live turn: see `isTurnActive` above;
        // - empty history: a brand-new session bound at send time has no
        //   persisted history yet — applying [] would wipe the optimistic
        //   first message.
        if (activeSessionIdRef.current !== sessionId) return;
        if (isTurnActive()) return;
        if (msgs.length === 0) return;
        setCachedSessionHistory(sessionId, msgs);
        onLoaded(msgs);
      } catch {
        // History load failure is non-fatal — user continues with the cached
        // (or empty) view.
      } finally {
        setIsLoading(false);
      }
    };

    void load();
  }, [sessionId, teamId, agentInstanceId, prepareExecution, onLoaded, isTurnActive]);

  return { isLoading };
}
