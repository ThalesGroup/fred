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
import { handlePlatformAccessResponse } from "../../../../common/platformAccess";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type { ChatMessage } from "../../../../slices/runtime/runtimeOpenApi";
import { deleteCachedSessionHistory, setCachedSessionHistory } from "./sessionHistoryCache";

interface UseSessionHistoryArgs {
  sessionId: string | null;
  spaceId?: string;
  messagesUrl: string | null | undefined;
  revision?: number;
  onLoaded: (messages: ChatMessage[]) => void;
  isTurnActive: () => boolean;
  getCurrentMessages?: () => ChatMessage[];
}

export function useSessionHistory({
  sessionId,
  spaceId = "",
  messagesUrl,
  revision,
  onLoaded,
  isTurnActive,
  getCurrentMessages,
}: UseSessionHistoryArgs) {
  const actor = KeyCloakService.GetSessionIdentity();
  const key = JSON.stringify([actor, spaceId, sessionId]);
  const loadedKey = useRef<string | null>(null);
  const activeKey = useRef(key);
  activeKey.current = key;
  const [result, setResult] = useState<{ key: string; status: "loading" | "ready" | "unavailable"; errorKey?: string }>(
    {
      key,
      status: "loading",
    },
  );

  useEffect(() => {
    if (!sessionId) return;
    const controller = new AbortController();
    const current = () =>
      !controller.signal.aborted && activeKey.current === key && KeyCloakService.GetSessionIdentity() === actor;
    const unavailable = (errorKey = "rework.weaverAgents.errors.server") => {
      loadedKey.current = null;
      deleteCachedSessionHistory(key);
      onLoaded([]);
      setResult({ key, status: "unavailable", errorKey });
    };
    // Local content is never evidence of current history access.
    if (messagesUrl === null) {
      unavailable();
      return;
    }
    if (messagesUrl === undefined) {
      if (!isTurnActive()) onLoaded([]);
      setResult({ key, status: "loading" });
      return;
    }
    if (loadedKey.current !== key && !isTurnActive()) {
      onLoaded([]);
      setResult({ key, status: "loading" });
    }
    const load = async () => {
      try {
        await KeyCloakService.ensureFreshToken(30);
        if (!current()) return;
        const response = await fetch(new URL(messagesUrl, window.location.origin), {
          headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
          signal: controller.signal,
          cache: "no-store",
          redirect: "error",
        });
        await handlePlatformAccessResponse(response);
        if (!response.ok) {
          if (current())
            unavailable(
              [401, 403, 404].includes(response.status)
                ? "rework.weaverAgents.scopeUnavailable"
                : "rework.weaverAgents.errors.server",
            );
          return;
        }
        const messages: ChatMessage[] = await response.json();
        if (!current()) return;
        const displayed = getCurrentMessages?.() ?? [];
        const lastExchange = displayed[displayed.length - 1]?.exchange_id;
        // Persistence follows stream close. An authorized but older snapshot
        // must not erase the live exchange already rendered in this visit.
        if (!isTurnActive() && (!lastExchange || messages.some((message) => message.exchange_id === lastExchange))) {
          setCachedSessionHistory(key, messages);
          onLoaded(messages);
        }
        loadedKey.current = key;
        setResult({ key, status: "ready" });
      } catch {
        if (current()) unavailable();
      }
    };
    void load();
    return () => controller.abort();
  }, [actor, key, sessionId, messagesUrl, revision, onLoaded, isTurnActive, getCurrentMessages]);

  const status = result.key === key ? result.status : "loading";
  return {
    isLoading: sessionId !== null && status === "loading",
    isSettled: sessionId === null || status !== "loading",
    errorKey: result.key === key ? result.errorKey : undefined,
    isUnavailable: sessionId !== null && status === "unavailable",
  };
}
