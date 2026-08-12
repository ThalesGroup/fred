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

// Regression coverage for `send()`'s ordering barrier, preflight reentrancy
// lock, and composer-safety contract:
//
// 1. `flushPendingWrites` returning `false` (a tracked session write failed)
//    must abort BEFORE prepare-execution is ever called — previously this
//    barrier only awaited void and could never observe a failure.
// 2. `prepareExecution(...).unwrap()` was not wrapped in try/catch — a
//    rejection (e.g. control-plane now rejecting a foreign/unknown
//    session_id — see the prepare_execution ownership-check fix) propagated
//    as an unhandled promise rejection: no toast, `waitResponse` never set,
//    the composer looked idle with no sign the message never sent.
// 3. `onTurnStarted` (the caller's cue to clear composer input/attachments)
//    must fire if and only if the turn actually starts — never on a flush
//    failure or a prepare-execution rejection, always once prep succeeds,
//    exactly once even across a failed-then-retried attempt.
// 4. A synchronous reentrancy lock, held from before the first await through
//    onTurnStarted, guarantees at most one prepare-execution in flight at a
//    time — a second Enter fired during preflight is dropped outright, not
//    turned into a cancel/replace (that behavior stays reserved for a
//    send() arriving once streaming has actually begun). An external
//    abort() during preflight must still let the in-flight call notice and
//    bail before onTurnStarted, and must release the lock so a subsequent
//    Send is not permanently blocked.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A promise whose settlement is controlled from outside — used to pin down
// exact ordering (e.g. "still preflighting when a second send() arrives")
// without guessing microtask-tick counts.
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const dispatchMock = vi.fn();
vi.mock("react-redux", () => ({
  useDispatch: () => dispatchMock,
}));

// Fixed UI locale so language-forwarding tests are deterministic — no other
// test in this file inspects request bodies, so a fixed value here is safe.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ i18n: { language: "fr-FR" } }),
}));

vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: {
    ensureFreshToken: vi.fn(async () => true),
    // Consulted only when ensureFreshToken resolves false. Mocked (not omitted)
    // so the refusal branch runs the real comparison instead of dying on
    // "GetTokenSecondsLeft is not a function" — the default is comfortably
    // above TURN_TOKEN_HARD_FLOOR_S so existing tests are unaffected.
    GetTokenSecondsLeft: vi.fn((): number | null => 3600),
    GetToken: () => "test-token",
    GetUserId: () => "user-1",
  },
}));

import { KeyCloakService } from "../../../security/KeycloakService";

let prepareExecutionImpl: (args: unknown) => Promise<unknown> = async () => ({
  execute_stream_url: "http://runtime.test/execute_stream",
  chat_controls: [],
  capability_base_urls: {},
});
const prepareExecutionCalls: unknown[] = [];

function mockMutationResult<T>(promise: Promise<T>): Promise<T> & { unwrap: () => Promise<T> } {
  const result = promise as Promise<T> & { unwrap: () => Promise<T> };
  result.unwrap = () => promise;
  return result;
}

vi.mock("../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  usePostPrepareExecutionControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPrepareExecutionPostMutation: () => [
    (args: unknown) => {
      prepareExecutionCalls.push(args);
      return mockMutationResult(prepareExecutionImpl(args));
    },
    { isLoading: false },
  ],
}));

import { useChatSse } from "./useChatSse";
import type { RuntimeAwaitingHumanEvent } from "./useChatSse";

function TestHost({ onRender }: { onRender: (hook: ReturnType<typeof useChatSse>) => void }) {
  const hook = useChatSse({
    agentInstanceId: "agent-1",
    teamId: "team-1",
    flushPendingWrites,
    onError: (msg) => onErrorMock(msg),
    onTurnStarted: () => onTurnStartedMock(),
  });
  onRender(hook);
  return null;
}

let flushPendingWrites: ((sessionId: string) => Promise<boolean>) | undefined;
const onErrorMock = vi.fn();
const onTurnStartedMock = vi.fn();

describe("useChatSse — send() ordering barrier and prepare-execution failure handling", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: ReturnType<typeof useChatSse>;

  const mount = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<TestHost onRender={(h) => (latest = h)} />);
    });
  };

  beforeEach(() => {
    flushPendingWrites = undefined;
    onErrorMock.mockClear();
    onTurnStartedMock.mockClear();
    dispatchMock.mockClear();
    prepareExecutionCalls.length = 0;
    prepareExecutionImpl = async () => ({
      execute_stream_url: "http://runtime.test/execute_stream",
      chat_controls: [],
      capability_base_urls: {},
    });
    // Reset the shared KeyCloakService mocks, including any queued
    // `...Once` values: without this an unconsumed queue entry leaks into the
    // next test and makes ordering load-bearing.
    vi.mocked(KeyCloakService.ensureFreshToken).mockReset();
    vi.mocked(KeyCloakService.ensureFreshToken).mockResolvedValue(true);
    vi.mocked(KeyCloakService.GetTokenSecondsLeft).mockReset();
    vi.mocked(KeyCloakService.GetTokenSecondsLeft).mockReturnValue(3600);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("never calls prepare-execution when the write barrier reports a failure", async () => {
    flushPendingWrites = async () => false;
    mount();

    await act(async () => {
      await latest.send("hello", "session-1");
    });

    expect(prepareExecutionCalls).toHaveLength(0);
    expect(latest.waitResponse).toBe(false);
    // The turn never started — the caller must not clear composer state.
    expect(onTurnStartedMock).not.toHaveBeenCalled();
  });

  it("passes the target session id to the write barrier", async () => {
    const seenSids: unknown[] = [];
    flushPendingWrites = async (sid: string) => {
      seenSids.push(sid);
      return true;
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();

    await act(async () => {
      await latest.send("hello", "session-42");
    });

    expect(seenSids).toEqual(["session-42"]);
    fetchSpy.mockRestore();
  });

  it("calls prepare-execution and fires onTurnStarted exactly once when the write barrier reports success", async () => {
    flushPendingWrites = async () => true;
    // The stream fetch itself is irrelevant to this assertion — let it fail
    // fast rather than hang, `send()` swallows streaming errors via onError.
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();

    await act(async () => {
      await latest.send("hello", "session-1");
    });

    expect(prepareExecutionCalls).toHaveLength(1);
    // The turn genuinely started (prep succeeded) — even though the stream
    // itself then failed, that is a later, separate concern (onError), not
    // a reason to have skipped clearing the composer.
    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });

  it("surfaces onError, never throws, and never fires onTurnStarted when prepare-execution itself rejects", async () => {
    flushPendingWrites = async () => true;
    prepareExecutionImpl = async () => {
      throw new Error("Session is not usable for this execution.");
    };
    mount();

    // Must resolve cleanly (not reject) — this is the exact bug: an
    // unguarded `await prepareExecution(...).unwrap()` used to leave this
    // promise rejecting with no caller ever catching it.
    await expect(
      act(async () => {
        await latest.send("hello", "session-1");
      }),
    ).resolves.toBeUndefined();

    expect(onErrorMock).toHaveBeenCalledTimes(1);
    expect(onErrorMock.mock.calls[0][0]).toContain("Session is not usable for this execution.");
    expect(latest.waitResponse).toBe(false);
    // The turn never started — composer input/attachments must survive so a
    // retry doesn't force the user to retype.
    expect(onTurnStartedMock).not.toHaveBeenCalled();
  });

  it("a retry after a prepare-execution failure starts exactly one turn", async () => {
    flushPendingWrites = async () => true;
    prepareExecutionImpl = async () => {
      throw new Error("transient 503");
    };
    mount();

    await act(async () => {
      await latest.send("hello", "session-1");
    });
    expect(onTurnStartedMock).not.toHaveBeenCalled();
    expect(onErrorMock).toHaveBeenCalledTimes(1);

    // Explicit retry: this time prepare-execution succeeds.
    prepareExecutionImpl = async () => ({
      execute_stream_url: "http://runtime.test/execute_stream",
      chat_controls: [],
      capability_base_urls: {},
    });
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));

    await act(async () => {
      await latest.send("hello", "session-1");
    });

    // Exactly one turn actually started across both attempts — no duplicate
    // from the first, failed attempt. The lock was released on the earlier
    // failure — otherwise this second attempt would never have reached
    // prepare-execution at all.
    expect(prepareExecutionCalls).toHaveLength(2);
    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });

  it("double Enter during prepare-execution: only one prepare-execution and one turn", async () => {
    flushPendingWrites = async () => true;
    const prep = deferred<unknown>();
    prepareExecutionImpl = () => prep.promise;
    mount();

    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));

    // Everything inside ONE act() scope: two overlapping, unawaited async
    // act() calls left dangling work that leaked into a LATER, unrelated
    // test in an earlier version of this suite (see useManagedChat.test.tsx
    // for the writeup) — React's act() tracking does not support nested/
    // overlapping open scopes. Calling send() directly (not each wrapped in
    // its own act()) avoids that entirely.
    await act(async () => {
      // Two Enters fired back to back, before prepare-execution has settled.
      const firstSend = latest.send("hello", "session-1");
      const secondSend = latest.send("hello", "session-1");
      prep.resolve({
        execute_stream_url: "http://runtime.test/execute_stream",
        chat_controls: [],
        capability_base_urls: {},
      });
      await Promise.all([firstSend, secondSend]);
    });

    // Only the first call's preflight ever reached prepare-execution — the
    // second was dropped outright, not queued/merged/replacing the first.
    expect(prepareExecutionCalls).toHaveLength(1);
    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });

  it("cancellation during prepare-execution: onTurnStarted never fires, and a later Send is not blocked", async () => {
    flushPendingWrites = async () => true;
    const prep = deferred<unknown>();
    prepareExecutionImpl = () => prep.promise;
    mount();

    await act(async () => {
      const sendPromise = latest.send("hello", "session-1");
      // The user clicks Stop while prepare-execution is still pending.
      latest.abort();
      // The network reply arrives late, after cancellation.
      prep.resolve({
        execute_stream_url: "http://runtime.test/execute_stream",
        chat_controls: [],
        capability_base_urls: {},
      });
      await sendPromise;
    });

    expect(onTurnStartedMock).not.toHaveBeenCalled();
    expect(latest.messages).toHaveLength(0); // no optimistic bubble created
    expect(latest.waitResponse).toBe(false);

    // The lock must not be stuck — a subsequent Send proceeds normally.
    prepareExecutionImpl = async () => ({
      execute_stream_url: "http://runtime.test/execute_stream",
      chat_controls: [],
      capability_base_urls: {},
    });
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    await act(async () => {
      await latest.send("hello", "session-1");
    });

    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });

  it("a stale, aborted attempt's late resumption never releases a later attempt's lock — a third send is still ignored, and the later attempt starts exactly one turn", async () => {
    flushPendingWrites = async () => true;
    const prep = deferred<unknown>();
    prepareExecutionImpl = () => prep.promise;
    mount();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));

    await act(async () => {
      // A starts preflighting.
      const sendA = latest.send("hello", "session-1");
      // The user hits Stop before A's own await (token refresh) has even
      // settled — A is cancelled mid-flight, well before reaching
      // prepare-execution.
      latest.abort();
      // B starts immediately after — the lock was freed by abort(), so B
      // becomes the new owner.
      const sendB = latest.send("hello", "session-1");
      // Let A's suspended continuation resume and run its own cleanup. It
      // must be a complete no-op on B's lock/abortRef/waitResponse.
      await sendA;

      // A third send, fired right now while B is still preflighting (not
      // yet reached prepare-execution), is still dropped outright — proving
      // A's stale cleanup did not free B's slot.
      const sendC = latest.send("hello", "session-1");
      await sendC;

      // B's prepare-execution reply finally arrives.
      prep.resolve({
        execute_stream_url: "http://runtime.test/execute_stream",
        chat_controls: [],
        capability_base_urls: {},
      });
      await sendB;
    });

    // Exactly one prepare-execution call: A never reached it (aborted
    // first), and C was dropped by the still-held lock — only B's own call
    // remains.
    expect(prepareExecutionCalls).toHaveLength(1);
    // Only B's turn ever actually started.
    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    expect(latest.messages).toHaveLength(1);
    expect(latest.waitResponse).toBe(false);
    fetchSpy.mockRestore();
  });

  it("sendHitlResume taking over from a preflighting send() frees the lock immediately — a later send is not blocked", async () => {
    // Regression test: sendHitlResume used to reassign abortRef without
    // touching preflightOwnerRef, so a send() it superseded stayed the
    // lock's "owner" until its own stale continuation happened to resume —
    // which could be arbitrarily late, silently dropping any send() fired
    // in the meantime.
    flushPendingWrites = async () => true;
    mount();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));

    const pendingHitl: RuntimeAwaitingHumanEvent = {
      type: "awaiting_human",
      session_id: "session-1",
      exchange_id: "exch-1",
      payload: { checkpoint_id: "cp-1" },
    };

    await act(async () => {
      // A starts preflighting — synchronously acquires the reentrancy lock.
      const sendA = latest.send("hello", "session-1");
      // The pending HITL card is answered while A is still preflighting.
      // Fired in the same synchronous tick, before A's own stale
      // continuation has had a chance to run — exactly the window the fix
      // targets.
      const hitlPromise = latest.sendHitlResume(pendingHitl, "yes");
      // A third attempt, fired immediately after sendHitlResume takes over
      // — must NOT be dropped. Before the fix, preflightOwnerRef still
      // pointed at A's (aborted, but not yet self-cleaned) controller here.
      const sendC = latest.send("hello", "session-1");
      await Promise.all([sendA, hitlPromise, sendC]);
    });

    // Neither A (cancelled by the HITL takeover) nor the HITL resume itself
    // (cancelled in turn by the third send) ever reached prepare-execution
    // — only the third send's own call remains.
    expect(prepareExecutionCalls).toHaveLength(1);
    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    expect(latest.waitResponse).toBe(false);
    fetchSpy.mockRestore();
  });

  it("ensureFreshToken rejection during preflight: lock released, error shown, no prepare-execution, no onTurnStarted, retry works", async () => {
    flushPendingWrites = async () => true;
    vi.mocked(KeyCloakService.ensureFreshToken).mockRejectedValueOnce(new Error("token refresh failed"));
    mount();

    // Must resolve cleanly, not reject — an uncaught rejection here would
    // surface as an unhandled promise rejection in production, since
    // handleSend() never awaits/catches send()'s own promise.
    await expect(
      act(async () => {
        await latest.send("hello", "session-1");
      }),
    ).resolves.toBeUndefined();

    expect(onErrorMock).toHaveBeenCalledTimes(1);
    expect(onErrorMock.mock.calls[0][0]).toContain("token refresh failed");
    expect(prepareExecutionCalls).toHaveLength(0);
    expect(onTurnStartedMock).not.toHaveBeenCalled();
    expect(latest.waitResponse).toBe(false);

    // The lock was released on failure — an explicit retry proceeds
    // normally (mockRejectedValueOnce only applies to the first call).
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    await act(async () => {
      await latest.send("hello", "session-1");
    });

    expect(prepareExecutionCalls).toHaveLength(1);
    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });

  it("flushPendingWrites rejection during preflight: lock released, error shown, no prepare-execution, no onTurnStarted, retry works", async () => {
    // `flushPendingWrites` itself is only read once, at TestHost's render
    // (mount) time — reassigning the outer variable after mount would not
    // reach the already-rendered hook without a rerender (this file has no
    // rerender() helper). Indirect through a live-read inner function
    // instead, the same pattern `prepareExecutionImpl` already relies on.
    let flushImpl: () => Promise<boolean> = async () => {
      throw new Error("write flush failed");
    };
    flushPendingWrites = () => flushImpl();
    mount();

    await expect(
      act(async () => {
        await latest.send("hello", "session-1");
      }),
    ).resolves.toBeUndefined();

    expect(onErrorMock).toHaveBeenCalledTimes(1);
    expect(onErrorMock.mock.calls[0][0]).toContain("write flush failed");
    expect(prepareExecutionCalls).toHaveLength(0);
    expect(onTurnStartedMock).not.toHaveBeenCalled();
    expect(latest.waitResponse).toBe(false);

    // Retry, this time the write barrier succeeds.
    flushImpl = async () => true;
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    await act(async () => {
      await latest.send("hello", "session-1");
    });

    expect(prepareExecutionCalls).toHaveLength(1);
    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });

  it("reset() during A's preflight, then B starts and completes: A's late resolution does not alter B's state", async () => {
    flushPendingWrites = async () => true;
    const preps = [deferred<unknown>(), deferred<unknown>()];
    let callIndex = 0;
    prepareExecutionImpl = () => preps[callIndex++].promise;
    mount();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));

    await act(async () => {
      const sendA = latest.send("hello", "session-1");
      // reset() (e.g. leaving the chat page) cancels A outright and clears
      // all state — the lock is freed immediately for a next attempt.
      latest.reset();
      const sendB = latest.send("world", "session-2");
      // A's reply arrives late, after reset() and after B has already
      // taken over the lock.
      preps[0].resolve({
        execute_stream_url: "http://runtime.test/execute_stream",
        chat_controls: [],
        capability_base_urls: {},
      });
      await sendA;
      preps[1].resolve({
        execute_stream_url: "http://runtime.test/execute_stream",
        chat_controls: [],
        capability_base_urls: {},
      });
      await sendB;
    });

    // Only B's turn started, with exactly B's own optimistic message — A's
    // late resolution left no trace (no stray onTurnStarted, no stray
    // message, no stuck waitResponse).
    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    expect(latest.messages).toHaveLength(1);
    expect(latest.messages[0].parts[0]).toMatchObject({ type: "text", text: "world" });
    expect(latest.waitResponse).toBe(false);
    fetchSpy.mockRestore();
  });

  // Backend-rendered copy (e.g. FredHitlMiddleware's approval prompt) reads
  // runtime_context.language — it silently defaulted to English regardless of
  // the UI's own locale because nothing ever sent it. Fixed by reading the
  // live i18next language (mocked to "fr-FR" for this file, see the
  // react-i18next mock above) into every request's runtime_context.
  it("send() forwards the UI language into runtime_context", async () => {
    flushPendingWrites = async () => true;
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();

    await act(async () => {
      await latest.send("hello", "session-1");
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const body = JSON.parse(String(fetchSpy.mock.calls[0][1]?.body));
    expect(body.runtime_context.language).toBe("fr");
    fetchSpy.mockRestore();
  });

  it("sendHitlResume() forwards the UI language into runtime_context", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();
    const pendingHitl: RuntimeAwaitingHumanEvent = {
      type: "awaiting_human",
      session_id: "session-1",
      exchange_id: "exch-1",
      payload: { checkpoint_id: "cp-1" },
    };

    await act(async () => {
      await latest.sendHitlResume(pendingHitl, "proceed");
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const body = JSON.parse(String(fetchSpy.mock.calls[0][1]?.body));
    expect(body.runtime_context.language).toBe("fr");
    fetchSpy.mockRestore();
  });

  it("sendHitlResume() round-trips interrupt_id from the awaiting_human event into the resume request body (#2216)", async () => {
    // ReAct V2 resume identity: the id received on the awaiting_human SSE
    // event (LangGraph's own Interrupt.id) must be echoed back verbatim on
    // resume — the backend rejects a resume without it. checkpoint_id is
    // the unrelated legacy Graph V2 field and must round-trip independently.
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();
    const pendingHitl: RuntimeAwaitingHumanEvent = {
      type: "awaiting_human",
      session_id: "session-1",
      exchange_id: "exch-1",
      payload: { interrupt_id: "interrupt-a", checkpoint_id: null },
    };

    await act(async () => {
      await latest.sendHitlResume(pendingHitl, "proceed");
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const body = JSON.parse(String(fetchSpy.mock.calls[0][1]?.body));
    expect(body.interrupt_id).toBe("interrupt-a");
    expect(body.checkpoint_id).toBeNull();
    fetchSpy.mockRestore();
  });

  it("a token that expires DURING preparation is refused without clearing the composer", async () => {
    // The preflight certifies headroom before flushPendingWrites and
    // prepare-execution, neither of which is time-bounded, so the floor is
    // re-checked at the wire. That gate must sit ABOVE onTurnStarted and the
    // optimistic user message: refusing after them would clear the user's text
    // and leave an orphan message in the thread with an error and no reply.
    flushPendingWrites = async () => true;
    // ensureFreshToken resolves true, so the preflight never consults the
    // remaining lifetime — only the wire-time re-check does, and it sees a
    // token that died while prepare-execution was in flight.
    vi.mocked(KeyCloakService.GetTokenSecondsLeft).mockReturnValue(5);
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();

    await act(async () => {
      await latest.send("hello", "session-1");
    });

    expect(onErrorMock).toHaveBeenCalledTimes(1);
    expect(onErrorMock.mock.calls[0][0]).toContain("expired while this turn was being prepared");
    // It refuses only AFTER trying to rescue the turn — the refusal must be
    // the last resort, not the first answer.
    expect(vi.mocked(KeyCloakService.ensureFreshToken).mock.calls.map((c) => c[0])).toEqual([120, 30]);
    // The turn never committed: no onTurnStarted (so the composer keeps its
    // text) and no optimistic user message left stranded in the thread.
    expect(onTurnStartedMock).not.toHaveBeenCalled();
    expect(latest.messages).toHaveLength(0);
    expect(latest.waitResponse).toBe(false);
    fetchSpy.mockRestore();
  });

  it("a token below the floor at the wire is refreshed once, and the turn proceeds when that clears it", async () => {
    // This is the case the degraded band (§8.50) exists for: on a realm whose
    // access tokens live under TURN_TOKEN_MIN_VALIDITY_S the preflight can
    // NEVER reach its target, so it proceeds degraded by design — and a
    // refuse-only gate at the wire would hard-fail exactly those realms.
    flushPendingWrites = async () => true;
    vi.mocked(KeyCloakService.GetTokenSecondsLeft)
      .mockReturnValueOnce(12) // at the wire: under the 30 s floor
      .mockReturnValue(90); // after the rescue refresh: clear
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();

    await act(async () => {
      await latest.send("hello", "session-1");
    });

    // Two refreshes, and the second asks for the FLOOR, not the turn-start
    // target: on a short-lifespan realm `ensureFreshToken(120)` reports "not
    // fresh" for a refresh that did in fact clear the floor, which would put
    // this test's realm right back into a hard refusal.
    expect(vi.mocked(KeyCloakService.ensureFreshToken).mock.calls.map((c) => c[0])).toEqual([120, 30]);
    // The turn committed instead of being refused. (The stream itself fails —
    // there is no network here — which is a different, later error.)
    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    expect(
      onErrorMock.mock.calls.filter(([m]) => String(m).includes("expired while this turn was being prepared")),
    ).toHaveLength(0);
    fetchSpy.mockRestore();
  });

  // ── Turn-start token preflight (§8.50) ───────────────────────────────────
  //
  // `ensureFreshToken` RESOLVES false on a failed refresh rather than
  // rejecting, so these are the branches that actually run in production; the
  // rejection test above covers only the path keycloak-js never takes.

  const hitlEvent: RuntimeAwaitingHumanEvent = {
    type: "awaiting_human",
    session_id: "session-1",
    exchange_id: "exch-1",
    payload: {
      interrupt_id: "interrupt-a",
      checkpoint_id: null,
      pending_calls: [{ tool_call_id: "call-1" }],
    },
  } as RuntimeAwaitingHumanEvent;

  it("send() refuses to start a turn whose refresh failed with less than the hard floor left", async () => {
    flushPendingWrites = async () => true;
    vi.mocked(KeyCloakService.ensureFreshToken).mockResolvedValueOnce(false);
    vi.mocked(KeyCloakService.GetTokenSecondsLeft).mockReturnValueOnce(12);
    mount();

    await act(async () => {
      await latest.send("hello", "session-1");
    });

    expect(onErrorMock).toHaveBeenCalledTimes(1);
    expect(onErrorMock.mock.calls[0][0]).toContain("12s");
    // The whole point: no doomed turn is started.
    expect(prepareExecutionCalls).toHaveLength(0);
    expect(onTurnStartedMock).not.toHaveBeenCalled();
    expect(latest.waitResponse).toBe(false);
  });

  it("send() still starts the turn when the refresh failed but ample validity remains", async () => {
    flushPendingWrites = async () => true;
    vi.mocked(KeyCloakService.ensureFreshToken).mockResolvedValueOnce(false);
    vi.mocked(KeyCloakService.GetTokenSecondsLeft).mockReturnValueOnce(240);
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();

    await act(async () => {
      await latest.send("hello", "session-1");
    });

    // Degraded, not refused — a turn with 240s of bearer left is worth trying.
    expect(prepareExecutionCalls).toHaveLength(1);
    expect(onTurnStartedMock).toHaveBeenCalledTimes(1);
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
    fetchSpy.mockRestore();
  });

  it("sendHitlResume() reports not-reached and leaves no optimistic cancellation when the token is refused", async () => {
    vi.mocked(KeyCloakService.ensureFreshToken).mockResolvedValueOnce(false);
    vi.mocked(KeyCloakService.GetTokenSecondsLeft).mockReturnValueOnce(5);
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();

    let reached: boolean | undefined;
    await act(async () => {
      reached = await latest.sendHitlResume(hitlEvent, "cancel");
    });

    // false is what tells useManagedChat to put the prompt back.
    expect(reached).toBe(false);
    expect(onErrorMock).toHaveBeenCalledTimes(1);
    expect(prepareExecutionCalls).toHaveLength(0);
    // Nothing may be shown as cancelled by an attempt the backend never heard.
    expect(latest.messages).toHaveLength(0);
    fetchSpy.mockRestore();
  });

  it("sendHitlResume() leaves no optimistic cancellation when prepare-execution fails", async () => {
    prepareExecutionImpl = async () => {
      throw new Error("prepare boom");
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();

    let reached: boolean | undefined;
    await act(async () => {
      reached = await latest.sendHitlResume(hitlEvent, "cancel");
    });

    expect(reached).toBe(false);
    // The regression: the optimistic cancel used to be applied BEFORE
    // prepare-execution, so a failure here left the gated calls displayed as
    // cancelled while the prompt came back for a retry — and because those
    // messages are ranked by Date.now(), the real results could never
    // supersede them.
    expect(latest.messages).toHaveLength(0);
    fetchSpy.mockRestore();
  });

  it("sendHitlResume() applies the optimistic cancellation once preparation has succeeded", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();

    await act(async () => {
      await latest.sendHitlResume(hitlEvent, "cancel");
    });

    expect(latest.messages).toHaveLength(1);
    expect(latest.messages[0].channel).toBe("tool_result");
    expect((latest.messages[0].metadata?.extras as { cancelled_by_user?: boolean })?.cancelled_by_user).toBe(true);
    fetchSpy.mockRestore();
  });

  it("a second cancel for the same calls does not duplicate the optimistic cancellation", async () => {
    // First resume reaches the backend but its stream fails; the user answers
    // cancel again. The retry must not add a second Date.now()-ranked
    // cancelled row for the same call_id — the existing one already tells the
    // story, and a duplicate would outrank a real result arriving later.
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in test"));
    mount();

    await act(async () => {
      await latest.sendHitlResume(hitlEvent, "cancel");
    });
    await act(async () => {
      await latest.sendHitlResume(hitlEvent, "cancel");
    });

    expect(latest.messages.filter((m) => m.channel === "tool_result")).toHaveLength(1);
    fetchSpy.mockRestore();
  });

  it("sendHitlResume() reports not-reached when the runtime rejects the resume outright", async () => {
    // A 503 from an unready pod (or a fetch rejection) means the runtime never
    // took the resume, so the paused checkpoint still needs an answer. The
    // previous unconditional `return true` reported "reached" here, so the
    // caller never restored the prompt and the interaction was unanswerable.
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => "runtime unavailable",
    } as unknown as Response);
    mount();

    let reached: boolean | undefined;
    await act(async () => {
      reached = await latest.sendHitlResume(hitlEvent, "proceed");
    });

    expect(reached).toBe(false);
    expect(onErrorMock).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });

  it("sendHitlResume() reports reached once the runtime accepted it, even if the stream then dies", async () => {
    // The counterpart: a 2xx means the checkpoint was consumed. A mid-stream
    // failure must NOT resurrect the prompt — answering it again would resume
    // an exchange the runtime has already moved past.
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: () => Promise.reject(new Error("connection reset mid-stream")),
          releaseLock: () => {},
        }),
      },
    } as unknown as Response);
    mount();

    let reached: boolean | undefined;
    await act(async () => {
      reached = await latest.sendHitlResume(hitlEvent, "proceed");
    });

    expect(reached).toBe(true);
    fetchSpy.mockRestore();
  });

  it("a refused HITL resume releases the composer instead of wedging it", async () => {
    // sendHitlResume takes abortRef (and clears preflightOwnerRef) from any
    // send() still preflighting, so send()'s ownership-checked cleanup will not
    // clear waitResponse once this call owns the slot — the refusal must.
    vi.mocked(KeyCloakService.ensureFreshToken).mockResolvedValueOnce(false);
    vi.mocked(KeyCloakService.GetTokenSecondsLeft).mockReturnValueOnce(5);
    mount();

    await act(async () => {
      await latest.sendHitlResume(hitlEvent, "proceed");
    });

    expect(latest.waitResponse).toBe(false);
  });

  it("sendHitlResume() aborted during preflight reports not-reached and shows no error", async () => {
    // The abort path stranded the prompt: it returned "reached" while nothing
    // had contacted the backend, so the caller never restored pendingHitl and
    // the paused checkpoint became unanswerable. Not-reached is a fact about
    // the backend, not about who owns the UI — the caller guards restoration.
    let releaseToken: (v: boolean) => void = () => {};
    vi.mocked(KeyCloakService.ensureFreshToken).mockImplementationOnce(
      () => new Promise<boolean>((r) => (releaseToken = r)),
    );
    mount();

    let result: Promise<boolean> | undefined;
    act(() => {
      result = latest.sendHitlResume(hitlEvent, "proceed");
    });
    act(() => {
      latest.abort();
    });
    await act(async () => {
      releaseToken(true);
      await Promise.resolve();
    });

    await expect(result).resolves.toBe(false);
    expect(prepareExecutionCalls).toHaveLength(0);
    expect(onErrorMock).not.toHaveBeenCalled();
  });
});
