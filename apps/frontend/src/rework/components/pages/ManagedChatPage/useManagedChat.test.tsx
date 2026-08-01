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

// Regression coverage for the context-prompt / session-write reliability
// finding, and its go-live consolidation pass. These tests drive
// `useManagedChat` through a minimal host component (no
// @testing-library/react in this repo) and assert the fixed contract:
//
// - session writes (row creation, context-prompt PATCH) are serialized per
//   session id — two concurrent PATCHes for the same session never race,
//   and a write for one session never blocks or is affected by another's;
// - `flushSessionWrites` is a stability loop, not a point-in-time snapshot —
//   a write enqueued WHILE the flush is already awaiting is also awaited;
// - a stale write's failure callback is generation-guarded: it can never
//   roll back a selection the user has already superseded with a newer one;
// - failures roll back the UI to the last durably-confirmed value, surface a
//   toast, and block send until an explicit, successful retry — without
//   ever double-sending;
// - `onTurnStarted` (not a fixed point before send() is even called) is what
//   actually clears composer input/attachments, so a later prepare-execution
//   failure can never wipe text/attachments the user still needs to retry.

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

// Reactive stand-in for react-router-dom's useSearchParams: bindSessionId
// must actually update `sessionId` across renders for the retry tests below
// (a retry re-reads `sessionId` from this, exactly like the real hook).
// `capturedSetSearchParams` additionally lets a test jump directly back to an
// arbitrary previously-visited sid (e.g. clicking a session in a sidebar) —
// something `startNewConversation()`/`handleSend()` alone can't simulate,
// since both only ever mint a brand-new sid, never rebind to an existing one.
let capturedSetSearchParams:
  | ((updater: URLSearchParams | ((prev: URLSearchParams) => URLSearchParams)) => void)
  | undefined;
vi.mock("react-router-dom", () => ({
  useSearchParams: () => {
    const [params, setParams] = useState(new URLSearchParams());
    const setSearchParams = (
      updater: URLSearchParams | ((prev: URLSearchParams) => URLSearchParams),
      _opts?: unknown,
    ) => {
      setParams((prev) => (typeof updater === "function" ? updater(prev) : updater));
    };
    capturedSetSearchParams = setSearchParams;
    return [params, setSearchParams] as const;
  },
}));

const showErrorMock = vi.fn();
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: showErrorMock, showSuccess: vi.fn() }),
}));

const notifyApiErrorMock = vi.fn();
vi.mock("@core/hooks/useApiErrorToast.ts", () => ({
  useApiErrorToast: () => ({ notifyApiError: notifyApiErrorMock }),
}));

// Every mocked hook below returns the SAME object/function references across
// renders (module-scoped, not recreated per call) — several of these values
// flow into useManagedChat's own useCallback/useEffect dependency arrays, and
// a fresh `vi.fn()` per render would make those deps look "changed" every
// render, re-firing the sessionId-change reset effect forever (observed as
// an OOM from an actual infinite render loop while writing this test).
const sendMock = vi.fn(async () => {});
const prepareChatControlsMock = vi.fn(async () => ({}));
const chatSseResetMock = vi.fn();
const sendHitlResumeMock = vi.fn();
const abortMock = vi.fn();
const replaceAllMessagesMock = vi.fn();
let capturedFlushPendingWrites: ((sid: string | null) => Promise<boolean>) | undefined;
let capturedOnTurnStarted: (() => void) | undefined;
vi.mock("@hooks/useChatSse", () => ({
  useChatSse: (params: {
    flushPendingWrites?: (sid: string | null) => Promise<boolean>;
    onTurnStarted?: () => void;
  }) => {
    capturedFlushPendingWrites = params.flushPendingWrites;
    capturedOnTurnStarted = params.onTurnStarted;
    return {
      messages: [],
      waitResponse: false,
      chatControls: [],
      prepareChatControls: prepareChatControlsMock,
      send: sendMock,
      sendHitlResume: sendHitlResumeMock,
      abort: abortMock,
      reset: chatSseResetMock,
      replaceAllMessages: replaceAllMessagesMock,
    };
  },
}));

const composerResetMock = vi.fn();
const composerValue = {
  searchPolicy: "corpus" as const,
  ragScope: "general" as const,
  selectedLibraryIds: [] as string[],
  selectedDocumentUids: [] as string[],
  setSearchPolicy: vi.fn(),
  setRagScope: vi.fn(),
  setSelectedLibraryIds: vi.fn(),
  setSelectedDocumentUids: vi.fn(),
  reset: composerResetMock,
};
vi.mock("./useComposerSettings", () => ({
  useComposerSettings: () => composerValue,
}));

const sessionHistoryValue = { isLoading: false };
vi.mock("./useSessionHistory", () => ({
  useSessionHistory: () => sessionHistoryValue,
}));

const chatAttachmentsValue = {
  attachments: [] as unknown[],
  persistedAttachments: [] as unknown[],
  isHydratingAttachments: false,
  attachmentsMarkdown: null as string | null,
  hasUploadingAttachments: false,
  addFiles: vi.fn(),
  removeAttachment: vi.fn(),
  deletePersistedAttachment: vi.fn(),
  clearReadyAttachments: vi.fn(),
};
vi.mock("./useChatAttachments", () => ({
  useChatAttachments: () => chatAttachmentsValue,
}));

// Controllable per-test mutation behavior — mirrors PromptsPage.test.tsx's
// pattern of mutable module-scoped state read inside the mock factory.
let registerSessionImpl: (args: unknown) => Promise<unknown> = async () => ({});
let patchSessionImpl: (args: unknown) => Promise<unknown> = async () => ({});
const registerSessionCalls: unknown[] = [];
const patchSessionCalls: unknown[] = [];
let sessionData: { context_prompt_ids?: string[]; title?: string } | undefined;
// True only for the regression test below modeling RTK Query's data/
// currentData divergence during a session switch (`data` reuses the last
// resolved result across an arg change; `currentData` doesn't). Every other
// test doesn't care about the distinction, so currentData mirrors data for
// them, unchanged.
let sessionDataIsStaleForCurrentArgs = false;

// Real RTK Query mutation triggers return a promise-like object that is
// BOTH directly catchable (`trigger(...).catch(...)`, used by
// touchSessionActivity) AND exposes `.unwrap()` (used everywhere else) —
// both must observe the same settlement, so `.unwrap` is attached directly
// onto the same promise instance rather than a separate wrapper object.
function mockMutationResult<T>(promise: Promise<T>): Promise<T> & { unwrap: () => Promise<T> } {
  const result = promise as Promise<T> & { unwrap: () => Promise<T> };
  result.unwrap = () => promise;
  return result;
}

// A promise whose settlement is controlled from outside, used to pin down
// exact ordering (e.g. "the second PATCH must not fire before the first
// settles") without guessing microtask-tick counts.
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery: () => ({ data: [] }),
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery: () => ({ data: [] }),
  useGetTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGetQuery: () => ({
    data: sessionData,
    currentData: sessionDataIsStaleForCurrentArgs ? undefined : sessionData,
  }),
  usePatchTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdPatchMutation: () => [
    (args: unknown) => {
      patchSessionCalls.push(args);
      return mockMutationResult(patchSessionImpl(args));
    },
    { isLoading: false },
  ],
  usePostTeamSessionControlPlaneV1TeamsTeamIdSessionsPostMutation: () => [
    (args: unknown) => {
      registerSessionCalls.push(args);
      return mockMutationResult(registerSessionImpl(args));
    },
    { isLoading: false },
  ],
}));

import { useManagedChat } from "./useManagedChat";

function TestHost({ onRender }: { onRender: (hook: ReturnType<typeof useManagedChat>) => void }) {
  const hook = useManagedChat({ teamId: "team-1", agentInstanceId: "agent-1" });
  onRender(hook);
  return null;
}

describe("useManagedChat — session write reliability", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: ReturnType<typeof useManagedChat>;

  const mount = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<TestHost onRender={(h) => (latest = h)} />);
    });
  };

  const rerender = () => {
    act(() => {
      root.render(<TestHost onRender={(h) => (latest = h)} />);
    });
  };

  const flush = async (sid: string | null) => {
    await act(async () => {
      await capturedFlushPendingWrites?.(sid);
    });
  };

  // `enqueueSessionWrite` chains onto the write tail with `.then()` — even
  // when the previous tail is ALREADY resolved, `.then()` still defers its
  // callback (here, the write's actual network call) to the next microtask,
  // never firing synchronously. One awaited `Promise.resolve()` is exactly
  // enough for that one link to run before the next assertion.
  const tick = async () => {
    await act(async () => {
      await Promise.resolve();
    });
  };

  beforeEach(() => {
    registerSessionImpl = async () => ({});
    patchSessionImpl = async () => ({});
    registerSessionCalls.length = 0;
    patchSessionCalls.length = 0;
    sessionData = undefined;
    sessionDataIsStaleForCurrentArgs = false;
    sendMock.mockClear();
    showErrorMock.mockClear();
    notifyApiErrorMock.mockClear();
    chatAttachmentsValue.clearReadyAttachments.mockClear();
    capturedFlushPendingWrites = undefined;
    capturedOnTurnStarted = undefined;
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    container.remove();
  });

  it("selecting a context prompt persists it and a send proceeds", async () => {
    mount();

    act(() => {
      latest.setContextPrompts(["p1"]);
    });
    expect(latest.contextPromptIds).toEqual(["p1"]);
    await flush(latest.sessionId);

    expect(registerSessionCalls).toHaveLength(1);
    expect(patchSessionCalls).toHaveLength(1);
    expect(notifyApiErrorMock).not.toHaveBeenCalled();

    act(() => {
      latest.setInput("hello");
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });

    expect(sendMock).toHaveBeenCalledTimes(1);
  });

  it("deselecting a context prompt persists the empty selection", async () => {
    mount();
    act(() => {
      latest.setContextPrompts(["p1"]);
    });
    await flush(latest.sessionId);
    expect(latest.contextPromptIds).toEqual(["p1"]);

    act(() => {
      latest.setContextPrompts([]);
    });
    expect(latest.contextPromptIds).toEqual([]);
    await flush(latest.sessionId);

    expect(notifyApiErrorMock).not.toHaveBeenCalled();
  });

  it("rolls back the selection and surfaces a toast when the PATCH fails", async () => {
    mount();
    act(() => {
      latest.setContextPrompts(["p1"]);
    });
    await flush(latest.sessionId);
    expect(latest.contextPromptIds).toEqual(["p1"]);

    patchSessionImpl = async () => {
      throw new Error("network down");
    };

    act(() => {
      latest.setContextPrompts(["p1", "p2"]);
    });
    // Optimistic value shown immediately.
    expect(latest.contextPromptIds).toEqual(["p1", "p2"]);

    await flush(latest.sessionId);
    rerender();

    expect(latest.contextPromptIds).toEqual(["p1"]); // rolled back
    expect(notifyApiErrorMock).toHaveBeenCalledTimes(1);
  });

  it("blocks send while a context-prompt PATCH is still failing, then allows a clean retry with no duplicate send", async () => {
    sessionData = { context_prompt_ids: [] };
    mount();

    patchSessionImpl = async () => {
      throw new Error("save failed");
    };

    act(() => {
      latest.setContextPrompts(["p1"]);
    });
    act(() => {
      latest.setInput("hello");
    });
    rerender();

    await act(async () => {
      await latest.handleSend();
    });

    expect(sendMock).not.toHaveBeenCalled();
    rerender();
    expect(latest.contextPromptIds).toEqual([]); // rolled back, not left showing "p1"
    expect(latest.input).toBe("hello"); // preserved for retry

    // Explicit retry: this time the PATCH succeeds, and the message is sent
    // exactly once — no duplicate from the earlier blocked attempt.
    patchSessionImpl = async () => ({});
    act(() => {
      latest.setContextPrompts(["p1"]);
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });

    expect(sendMock).toHaveBeenCalledTimes(1);
  });

  it("blocks send when session creation fails, with no send and the message preserved", async () => {
    mount();
    registerSessionImpl = async () => {
      throw new Error("could not create session");
    };
    act(() => {
      latest.setInput("first message");
    });
    rerender();

    await act(async () => {
      await latest.handleSend();
    });

    expect(sendMock).not.toHaveBeenCalled();
    expect(notifyApiErrorMock).toHaveBeenCalledTimes(1);
    rerender();
    expect(latest.input).toBe("first message"); // not cleared — retry keeps the text
  });

  it("retries session creation for the same bound sid after a prior failure, without double-sending", async () => {
    mount();
    registerSessionImpl = async () => {
      throw new Error("transient failure");
    };
    act(() => {
      latest.setInput("hello");
    });
    rerender();

    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).not.toHaveBeenCalled();
    expect(registerSessionCalls).toHaveLength(1);

    // Retry: the sid stayed bound to the URL from the failed attempt above —
    // creation must fire again for that same sid, not be silently skipped.
    registerSessionImpl = async () => ({});
    rerender();
    await act(async () => {
      await latest.handleSend();
    });

    expect(registerSessionCalls).toHaveLength(2);
    expect(sendMock).toHaveBeenCalledTimes(1);
  });

  it("two concurrently-failing new sessions can each be retried independently", async () => {
    // Regression test: sessionCreateFailedIdRef used to be a single scalar
    // shared across ALL sessions — session B's failure silently overwrote
    // session A's, so returning to A skipped retrying its creation
    // (needsCreate false) while A's write tail stayed permanently failed,
    // making it unsendable forever. Fixed by keying it per sid, like
    // writeTailsRef.
    mount();
    registerSessionImpl = async () => {
      throw new Error("transient failure");
    };

    // Session A: creation fails.
    act(() => {
      latest.setInput("message for A");
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).not.toHaveBeenCalled();
    const sidA = latest.sessionId;
    expect(sidA).not.toBeNull();
    expect(registerSessionCalls).toHaveLength(1);

    // Navigate away and start session B — its creation ALSO fails, while the
    // impl is still throwing.
    act(() => {
      latest.startNewConversation();
    });
    act(() => {
      latest.setInput("message for B");
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).not.toHaveBeenCalled();
    const sidB = latest.sessionId;
    expect(sidB).not.toBeNull();
    expect(sidB).not.toBe(sidA);
    expect(registerSessionCalls).toHaveLength(2);

    // The transient failure has cleared — creation succeeds going forward.
    registerSessionImpl = async () => ({});

    // Navigate directly back to session A (e.g. clicking it in a sidebar) —
    // not via startNewConversation, which would mint an unrelated third sid.
    act(() => {
      capturedSetSearchParams?.(new URLSearchParams({ session: sidA! }));
    });
    rerender();
    expect(latest.sessionId).toBe(sidA);

    act(() => {
      latest.setInput("retry for A");
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });

    // A's earlier failure must still be remembered independently of B's:
    // creation is retried (a 3rd registerSession call, for sid A again), and
    // the retried send actually goes through.
    expect(registerSessionCalls).toHaveLength(3);
    expect(sendMock).toHaveBeenCalledTimes(1);
  });

  it("rehydrates the persisted context-prompt selection on reload", async () => {
    sessionData = undefined;
    mount();
    expect(latest.contextPromptIds).toEqual([]);

    // Bind a session without making any local context-prompt mutation —
    // e.g. dropping an attachment, or (in the real app) simply loading a
    // page that already carries `?session=...` in the URL. Rehydration must
    // still apply normally in this case: no local mutation has happened yet.
    act(() => {
      latest.handleAddAttachments([], "picker");
    });
    rerender();
    expect(latest.sessionId).not.toBeNull();

    // Simulate a reload: the session query now resolves with the
    // previously-saved selection.
    sessionData = { context_prompt_ids: ["p1", "p2"] };
    rerender();

    expect(latest.contextPromptIds).toEqual(["p1", "p2"]);
  });

  it("échec de préparation: onTurnStarted clears input and ready attachments only once actually invoked", async () => {
    mount();
    act(() => {
      latest.setInput("typed text");
    });
    rerender();
    expect(latest.input).toBe("typed text");

    // Simulates useChatSse aborting BEFORE the turn starts (flush or
    // prepare-execution failure) — onTurnStarted is simply never called;
    // nothing here should have touched input or attachments.
    expect(chatAttachmentsValue.clearReadyAttachments).not.toHaveBeenCalled();
    expect(latest.input).toBe("typed text");

    // Only once the turn genuinely starts does the composer clear.
    act(() => {
      capturedOnTurnStarted?.();
    });
    rerender();

    expect(latest.input).toBe("");
    expect(chatAttachmentsValue.clearReadyAttachments).toHaveBeenCalledTimes(1);
  });

  it("serializes two rapid context-prompt selections — the second PATCH is not sent before the first settles", async () => {
    sessionData = { context_prompt_ids: [] };
    mount();
    // Establish a bound, already-created session first — this test is about
    // PATCH-to-PATCH ordering specifically, not the creation-then-PATCH
    // chaining already covered elsewhere.
    act(() => {
      latest.setContextPrompts([]);
    });
    await flush(latest.sessionId);
    patchSessionCalls.length = 0;

    const first = deferred<unknown>();
    patchSessionImpl = () => first.promise;

    act(() => {
      latest.setContextPrompts(["A"]);
    });
    await tick();
    const sid = latest.sessionId;
    expect(patchSessionCalls).toHaveLength(1);

    patchSessionImpl = async () => ({});
    act(() => {
      latest.setContextPrompts(["A", "B"]);
    });
    await tick();
    // Queued behind the still-pending first PATCH — not dispatched yet.
    expect(patchSessionCalls).toHaveLength(1);

    const flushPromise = flush(sid);
    first.resolve({});
    await flushPromise;

    expect(patchSessionCalls).toHaveLength(2);
    expect(latest.contextPromptIds).toEqual(["A", "B"]);
  });

  it("succès A puis succès B: UI and server end up with B", async () => {
    sessionData = { context_prompt_ids: [] };
    mount();

    act(() => {
      latest.setContextPrompts(["A"]);
    });
    await flush(latest.sessionId);
    act(() => {
      latest.setContextPrompts(["B"]);
    });
    await flush(latest.sessionId);

    expect(latest.contextPromptIds).toEqual(["B"]);
    expect(patchSessionCalls).toHaveLength(2);
    expect(notifyApiErrorMock).not.toHaveBeenCalled();
  });

  it("échec A puis succès B: B's success is not undone by A's later-observed (but stale) failure", async () => {
    sessionData = { context_prompt_ids: ["base"] };
    mount();
    act(() => {
      latest.setContextPrompts(["base"]);
    });
    await flush(latest.sessionId);
    patchSessionCalls.length = 0;

    const a = deferred<unknown>();
    patchSessionImpl = () => a.promise;
    act(() => {
      latest.setContextPrompts(["A"]);
    });
    await tick();
    const sid = latest.sessionId;
    expect(patchSessionCalls).toHaveLength(1);

    patchSessionImpl = async () => ({});
    act(() => {
      latest.setContextPrompts(["B"]);
    });
    await tick();
    expect(patchSessionCalls).toHaveLength(1); // B queued behind A

    const flushPromise = flush(sid);
    a.reject(new Error("A failed"));
    await flushPromise;
    rerender();

    expect(patchSessionCalls).toHaveLength(2); // B's write fired once A settled
    expect(latest.contextPromptIds).toEqual(["B"]); // never reverted to "base"
    // A's failure is stale by the time it resolves (B already superseded it):
    // no rollback, no toast for a selection the user has already moved past.
    expect(notifyApiErrorMock).not.toHaveBeenCalled();
  });

  it("succès A puis échec B: rolls back to A, not to whatever preceded A", async () => {
    sessionData = { context_prompt_ids: ["base"] };
    mount();

    act(() => {
      latest.setContextPrompts(["A"]);
    });
    await flush(latest.sessionId);
    expect(latest.contextPromptIds).toEqual(["A"]);

    patchSessionImpl = async () => {
      throw new Error("B failed");
    };
    act(() => {
      latest.setContextPrompts(["B"]);
    });
    expect(latest.contextPromptIds).toEqual(["B"]); // optimistic
    await flush(latest.sessionId);
    rerender();

    expect(latest.contextPromptIds).toEqual(["A"]); // rolled back to A, not "base"
    expect(notifyApiErrorMock).toHaveBeenCalledTimes(1);
  });

  it("flushSessionWrites waits for a write enqueued while it is already awaiting (stability loop)", async () => {
    sessionData = { context_prompt_ids: [] };
    mount();
    act(() => {
      latest.setContextPrompts([]);
    });
    await flush(latest.sessionId);
    patchSessionCalls.length = 0;

    const first = deferred<unknown>();
    const second = deferred<unknown>();
    const impls = [() => first.promise, () => second.promise];
    patchSessionImpl = () => impls.shift()!();

    act(() => {
      latest.setContextPrompts(["A"]);
    });
    await tick();
    const sid = latest.sessionId;
    expect(patchSessionCalls).toHaveLength(1);

    let flushResolvedTo: boolean | "pending" = "pending";
    const flushPromise = capturedFlushPendingWrites!(sid).then((ok) => {
      flushResolvedTo = ok;
      return ok;
    });

    // A second write for the SAME session is enqueued while the flush above
    // is still awaiting the first, unsettled one.
    act(() => {
      latest.setContextPrompts(["A", "B"]);
    });
    await tick();
    expect(patchSessionCalls).toHaveLength(1); // B queued, not dispatched yet

    // Settle A: B's network call fires next, but the flush must not resolve
    // yet — it has to notice and wait for B too.
    await act(async () => {
      first.resolve({});
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(patchSessionCalls).toHaveLength(2);
    expect(flushResolvedTo).toBe("pending");

    // Only once B also settles does the flush resolve.
    await act(async () => {
      second.resolve({});
      await flushPromise;
    });
    expect(flushResolvedTo).toBe(true);
  });

  it("handleSend never calls send() until the write queue is fully stable, even if a write is added mid-flush", async () => {
    sessionData = { context_prompt_ids: [] };
    mount();
    act(() => {
      latest.setContextPrompts([]);
    });
    await flush(latest.sessionId);

    const first = deferred<unknown>();
    patchSessionImpl = () => first.promise;
    act(() => {
      latest.setContextPrompts(["A"]);
    });
    act(() => {
      latest.setInput("hello");
    });
    rerender();

    // Deliberately NOT wrapped in `act()`: with the session already
    // established above, `handleSend()` performs no synchronous state
    // update before its own first `await` (it goes straight into awaiting
    // the flush), so there is nothing here for `act()` to batch. Keeping an
    // async `act()` scope open (unawaited) while other `act()` calls run
    // below is an unsupported, overlapping-scope pattern that was observed
    // to corrupt React's act tracking badly enough to leak state into a
    // LATER, unrelated test.
    const handleSendPromise = latest.handleSend();

    const second = deferred<unknown>();
    await act(async () => {
      patchSessionImpl = () => second.promise;
      latest.setContextPrompts(["A", "B"]);
      await Promise.resolve();
    });
    expect(sendMock).not.toHaveBeenCalled();

    await act(async () => {
      first.resolve({});
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(sendMock).not.toHaveBeenCalled(); // still waiting on B

    await act(async () => {
      second.resolve({});
      await handleSendPromise;
    });

    expect(sendMock).toHaveBeenCalledTimes(1);
  });

  it("does not let a failed session-creation from a previous session contaminate a newly navigated-to session", async () => {
    mount();
    registerSessionImpl = async () => {
      throw new Error("create failed for session A");
    };
    act(() => {
      latest.setInput("first");
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).not.toHaveBeenCalled();
    const sidA = latest.sessionId;
    expect(sidA).not.toBeNull();

    // Navigate away — this unbinds the session id (e.g. "New conversation").
    act(() => {
      latest.startNewConversation();
    });
    expect(latest.sessionId).toBeNull();

    // A brand-new session is created for the new conversation (a different
    // sid) and this time creation succeeds — it must not be blocked or
    // affected by session A's earlier rejected write tail.
    registerSessionImpl = async () => ({});
    act(() => {
      latest.setInput("second");
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });

    const sidB = latest.sessionId;
    expect(sidB).not.toBeNull();
    expect(sidB).not.toBe(sidA);
    expect(sendMock).toHaveBeenCalledTimes(1);
  });

  it("PATCH A pending, navigation to B, then A fails → B's UI is unaffected", async () => {
    mount();

    // Establish session A with a deliberately still-pending PATCH.
    const aPatch = deferred<unknown>();
    patchSessionImpl = () => aPatch.promise;
    act(() => {
      latest.setContextPrompts(["pA"]);
    });
    const sidA = latest.sessionId;
    expect(sidA).not.toBeNull();
    // Let A's own PATCH action actually fire (consuming `aPatch.promise`)
    // BEFORE the mock impl is reassigned for session B below — otherwise
    // A's write ends up using B's (later) impl instead, and `aPatch.promise`
    // is never actually consumed by anything.
    await tick();
    await tick();
    expect(patchSessionCalls).toHaveLength(1);

    // Navigate away — a genuine "enter a new session" transition (not a
    // handleSend-driven bind), so the reset effect runs normally.
    act(() => {
      latest.startNewConversation();
    });
    expect(latest.sessionId).toBeNull();

    // Session B gets its own successful selection.
    patchSessionImpl = async () => ({});
    act(() => {
      latest.setContextPrompts(["pB"]);
    });
    const sidB = latest.sessionId;
    expect(sidB).not.toBeNull();
    expect(sidB).not.toBe(sidA);
    await flush(sidB);
    expect(latest.contextPromptIds).toEqual(["pB"]);

    // A's long-pending PATCH finally fails, well after the user moved on.
    aPatch.reject(new Error("A failed after navigation"));
    await flush(sidA);

    // B's UI must be completely unaffected: no rollback to A's value, no
    // toast shown in B's context for a session the user no longer sees.
    expect(latest.contextPromptIds).toEqual(["pB"]);
    expect(notifyApiErrorMock).not.toHaveBeenCalled();
  });

  it("PATCH A pending, navigation to B, then A succeeds → B's confirmation is unaffected", async () => {
    mount();

    const aPatch = deferred<unknown>();
    patchSessionImpl = () => aPatch.promise;
    act(() => {
      latest.setContextPrompts(["pA"]);
    });
    const sidA = latest.sessionId;
    // Let A's own PATCH action actually fire before the mock impl is
    // reassigned for session B below — see the sibling test above.
    await tick();
    await tick();
    expect(patchSessionCalls).toHaveLength(1);

    act(() => {
      latest.startNewConversation();
    });

    patchSessionImpl = async () => ({});
    act(() => {
      latest.setContextPrompts(["pB"]);
    });
    const sidB = latest.sessionId;
    await flush(sidB);
    expect(latest.contextPromptIds).toEqual(["pB"]);

    // A's long-pending PATCH finally succeeds — after the user already
    // moved on to B. A's own write completing normally server-side must not
    // leak into B's UI.
    aPatch.resolve({});
    await flush(sidA);

    expect(latest.contextPromptIds).toEqual(["pB"]);
    expect(notifyApiErrorMock).not.toHaveBeenCalled();
  });

  it("an optimistic selection survives a stale sessionData snapshot arriving afterward", async () => {
    sessionData = undefined;
    mount();

    // Bind a session with no local mutation yet, so initial rehydration applies.
    act(() => {
      latest.handleAddAttachments([], "picker");
    });
    rerender();
    const sid = latest.sessionId;
    expect(sid).not.toBeNull();

    sessionData = { context_prompt_ids: ["old"] };
    rerender();
    expect(latest.contextPromptIds).toEqual(["old"]);

    // A local mutation, with its PATCH deliberately left pending.
    const pending = deferred<unknown>();
    patchSessionImpl = () => pending.promise;
    act(() => {
      latest.setContextPrompts(["new"]);
    });
    expect(latest.contextPromptIds).toEqual(["new"]);

    // A stale sessionData snapshot (a slow initial fetch, or a refetch that
    // started before the local mutation) resolves now, AFTER the local
    // mutation was already made.
    sessionData = { context_prompt_ids: ["old"] };
    rerender();

    // The optimistic (still-pending) local selection must survive — never
    // silently replaced by the older server snapshot.
    expect(latest.contextPromptIds).toEqual(["new"]);

    pending.resolve({});
    await flush(sid);
    expect(latest.contextPromptIds).toEqual(["new"]);
  });

  it("navigating to a genuinely new session re-enables normal rehydration", async () => {
    mount();

    // Session A: a local mutation happens, disabling further rehydration for A.
    act(() => {
      latest.setContextPrompts(["pA"]);
    });
    await flush(latest.sessionId);

    // Navigate to a new session B — a real transition, not a handleSend bind.
    act(() => {
      latest.startNewConversation();
    });
    expect(latest.contextPromptIds).toEqual([]);

    act(() => {
      latest.handleAddAttachments([], "picker");
    });
    rerender();
    const sidB = latest.sessionId;
    expect(sidB).not.toBeNull();

    // B has no local mutation yet — a fresh server snapshot for B must apply
    // normally, exactly like a first-time session entry.
    sessionData = { context_prompt_ids: ["pB-from-server"] };
    rerender();
    expect(latest.contextPromptIds).toEqual(["pB-from-server"]);
  });

  it("does not attribute session A's reused (stale) sessionData to session B while B's query is still resolving", async () => {
    // Regression test: RTK Query's `data` deliberately reuses the last
    // resolved result across an arg change (here, a session switch) while
    // the new args' request is still in flight — `sessionDataIsStaleForCurrentArgs`
    // models exactly that. The fix reads `currentData` instead, which stays
    // undefined until the result genuinely belongs to the new session.
    mount();

    // Bind and enter session A.
    act(() => {
      latest.handleAddAttachments([], "picker");
    });
    rerender();
    const sidA = latest.sessionId;
    expect(sidA).not.toBeNull();

    // A's server snapshot resolves normally.
    sessionData = { context_prompt_ids: ["pA-from-server"] };
    rerender();
    expect(latest.contextPromptIds).toEqual(["pA-from-server"]);

    // Navigate to a new session B — a real transition, not a handleSend bind.
    act(() => {
      latest.startNewConversation();
    });
    expect(latest.contextPromptIds).toEqual([]);

    // B's own query hasn't resolved yet — set this BEFORE the render where
    // sessionId actually flips to B, so the race is captured at the exact
    // render where they first interact: `data` still reflects A's payload
    // (the real-world RTK Query behavior), but `currentData` correctly does
    // not.
    sessionDataIsStaleForCurrentArgs = true;
    act(() => {
      latest.handleAddAttachments([], "picker");
    });
    rerender();
    const sidB = latest.sessionId;
    expect(sidB).not.toBeNull();
    expect(sidB).not.toBe(sidA);
    // Must NOT inherit A's prompts under B's session id.
    expect(latest.contextPromptIds).toEqual([]);

    // B's real snapshot finally arrives.
    sessionDataIsStaleForCurrentArgs = false;
    sessionData = { context_prompt_ids: ["pB-from-server"] };
    rerender();
    expect(latest.contextPromptIds).toEqual(["pB-from-server"]);
  });

  it("handleSend() called twice while session creation is suspended: one sid, one creation, one bind, one send", async () => {
    mount();
    const create = deferred<unknown>();
    registerSessionImpl = () => create.promise;
    act(() => {
      latest.setInput("hello");
    });
    rerender();

    // Two rapid handleSend() calls, back to back, before the first has any
    // chance to resolve its own await — mirrors a double Enter. Deliberately
    // NOT each wrapped in their own act(): keeping an async act() scope open
    // while a second, separate act() call runs before the first is awaited
    // is an unsupported, overlapping-scope pattern (see the note on this
    // elsewhere in this file and in useChatSse.test.tsx).
    const first = latest.handleSend();
    const second = latest.handleSend();

    await act(async () => {
      create.resolve({});
      await Promise.all([first, second]);
    });

    // The second call was dropped outright by handleSend's own reentrancy
    // guard, acquired synchronously before flushSessionWrites is ever
    // awaited — it never generated its own session id, never called
    // bindSessionId, and never created a session row of its own.
    expect(registerSessionCalls).toHaveLength(1);
    expect(sendMock).toHaveBeenCalledTimes(1);
    rerender();
    expect(latest.sessionId).not.toBeNull();
  });
});
