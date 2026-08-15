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

import { act, StrictMode } from "react";
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
  getLiveActivityRevision,
  onRender,
}: {
  sessionId: string | null;
  onLoaded: (messages: ChatMessage[]) => void;
  isTurnActive: () => boolean;
  getLiveActivityRevision: () => number;
  onRender: (hook: ReturnType<typeof useSessionHistory>) => void;
}) {
  const hook = useSessionHistory({
    sessionId,
    teamId: "team-1",
    agentInstanceId: "agent-1",
    onLoaded,
    isTurnActive,
    getLiveActivityRevision,
  });
  onRender(hook);
  return null;
}

describe("useSessionHistory — #2239 serve-then-revalidate cache", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: ReturnType<typeof useSessionHistory>;
  const onLoaded = vi.fn();
  let turnActive = false;
  let liveActivityRevision = 0;
  const isTurnActive = () => turnActive;
  const getLiveActivityRevision = () => liveActivityRevision;

  const host = (sessionId: string | null) => (
    <TestHost
      sessionId={sessionId}
      onLoaded={onLoaded}
      isTurnActive={isTurnActive}
      getLiveActivityRevision={getLiveActivityRevision}
      onRender={(h) => (latest = h)}
    />
  );

  const render = (sessionId: string | null) => {
    act(() => {
      root.render(host(sessionId));
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
    liveActivityRevision = 0;
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

  it("keeps an uncached StrictMode load visible until its request settles", async () => {
    const history = [msg("m1")];
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => response.promise;

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<StrictMode>{host("session-a")}</StrictMode>);
    });

    expect(latest.isLoading).toBe(true);

    response.resolve(okResponse(history));
    await settle();

    expect(latest.isLoading).toBe(false);
    expect(onLoaded).toHaveBeenCalledWith(history);
  });

  it("resets loading when switching from an uncached session to a cached session", () => {
    const cachedHistory = [msg("b1")];
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    setCachedSessionHistory("session-b", cachedHistory);
    fetchImpl = () => response.promise;

    mount("session-a");
    expect(latest.isLoading).toBe(true);

    render("session-b");

    expect(latest.isLoading).toBe(false);
    expect(onLoaded).toHaveBeenLastCalledWith(cachedHistory);
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

  it("does not replay cached history over a turn that is already active", async () => {
    setCachedSessionHistory("session-a", [msg("cached-before-live-turn")]);
    turnActive = true;

    mount("session-a");

    expect(onLoaded).not.toHaveBeenCalled();
    expect(latest.isLoading).toBe(false);
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

  it("does not let an older session request clear the active session's loading state", async () => {
    const aResponse = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    const bResponse = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = (url) => (url.includes("session-a") ? aResponse.promise : bResponse.promise);

    mount("session-a");
    render("session-b");
    expect(latest.isLoading).toBe(true);

    aResponse.resolve(okResponse([msg("a1")]));
    await settle();
    expect(latest.isLoading).toBe(true);

    bResponse.resolve(okResponse([msg("b1")]));
    await settle();
    expect(latest.isLoading).toBe(false);
  });

  it("an empty response is not applied — a brand-new session's optimistic first message survives", async () => {
    fetchImpl = async () => okResponse([]);
    mount("session-new");
    await settle();

    expect(onLoaded).not.toHaveBeenCalled();
    expect(getCachedSessionHistory("session-new")).toBeUndefined();
  });

  it("does not apply or cache a response that arrives during a live turn", async () => {
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => response.promise;

    mount("session-a");
    turnActive = true;
    response.resolve(okResponse([msg("stale-history")]));
    await settle();

    expect(onLoaded).not.toHaveBeenCalled();
    expect(getCachedSessionHistory("session-a")).toBeUndefined();
  });

  it("discards history started before a turn even when that turn has already settled", async () => {
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => response.promise;

    mount("session-a");
    liveActivityRevision += 1;
    response.resolve(okResponse([msg("stale-history")]));
    await settle();

    expect(turnActive).toBe(false);
    expect(onLoaded).not.toHaveBeenCalled();
    expect(getCachedSessionHistory("session-a")).toBeUndefined();
  });

  it("discards an overlapping response without scheduling a retry", async () => {
    vi.useFakeTimers();
    try {
      let call = 0;
      fetchImpl = async () => {
        call += 1;
        return okResponse([msg("stale-history")]);
      };

      mount("session-a");
      liveActivityRevision += 1;
      await settle();

      expect(onLoaded).not.toHaveBeenCalled();
      expect(getCachedSessionHistory("session-a")).toBeUndefined();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000);
        for (let i = 0; i < 10; i++) await Promise.resolve();
      });

      expect(call).toBe(1);
      expect(onLoaded).not.toHaveBeenCalled();
      expect(getCachedSessionHistory("session-a")).toBeUndefined();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not apply or cache an overlapping response that settles after unmount", async () => {
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => response.promise;

    mount("session-a");
    liveActivityRevision += 1;
    act(() => root.render(null));
    response.resolve(okResponse([msg("stale-history")]));
    await settle();

    expect(prepareExecutionCalls).toHaveLength(1);
    expect(onLoaded).not.toHaveBeenCalled();
    expect(getCachedSessionHistory("session-a")).toBeUndefined();
  });

  it("discards a response whose request began while a turn was active", async () => {
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => response.promise;
    turnActive = true;

    mount("session-a");
    turnActive = false;
    response.resolve(okResponse([msg("history-without-active-turn")]));
    await settle();

    expect(onLoaded).not.toHaveBeenCalled();
    expect(getCachedSessionHistory("session-a")).toBeUndefined();
  });

  it("replays the cache when the user returns to a session this mount already fetched", async () => {
    // The fetch guard must sit BELOW the cache replay. Above it, browser
    // Back/Forward on the same agent (no remount, sessionId → null → same id)
    // returns to a permanently empty thread.
    fetchImpl = async () => okResponse([msg("m1")]);
    mount("session-a");
    await settle();
    expect(onLoaded).toHaveBeenCalledWith([msg("m1")]);
    onLoaded.mockClear();
    prepareExecutionCalls.length = 0;

    render(null);
    await settle();
    render("session-a");
    await settle();

    expect(onLoaded).toHaveBeenCalledWith([msg("m1")]);
    // Served from cache — the guard still suppresses a duplicate fetch.
    expect(prepareExecutionCalls).toHaveLength(0);
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
