// @vitest-environment happy-dom
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

// Coverage for the #2239 session-history cache: switching back to a
// previously opened conversation renders instantly from the in-memory cache
// (no spinner) while the runtime is revalidated in the background — and the
// guards that keep that safe:
//
// - a response that lands after the user switched sessions is neither
//   rendered under the new session nor written to the cache;
// - a response never replaces a live streamed turn;
// - an empty response never wipes the optimistic first message of a
//   brand-new session;
// - the cache is a bounded LRU.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../../../../slices/runtime/runtimeOpenApi";
import {
  clearSessionHistoryCache,
  dropInMemorySessionHistoryForTests,
  getCachedSessionHistory,
  setCachedSessionHistory,
} from "./sessionHistoryCache";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    ensureFreshToken: async () => {},
    GetToken: () => "test-token",
  },
}));

const prepareExecutionCalls: unknown[] = [];
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation: () => [
    (args: unknown) => {
      prepareExecutionCalls.push(args);
      return {
        unwrap: async () => ({ messages_url_template: "/runtime/sessions/{session_id}/messages" }),
      };
    },
  ],
}));

import { useSessionHistory } from "./useSessionHistory";

const msg = (id: string): ChatMessage => ({ id }) as unknown as ChatMessage;

// Per-test fetch behavior, keyed on the session id present in the URL.
let fetchImpl: (url: string) => Promise<{ ok: boolean; json: () => Promise<ChatMessage[]> }>;
const okResponse = (msgs: ChatMessage[]) => ({ ok: true, json: async () => msgs });

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function TestHost({
  sessionId,
  onLoaded,
  isTurnActive,
  onRender,
}: {
  sessionId: string | null;
  onLoaded: (messages: ChatMessage[]) => void;
  isTurnActive: () => boolean;
  onRender: (hook: ReturnType<typeof useSessionHistory>) => void;
}) {
  const hook = useSessionHistory({ sessionId, teamId: "team-1", agentInstanceId: "agent-1", onLoaded, isTurnActive });
  onRender(hook);
  return null;
}

describe("useSessionHistory — #2239 serve-then-revalidate cache", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: ReturnType<typeof useSessionHistory>;
  const onLoaded = vi.fn();
  let turnActive = false;
  const isTurnActive = () => turnActive;

  const render = (sessionId: string | null) => {
    act(() => {
      root.render(
        <TestHost
          sessionId={sessionId}
          onLoaded={onLoaded}
          isTurnActive={isTurnActive}
          onRender={(h) => (latest = h)}
        />,
      );
    });
  };

  const mount = (sessionId: string | null) => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    render(sessionId);
  };

  // Drains the microtask chain inside load() (token → prepare → fetch → json).
  const settle = async () => {
    await act(async () => {
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
  };

  beforeEach(() => {
    clearSessionHistoryCache();
    onLoaded.mockClear();
    prepareExecutionCalls.length = 0;
    turnActive = false;
    fetchImpl = async () => okResponse([]);
    vi.stubGlobal("fetch", (url: string) => fetchImpl(String(url)));
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("cache miss: shows the loading state, applies the fetched history, and populates the cache", async () => {
    const history = [msg("m1"), msg("m2")];
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => response.promise;

    mount("session-a");
    expect(latest.isLoading).toBe(true);
    expect(onLoaded).not.toHaveBeenCalled();

    response.resolve(okResponse(history));
    await settle();

    expect(latest.isLoading).toBe(false);
    expect(onLoaded).toHaveBeenCalledWith(history);
    expect(getCachedSessionHistory("session-a")).toEqual(history);
  });

  it("cache hit: renders synchronously with no loading state, then revalidates in the background", async () => {
    const cachedHistory = [msg("m1")];
    const freshHistory = [msg("m1"), msg("m2-from-another-device")];
    setCachedSessionHistory("session-a", cachedHistory);
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => response.promise;

    mount("session-a");
    // Served from cache before any network round-trip, composer never gated.
    expect(onLoaded).toHaveBeenCalledWith(cachedHistory);
    expect(latest.isLoading).toBe(false);

    response.resolve(okResponse(freshHistory));
    await settle();

    expect(latest.isLoading).toBe(false);
    expect(onLoaded).toHaveBeenLastCalledWith(freshHistory);
    expect(getCachedSessionHistory("session-a")).toEqual(freshHistory);
  });

  it("a response landing after a session switch is neither applied nor cached under either session", async () => {
    const aResponse = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    const bHistory = [msg("b1")];
    fetchImpl = (url) => (url.includes("session-a") ? aResponse.promise : Promise.resolve(okResponse(bHistory)));

    mount("session-a");
    render("session-b");
    await settle();
    expect(onLoaded).toHaveBeenLastCalledWith(bHistory);
    onLoaded.mockClear();

    // Session A's slow response finally lands — after the user moved to B.
    aResponse.resolve(okResponse([msg("a1")]));
    await settle();

    expect(onLoaded).not.toHaveBeenCalled(); // A's history never rendered under B
    expect(getCachedSessionHistory("session-a")).toBeUndefined(); // and never cached as fresh
    expect(getCachedSessionHistory("session-b")).toEqual(bHistory);
  });

  it("an empty response is not applied — a brand-new session's optimistic first message survives", async () => {
    fetchImpl = async () => okResponse([]);
    mount("session-new");
    await settle();

    expect(onLoaded).not.toHaveBeenCalled();
    expect(getCachedSessionHistory("session-new")).toBeUndefined();
  });

  it("a response never replaces a live streamed turn, and is not cached over it", async () => {
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => response.promise;

    mount("session-a");
    turnActive = true; // a turn starts streaming while history is in flight
    response.resolve(okResponse([msg("stale-history")]));
    await settle();

    expect(onLoaded).not.toHaveBeenCalled();
    expect(getCachedSessionHistory("session-a")).toBeUndefined();
  });

  it("does not re-fetch on an effect re-fire for the same session", async () => {
    fetchImpl = async () => okResponse([msg("m1")]);
    mount("session-a");
    await settle();
    expect(prepareExecutionCalls).toHaveLength(1);

    render("session-a");
    await settle();
    expect(prepareExecutionCalls).toHaveLength(1); // still one fetch round-trip
  });
});

describe("sessionHistoryCache — bounded LRU", () => {
  beforeEach(() => clearSessionHistoryCache());

  it("evicts the least-recently-used entry beyond the cap", () => {
    for (let i = 0; i < 21; i++) setCachedSessionHistory(`session-${i}`, [msg(`m${i}`)]);
    expect(getCachedSessionHistory("session-0")).toBeUndefined(); // oldest evicted
    expect(getCachedSessionHistory("session-1")).toEqual([msg("m1")]);
    expect(getCachedSessionHistory("session-20")).toEqual([msg("m20")]);
  });

  it("a read refreshes recency", () => {
    for (let i = 0; i < 20; i++) setCachedSessionHistory(`session-${i}`, [msg(`m${i}`)]);
    getCachedSessionHistory("session-0"); // touch the oldest
    setCachedSessionHistory("session-extra", [msg("extra")]);
    expect(getCachedSessionHistory("session-0")).toEqual([msg("m0")]); // survived
    expect(getCachedSessionHistory("session-1")).toBeUndefined(); // evicted instead
  });
});

describe("sessionHistoryCache — per-tab persistence across a page refresh", () => {
  beforeEach(() => clearSessionHistoryCache());
  afterEach(() => vi.restoreAllMocks());

  it("an entry survives a reload: JS heap gone, sessionStorage kept", () => {
    setCachedSessionHistory("session-a", [msg("m1")]);
    dropInMemorySessionHistoryForTests(); // simulates F5
    expect(getCachedSessionHistory("session-a")).toEqual([msg("m1")]);
  });

  it("eviction removes the persisted copy too — the cap holds across reloads", () => {
    for (let i = 0; i < 21; i++) setCachedSessionHistory(`session-${i}`, [msg(`m${i}`)]);
    dropInMemorySessionHistoryForTests();
    expect(getCachedSessionHistory("session-0")).toBeUndefined(); // evicted from storage as well
    expect(getCachedSessionHistory("session-20")).toEqual([msg("m20")]);
  });

  it("a blocked or full sessionStorage degrades to in-memory only, without throwing", () => {
    // Replace the WHOLE global with a delegating fake. Patching the instance
    // (Object.defineProperty) or Storage.prototype no longer intercepts:
    // vitest's happy-dom serves sessionStorage through a proxy whose method
    // lookup ignores outside-defined own properties — defineProperty reports
    // success, the real setItem still runs, and this test silently asserted
    // nothing (the entry WAS persisted).
    const real = sessionStorage;
    vi.stubGlobal("sessionStorage", {
      getItem: (k: string) => real.getItem(k),
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
      removeItem: (k: string) => real.removeItem(k),
      key: (i: number) => real.key(i),
      get length() {
        return real.length;
      },
    });
    try {
      setCachedSessionHistory("session-a", [msg("m1")]); // must not throw
      expect(getCachedSessionHistory("session-a")).toEqual([msg("m1")]); // memory still serves it
    } finally {
      vi.unstubAllGlobals();
    }

    dropInMemorySessionHistoryForTests();
    expect(getCachedSessionHistory("session-a")).toBeUndefined(); // nothing was persisted
  });

  it("a corrupted persisted entry is ignored, not thrown", () => {
    sessionStorage.setItem("chat.history.session-a", "{not json");
    sessionStorage.setItem("chat.history#index", JSON.stringify(["session-a"]));
    expect(getCachedSessionHistory("session-a")).toBeUndefined();
  });
});
