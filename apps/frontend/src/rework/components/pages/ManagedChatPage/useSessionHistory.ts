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
import { getCachedSessionHistory, setCachedSessionHistory } from "./sessionHistoryCache";

interface UseSessionHistoryArgs {
  sessionId: string | null;
  messagesUrl: string | null | undefined;
  onLoaded: (messages: ChatMessage[]) => void;
  // True while a streamed turn is in progress. A history response — cached or
  // fetched — must never replace a live turn: history necessarily lacks the
  // in-flight exchange, so applying it would visibly eat the user's message.
  isTurnActive: () => boolean;
}

export function useSessionHistory({ sessionId, messagesUrl, onLoaded, isTurnActive }: UseSessionHistoryArgs) {
  const [isLoading, setIsLoading] = useState(false);
  const [unavailableFor, setUnavailableFor] = useState<string | null>(null);
  const requestVersionRef = useRef(0);
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

  // The conversation this effect last saw. `startedForRef` suppresses a re-fire
  // WITHIN a visit; leaving and coming back is a NEW visit and must load again,
  // or a conversation left mid-load never revalidates and never settles.
  const visitingRef = useRef<string | null>(null);

  useEffect(() => {
    if (visitingRef.current !== sessionId) {
      visitingRef.current = sessionId;
      startedForRef.current = null;
      requestVersionRef.current += 1;
      setUnavailableFor(null);
      setSettledFor(null);
    }
    if (!sessionId) {
      setIsLoading(false);
      return;
    }

    // Cached history remains readable while session routing is resolved.
    const cached = getCachedSessionHistory(sessionId);
    if (cached !== undefined && cached.length > 0 && !isTurnActive()) onLoaded(cached);

    if (messagesUrl === undefined) {
      requestVersionRef.current += 1;
      startedForRef.current = null;
      setIsLoading(cached === undefined);
      return;
    }
    if (messagesUrl === null) {
      requestVersionRef.current += 1;
      startedForRef.current = null;
      setIsLoading(false);
      setUnavailableFor(sessionId);
      setSettledFor(sessionId);
      return;
    }
    const requestKey = JSON.stringify([sessionId, messagesUrl]);
    if (startedForRef.current === requestKey) return;
    startedForRef.current = requestKey;
    const requestVersion = ++requestVersionRef.current;
    const isCurrent = () => activeSessionIdRef.current === sessionId && requestVersionRef.current === requestVersion;
    setUnavailableFor(null);
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
        await KeyCloakService.ensureFreshToken(30);
        const token = KeyCloakService.GetToken() ?? "";
        if (!isCurrent()) return;
        const url = new URL(messagesUrl, window.location.origin);
        const resp = await fetch(url.toString(), { headers: { Authorization: `Bearer ${token}` } });
        if (!resp.ok) throw new Error("History unavailable");
        const msgs: ChatMessage[] = await resp.json();
        // Guards, in order:
        // - stale response: the user switched sessions while this fetch was
        //   in flight — applying would render session A's history under
        //   session B and poison the cache;
        // - live turn: see `isTurnActive` above;
        // - empty history: a brand-new session bound at send time has no
        //   persisted history yet — applying [] would wipe the optimistic
        //   first message.
        if (!isCurrent()) return;
        if (isTurnActive()) return;
        if (msgs.length === 0) return;
        setCachedSessionHistory(sessionId, msgs);
        onLoaded(msgs);
      } catch {
        if (isCurrent()) setUnavailableFor(sessionId);
      } finally {
        if (isCurrent()) {
          setIsLoading(false);
          setSettledFor(sessionId);
        }
      }
    };

    void load();
  }, [sessionId, messagesUrl, onLoaded, isTurnActive]);

  // No session is not "waiting": a fresh chat has no history to resolve, and
  // the marker left by the conversation just left says nothing about it.
  return {
    isLoading,
    isSettled: sessionId === null || settledFor === sessionId,
    isUnavailable: sessionId !== null && unavailableFor === sessionId,
  };
}
