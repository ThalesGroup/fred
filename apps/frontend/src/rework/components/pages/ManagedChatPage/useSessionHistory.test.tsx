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

// History requires a current authorized read. Local snapshots never bypass
// admission; stale responses and active turns retain their isolation guarantees.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { platformAccessDenied } from "../../../../common/platformAccess";
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

vi.mock("../../../../common/config", () => ({ getConfig: () => ({ frontend_basename: "/" }) }));

vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    ensureFreshToken: async () => {},
    GetSessionIdentity: () => "alice-session",
    GetToken: () => "test-token",
  },
}));

import { useSessionHistory } from "./useSessionHistory";

const historyKey = (sid: string) => JSON.stringify(["alice-session", "space-1", sid]);

const msg = (id: string): ChatMessage => ({ id }) as unknown as ChatMessage;

// Per-test fetch behavior, keyed on the session id present in the URL.
let routeOverride: string | null | undefined = "default";
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
  const hook = useSessionHistory({
    sessionId,
    spaceId: "space-1",
    messagesUrl: routeOverride === "default" ? `/runtime/sessions/${sessionId}/messages` : routeOverride,
    onLoaded,
    isTurnActive,
  });
  onRender(hook);
  return null;
}

describe("useSessionHistory authorized reads", () => {
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

  // Drains token refresh, fetch and JSON decoding.
  const settle = async () => {
    await act(async () => {
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
  };

  beforeEach(() => {
    clearSessionHistoryCache();
    onLoaded.mockClear();
    routeOverride = "default";
    turnActive = false;
    fetchImpl = async () => okResponse([]);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => fetchImpl(String(url))),
    );
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
    expect(onLoaded.mock.calls.every(([messages]) => messages.length === 0)).toBe(true);

    response.resolve(okResponse(history));
    await settle();

    expect(latest.isLoading).toBe(false);
    expect(onLoaded).toHaveBeenCalledWith(history);
    expect(getCachedSessionHistory(historyKey("session-a"))).toEqual(history);
    expect(fetch).toHaveBeenCalledWith(new URL("/runtime/sessions/session-a/messages", window.location.origin), {
      cache: "no-store",
      redirect: "error",
      signal: expect.any(AbortSignal),
      headers: { Authorization: "Bearer test-token" },
    });
  });

  it("a cached snapshot stays hidden until the current authorized read succeeds", async () => {
    const cachedHistory = [msg("m1")];
    const freshHistory = [msg("m1"), msg("m2-from-another-device")];
    setCachedSessionHistory(historyKey("session-a"), cachedHistory);
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => response.promise;

    mount("session-a");
    // A local snapshot cannot prove access to this conversation.
    expect(onLoaded).toHaveBeenCalledWith([]);
    expect(onLoaded).not.toHaveBeenCalledWith(cachedHistory);
    expect(latest.isLoading).toBe(true);

    response.resolve(okResponse(freshHistory));
    await settle();

    expect(latest.isLoading).toBe(false);
    expect(onLoaded).toHaveBeenLastCalledWith(freshHistory);
    expect(getCachedSessionHistory(historyKey("session-a"))).toEqual(freshHistory);
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

    // Session A's slow response finally lands - after the user moved to B.
    aResponse.resolve(okResponse([msg("a1")]));
    await settle();

    expect(onLoaded).not.toHaveBeenCalled(); // A's history never rendered under B
    expect(getCachedSessionHistory(historyKey("session-a"))).toBeUndefined(); // and never cached as fresh
    expect(getCachedSessionHistory(historyKey("session-b"))).toEqual(bHistory);
    // ...nor does it report ITS completion as B's: callers sequence work behind
    // this flag, and B's own load has already settled and will not settle twice.
    expect(latest.isSettled).toBe(true);
  });

  // A chat with no session id yet has no history to resolve. Reporting it as
  // unsettled would put callers that sequence work behind the thread - the
  // welcome stage, the capability panel - into a wait that never ends.
  it("is settled with no session, even after leaving one that had settled", async () => {
    mount("session-a");
    await settle();
    expect(latest.isSettled).toBe(true);

    render(null);

    expect(latest.isSettled).toBe(true);
  });

  it("re-entering a conversation is not settled by its previous visit", async () => {
    setCachedSessionHistory(historyKey("session-a"), [msg("a1")]);
    const slowB = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = (url) => (url.includes("session-b") ? slowB.promise : Promise.resolve(okResponse([msg("a1")])));

    mount("session-a");
    await settle();
    expect(latest.isSettled).toBe(true);

    // Leave for B, which never answers, then come straight back to A: A's own
    // load is in flight again, so the verdict from its first visit is stale.
    render("session-b");
    render("session-a");

    expect(latest.isSettled).toBe(false);
  });

  // Leaving mid-load discards the answer (the stale guard) and caches nothing.
  // Coming back therefore has to load again - a visit suppressed as if it were
  // a re-render would never settle, and callers waiting on that wait forever.
  it("loads again on re-entry after leaving mid-load", async () => {
    const slowA = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => slowA.promise;

    mount("session-a");
    render(null);
    slowA.resolve(okResponse([msg("a1")]));
    await settle();
    expect(latest.isSettled).toBe(true); // no session: nothing to resolve

    fetchImpl = async () => okResponse([msg("a1")]);
    render("session-a");
    await settle();

    expect(latest.isSettled).toBe(true);
    expect(onLoaded).toHaveBeenLastCalledWith([msg("a1")]);
  });

  it("an authorized empty response is a settled empty history", async () => {
    fetchImpl = async () => okResponse([]);
    mount("session-new");
    await settle();

    expect(onLoaded.mock.calls.every(([messages]) => messages.length === 0)).toBe(true);
    expect(getCachedSessionHistory(historyKey("session-new"))).toEqual([]);
    expect(latest.isSettled).toBe(true);
    expect(latest.isUnavailable).toBe(false);
  });

  it("a response never replaces a live streamed turn, and is not cached over it", async () => {
    const response = deferred<{ ok: boolean; json: () => Promise<ChatMessage[]> }>();
    fetchImpl = () => response.promise;

    mount("session-a");
    turnActive = true; // a turn starts streaming while history is in flight
    response.resolve(okResponse([msg("stale-history")]));
    await settle();

    expect(onLoaded.mock.calls.every(([messages]) => messages.length === 0)).toBe(true);
    expect(getCachedSessionHistory(historyKey("session-a"))).toBeUndefined();
  });

  it("does not re-fetch on an effect re-fire for the same session", async () => {
    fetchImpl = async () => okResponse([msg("m1")]);
    mount("session-a");
    await settle();
    expect(fetch).toHaveBeenCalledTimes(1);

    render("session-a");
    await settle();
    expect(fetch).toHaveBeenCalledTimes(1); // still one fetch round-trip
  });
  it("hides cached history while routing and evicts it when the route is unavailable", async () => {
    const history = [msg("cached")];
    setCachedSessionHistory(historyKey("legacy"), history);
    routeOverride = undefined;
    mount("legacy");
    await settle();
    expect(onLoaded).toHaveBeenCalledWith([]);
    expect(onLoaded).not.toHaveBeenCalledWith(history);
    expect(fetch).not.toHaveBeenCalled();
    expect(latest.isUnavailable).toBe(false);
    routeOverride = null;
    render("legacy");
    await settle();
    expect(latest.isUnavailable).toBe(true);
    expect(latest.isSettled).toBe(true);
    expect(getCachedSessionHistory(historyKey("legacy"))).toBeUndefined();
  });

  it("shows an unavailable state for failed history reads", async () => {
    fetchImpl = async () => ({ ok: false, json: async () => [] });
    mount("missing");
    await settle();
    expect(latest.isUnavailable).toBe(true);
    expect(latest.isSettled).toBe(true);
    expect(onLoaded.mock.calls.every(([messages]) => messages.length === 0)).toBe(true);
  });

  it("preserves platform admission denial handling when a history read is refused", async () => {
    const denied = vi.fn();
    const redirect = vi.spyOn(window.location, "replace").mockImplementation(() => {});
    window.addEventListener(platformAccessDenied, denied);
    fetchImpl = async () =>
      new Response(JSON.stringify({ detail: "platform_access_denied" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    try {
      mount("restricted");
      await act(async () => {
        await vi.waitFor(() => expect(redirect).toHaveBeenCalledWith("/platform-access-denied"));
      });
      expect(denied).toHaveBeenCalledTimes(1);
      expect(latest.isUnavailable).toBe(true);
      expect(latest.isSettled).toBe(true);
      expect(onLoaded.mock.calls.every(([messages]) => messages.length === 0)).toBe(true);
    } finally {
      window.removeEventListener(platformAccessDenied, denied);
      redirect.mockRestore();
    }
  });

  it("discards a history request when its route becomes unavailable", async () => {
    const response = deferred<ReturnType<typeof okResponse>>();
    fetchImpl = () => response.promise;
    mount("legacy");
    await settle();
    routeOverride = null;
    render("legacy");
    response.resolve(okResponse([msg("stale")]));
    await settle();
    expect(onLoaded.mock.calls.every(([messages]) => messages.length === 0)).toBe(true);
    expect(latest.isUnavailable).toBe(true);
  });
});

describe("sessionHistoryCache - bounded LRU", () => {
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

describe("sessionHistoryCache - per-tab persistence across a page refresh", () => {
  beforeEach(() => clearSessionHistoryCache());
  afterEach(() => vi.restoreAllMocks());

  it("an entry survives a reload: JS heap gone, sessionStorage kept", () => {
    setCachedSessionHistory("session-a", [msg("m1")]);
    dropInMemorySessionHistoryForTests(); // simulates F5
    expect(getCachedSessionHistory("session-a")).toEqual([msg("m1")]);
  });

  it("eviction removes the persisted copy too - the cap holds across reloads", () => {
    for (let i = 0; i < 21; i++) setCachedSessionHistory(`session-${i}`, [msg(`m${i}`)]);
    dropInMemorySessionHistoryForTests();
    expect(getCachedSessionHistory("session-0")).toBeUndefined(); // evicted from storage as well
    expect(getCachedSessionHistory("session-20")).toEqual([msg("m20")]);
  });

  it("a blocked or full sessionStorage degrades to in-memory only, without throwing", () => {
    // Replace the WHOLE global with a delegating fake. Patching the instance
    // (Object.defineProperty) or Storage.prototype no longer intercepts:
    // vitest's happy-dom serves sessionStorage through a proxy whose method
    // lookup ignores outside-defined own properties - defineProperty reports
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
