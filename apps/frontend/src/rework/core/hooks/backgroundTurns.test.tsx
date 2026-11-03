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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LiveTurn, PendingMessage, TurnStatus } from "./backgroundTurns";

const storageKey = "chat.background-indicators";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe("background indicator persistence", () => {
  let registry: typeof import("./backgroundTurns");
  let container: HTMLDivElement;
  let root: Root;
  let current: { status: TurnStatus; unread: boolean; queue: PendingMessage[] };

  beforeEach(async () => {
    sessionStorage.clear();
    vi.resetModules();
    registry = await import("./backgroundTurns");
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  function Probe({ id }: { id: string }) {
    const [queue] = registry.usePendingMessages(id);
    current = { status: registry.useTurnStatus(id), unread: registry.useSessionUnread(id), queue };
    return null;
  }
  function show(id: string) {
    act(() => root.render(<Probe id={id} />));
    return current;
  }
  async function reload() {
    act(() => root.unmount());
    vi.resetModules();
    registry = await import("./backgroundTurns");
    root = createRoot(container);
  }
  function turn(id: string, flags: Partial<LiveTurn> = {}): LiveTurn {
    return {
      sessionId: id,
      controller: new AbortController(),
      steeringTurnId: id,
      thoughts: new Map(),
      host: null,
      messages: [],
      completed: true,
      detachedCallbacks: {},
      ...flags,
    };
  }
  function finish(value: LiveTurn) {
    act(() => {
      registry.registerTurn(value);
      registry.settleTurn(value);
    });
  }

  it("restores known waiting and unread indicators without live turns, queues or notifications", async () => {
    finish(turn("waiting", { awaitingInput: true }));
    finish(turn("answer"));
    registry.registerTurn(turn("running"));
    const write = vi.spyOn(Storage.prototype, "setItem");
    registry.updatePendingMessages("answer", [{ id: "q", text: "private queued text", status: "waiting" }]);
    expect(write).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(storageKey)).not.toContain("private queued text");

    await reload();
    const settled = vi.fn();
    registry.subscribeBackgroundSettled(settled);
    expect(show("waiting")).toMatchObject({ status: "awaiting_input", unread: true });
    expect(show("answer")).toEqual({ status: null, unread: true, queue: [] });
    expect(show("running")).toEqual({ status: null, unread: false, queue: [] });
    expect(settled).not.toHaveBeenCalled();
  });

  it("persists read and history reconciliation independently for each conversation", async () => {
    finish(turn("waiting", { awaitingInput: true }));
    finish(turn("answer"));
    await reload();
    registry.markSessionRead("waiting");
    await reload();
    expect(show("waiting")).toMatchObject({ status: "awaiting_input", unread: false });
    act(() => registry.setSessionAwaitingInput("waiting", false));
    await reload();
    expect(show("waiting")).toMatchObject({ status: null, unread: false });
    expect(show("answer")).toMatchObject({ status: null, unread: true });
    act(() => registry.markSessionRead("answer"));
    expect(sessionStorage.getItem(storageKey)).toBeNull();
  });

  it("clears persisted waiting on a new turn and both indicators on Stop or deletion", async () => {
    finish(turn("new-turn", { awaitingInput: true }));
    finish(turn("deleted", { awaitingInput: true }));
    registry.markSessionRead("new-turn");
    registry.registerTurn(turn("new-turn"));
    registry.abortTurn("deleted");
    await reload();
    expect(show("new-turn")).toMatchObject({ status: null, unread: false });
    expect(show("deleted")).toMatchObject({ status: null, unread: false });
    expect(sessionStorage.getItem(storageKey)).toBeNull();
  });

  it.each(["incomplete", "interrupted", "cancelled"])(
    "does not persist an unread answer for a %s turn",
    async (outcome) => {
      const value = turn("failed", { completed: outcome !== "incomplete", interrupted: outcome === "interrupted" });
      if (outcome === "cancelled") value.controller.abort();
      finish(value);
      await reload();
      expect(show("failed")).toMatchObject({ status: null, unread: false });
    },
  );

  it.each(["invalid json", "null", "[]", '{"awaitingInput":true,"unread":{}}'])(
    "ignores malformed storage: %s",
    async (payload) => {
      sessionStorage.setItem(storageKey, payload);
      await reload();
      expect(show("unknown")).toMatchObject({ status: null, unread: false });
    },
  );

  it("filters invalid ids and bounds stored and restored indicators", async () => {
    for (let index = 0; index < 105; index++) registry.setSessionAwaitingInput(`waiting-${index}`, true);
    const stored = JSON.parse(sessionStorage.getItem(storageKey)!);
    expect(stored.awaitingInput).toHaveLength(100);
    expect(stored.awaitingInput[0]).toBe("waiting-5");
    sessionStorage.setItem(
      storageKey,
      JSON.stringify({
        awaitingInput: stored.awaitingInput,
        unread: [...Array.from({ length: 105 }, (_, index) => `answer-${index}`), null, 42],
      }),
    );
    await reload();
    expect(show("waiting-0").status).toBeNull();
    expect(show("waiting-104").status).toBe("awaiting_input");
    expect(show("answer-0").unread).toBe(false);
    expect(show("answer-104").unread).toBe(true);
    expect(show("42").unread).toBe(false);
    registry.setSessionAwaitingInput("waiting-104", false);
    const filtered = JSON.parse(sessionStorage.getItem(storageKey)!);
    expect(filtered.unread).toHaveLength(98);
    expect(filtered.unread.every((id: unknown) => typeof id === "string")).toBe(true);
  });

  it("keeps working in memory when browser storage is unavailable", async () => {
    for (const method of ["getItem", "setItem", "removeItem"] as const) {
      vi.spyOn(Storage.prototype, method).mockImplementation(() => {
        throw new Error("Storage blocked");
      });
    }
    await reload();
    finish(turn("waiting", { awaitingInput: true }));
    expect(show("waiting")).toMatchObject({ status: "awaiting_input", unread: true });
    act(() => {
      registry.markSessionRead("waiting");
      registry.setSessionAwaitingInput("waiting", false);
    });
    expect(current).toMatchObject({ status: null, unread: false });
  });
});
