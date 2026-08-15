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
  // True while a streamed turn is in progress. Cached or fetched history must
  // not replace a live turn because it cannot contain the in-flight exchange.
  isTurnActive: () => boolean;
  // A turn can start and finish while a history request is in flight. This
  // revision detects that overlap even when the turn is no longer active when
  // the response arrives.
  getLiveActivityRevision: () => number;
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
  getLiveActivityRevision,
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
  const isMountedRef = useRef(true);
  const loadGenerationRef = useRef(0);
  const loadingResetSessionRef = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    // Run once per session identity. Re-running this for the session already
    // being fetched would leave the loading indicator out of step with its request.
    if (loadingResetSessionRef.current === sessionId) return;
    loadingResetSessionRef.current = sessionId;
    loadGenerationRef.current += 1;
    setIsLoading(false);
  }, [sessionId]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const [prepareExecution] =
    usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation();

  useEffect(() => {
    if (!sessionId || !teamId || !agentInstanceId) return;

    // #2239 instant switch: a previously opened conversation renders straight
    // from the cache — synchronously, no spinner, composer stays enabled —
    // while the fetch below revalidates against the runtime (the source of
    // truth) in the background and replaces it with fresh history when safe.
    // Replayed on EVERY effect run, including a return to a session this mount
    // already fetched. The fetch guard below must stay BELOW this line: above
    // it, re-entering a session (browser Back/Forward on the same agent, which
    // does not remount) renders an empty thread forever.
    const cached = getCachedSessionHistory(sessionId);
    if (cached !== undefined && cached.length > 0 && !isTurnActive()) onLoaded(cached);

    if (startedForRef.current === sessionId) return;
    startedForRef.current = sessionId;

    const turnWasActiveAtStart = isTurnActive();
    const liveActivityRevisionAtStart = getLiveActivityRevision();
    const loadGeneration = ++loadGenerationRef.current;

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
        // A response that overlapped live activity cannot contain the current
        // turn. Applying or caching it would replace newer state with an older
        // snapshot. Do not retry automatically: persistence can still lag the
        // completed turn, so a later full replacement is not inherently safer.
        if (!isMountedRef.current || activeSessionIdRef.current !== sessionId) return;
        if (turnWasActiveAtStart || isTurnActive() || getLiveActivityRevision() !== liveActivityRevisionAtStart) {
          return;
        }
        if (msgs.length === 0) return;
        setCachedSessionHistory(sessionId, msgs);
        onLoaded(msgs);
      } catch {
        // History load failure is non-fatal — user continues with the cached
        // (or empty) view.
      } finally {
        if (
          isMountedRef.current &&
          activeSessionIdRef.current === sessionId &&
          loadGenerationRef.current === loadGeneration
        ) {
          setIsLoading(false);
        }
      }
    };

    void load();
  }, [sessionId, teamId, agentInstanceId, prepareExecution, onLoaded, isTurnActive, getLiveActivityRevision]);

  return { isLoading };
}
