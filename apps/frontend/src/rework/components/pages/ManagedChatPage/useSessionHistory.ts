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
  // The session this hook has finished answering for — "nothing more is
  // coming", which `isLoading` cannot say (it is also false before a load
  // starts). Callers sequencing work behind the thread need that difference.
  const [settledFor, setSettledFor] = useState<string | null>(null);
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

  // Deliberately session-less: history needs only `messages_url_template`,
  // which does not depend on the session — and asking for a session the caller
  // has only just minted (the URL is bound before the row is written) would be
  // refused, costing the thread its history.
  const [prepareExecution] =
    usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation();

  // The conversation this effect last saw. `startedForRef` suppresses a re-fire
  // WITHIN a visit; leaving and coming back is a NEW visit and must load again,
  // or a conversation left mid-load never revalidates and never settles.
  const visitingRef = useRef<string | null>(null);

  useEffect(() => {
    if (visitingRef.current !== sessionId) {
      visitingRef.current = sessionId;
      startedForRef.current = null;
    }
    if (!sessionId || !teamId || !agentInstanceId) return;

    // #2239 instant switch: a previously opened conversation renders straight
    // from the cache — synchronously, no spinner, composer stays enabled —
    // while the fetch below revalidates against the runtime (the source of
    // truth) in the background and swaps in the fresh history when it lands.
    const cached = getCachedSessionHistory(sessionId);
    if (cached !== undefined && cached.length > 0 && !isTurnActive()) onLoaded(cached);

    if (startedForRef.current === sessionId) return;
    startedForRef.current = sessionId;
    // This session's own load is what settles it. Without clearing, an A→B→A
    // round trip where B never settled comes back to A still flagged settled
    // from its first visit, while the load that would say so is in flight.
    setSettledFor(null);

    const load = async () => {
      // A cache hit downgrades the fetch to a silent background revalidation:
      // isLoading stays false so the UI never regresses to a spinner over an
      // already-rendered thread.
      if (cached === undefined) setIsLoading(true);
      try {
        // Started before the token refresh so the two overlap instead of
        // queueing. Claimed right away so a rejection while we are suspended is
        // not seen as unhandled; the await below still throws into this try.
        const preparation = prepareExecution({ teamId, agentInstanceId }).unwrap();
        preparation.catch(() => {});
        await KeyCloakService.ensureFreshToken(30);
        const token = KeyCloakService.GetToken() ?? "";
        const prep = await preparation;
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
        // Only for the session still on screen: a slow answer for one the user
        // has left would otherwise report ITS completion as the current
        // conversation's.
        if (activeSessionIdRef.current === sessionId) setSettledFor(sessionId);
      }
    };

    void load();
  }, [sessionId, teamId, agentInstanceId, prepareExecution, onLoaded, isTurnActive]);

  // No session is not "waiting": a fresh chat has no history to resolve, and
  // the marker left by the conversation just left says nothing about it.
  return { isLoading, isSettled: sessionId === null || settledFor === sessionId };
}
