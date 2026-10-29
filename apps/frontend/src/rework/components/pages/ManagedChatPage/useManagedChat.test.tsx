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

// Weaver session creation, admission and stale-response boundaries. Shared
// interaction tests also exercise HITL mechanics without claiming Weaver enables it.

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { assemblePromptTurn } from "@rework/utils/skillInvocation";
import type { PreparationModels, ModelOfferKey } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { modelChoiceKey } from "../../../features/capabilities/modelChoice";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetUserId: () => "alice", GetSessionIdentity: () => "alice-session" },
}));

const translate = vi.hoisted(() => (key: string) => key);
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ agentsNicknameSingular: "" }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate, i18n: { language: "en" } }),
}));

// Reactive stand-in for react-router-dom's useSearchParams: bindSessionId
// must actually update `sessionId` across renders for the retry tests below
// (a retry re-reads `sessionId` from this, exactly like the real hook).
// `capturedSetSearchParams` additionally lets a test jump directly back to an
// arbitrary previously-visited sid (e.g. clicking a session in a sidebar) —
// something `startNewConversation()`/`handleSend()` alone can't simulate,
// since both only ever mint a brand-new sid, never rebind to an existing one.
let postponeNavigation = false;
let commitNavigation: (() => void) | undefined;
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
      const commit = () => setParams((prev) => (typeof updater === "function" ? updater(prev) : updater));
      if (postponeNavigation) commitNavigation = commit;
      else commit();
    };
    capturedSetSearchParams = setSearchParams;
    return [params, setSearchParams] as const;
  },
}));

const showErrorMock = vi.fn();
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: showErrorMock, showSuccess: vi.fn(), showWarn: vi.fn() }),
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
const sendMock = vi.fn(async (..._args: unknown[]) => true);
const steerActiveTurnMock = vi.fn(async (..._args: unknown[]) => "accepted");
let chatSseWaitResponse = false;
const prepareChatControlsMock = vi.fn(() => Object.assign(Promise.resolve({}), { abort: vi.fn() }));
const chatSseResetMock = vi.fn();
// Default: the resume reached the backend. `useManagedChat` calls `.then()` on
// whatever this returns, so an implementation-less `vi.fn()` would throw inside
// a React continuation the moment a test forgot to arrange one — and `reached
// === true` is the outcome that asks nothing of the prompt-restore path, so a
// test that forgets fails on its own assertion rather than on a TypeError.
const sendHitlResumeMock = vi.fn<(...args: unknown[]) => Promise<boolean>>(async () => true);
const abortMock = vi.fn();
const replaceAllMessagesMock = vi.fn();
// Mutable displayed thread; reset between cases.
let chatSseMessages: unknown[] = [];
let chatSseMaxChatInputChars: number | undefined;
let chatSseChatControls: unknown[] = [];
let hostModels: PreparationModels | undefined;
let preparedModelChoice: ModelOfferKey | null = null;
let capturedOnTurnStarted: (() => void) | undefined;
let capturedOnTurnRejected: ((draft: string, sessionId: string) => void) | undefined;
let capturedIsTurnCurrent: ((sessionId: string) => boolean) | undefined;
let capturedOnError: ((msg: string, code?: string) => void) | undefined;
let capturedOnAwaitingHuman: ((event: unknown) => void) | undefined;
let capturedOnSteeredMessage: ((messageId: string, sessionId: string) => void) | undefined;
vi.mock("@hooks/useChatSse", () => ({
  useChatSse: (params: {
    onTurnStarted?: () => void;
    onTurnRejected?: (draft: string, sessionId: string) => void;
    isTurnCurrent?: (sessionId: string) => boolean;
    onError?: (msg: string, code?: string) => void;
    onAwaitingHuman?: (event: unknown) => void;
    onSteeredMessage?: (messageId: string, sessionId: string) => void;
  }) => {
    capturedOnTurnStarted = params.onTurnStarted;
    capturedOnTurnRejected = params.onTurnRejected;
    capturedIsTurnCurrent = params.isTurnCurrent;
    capturedOnError = params.onError;
    capturedOnAwaitingHuman = params.onAwaitingHuman;
    capturedOnSteeredMessage = params.onSteeredMessage;
    return {
      preparation: { model_choice: preparedModelChoice, model_error: null, models: hostModels },
      messages: chatSseMessages,
      waitResponse: chatSseWaitResponse,
      chatControls: chatSseChatControls,
      maxChatInputChars: chatSseMaxChatInputChars,
      prepareChatControls: prepareChatControlsMock,
      steerActiveTurn: steerActiveTurnMock,
      send: sendMock,
      sendHitlResume: sendHitlResumeMock,
      abort: abortMock,
      reset: chatSseResetMock,
      replaceAllMessages: replaceAllMessagesMock,
    };
  },
}));

vi.mock("@shared/molecules/DocumentLibraryScopePicker/documentLibrarySelection", () => ({
  DOCUMENT_SELECTION_SUPPORTED: true,
}));

const composerResetMock = vi.fn();
const composerBindSessionMock = vi.fn();
const composerValue = {
  agentConfigurationRevision: 7,
  acceptPreparation: vi.fn(),
  documentSelection: null as { folderIds: string[]; documentIds: string[] } | null,
  setDocumentSelection: vi.fn(),
  searchPolicy: "corpus" as const,
  ragScope: "general" as const,
  askUser: true,
  setAskUser: vi.fn(),
  reasoning: false,
  setReasoning: vi.fn(),
  chatProfileId: null as string | null,
  setChatProfileId: vi.fn(),
  setSearchPolicy: vi.fn(),
  setRagScope: vi.fn(),
  reset: composerResetMock,
  bindSession: composerBindSessionMock,
  discardDraft: vi.fn(),
};
vi.mock("./useComposerSettings", () => ({
  useComposerSettings: (_sessionId: unknown, _controls: unknown, _models: unknown) => {
    return composerValue;
  },
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
  clearLocalAttachments: vi.fn(),
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
let sessionData:
  | {
      context_prompt_ids?: string[];
      title?: string;
      agent_deleted?: boolean;
      agent_display_name?: string | null;
      agent_instance_id?: string;
    }
  | undefined;
let sessionQueryUnresolved = false;
const refetchSessionMock = vi.fn();
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

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery: () => ({ data: [] }),
  useListAgentInstancesQuery: () => ({ data: [] }),
  useGetSessionQuery: () => ({
    data: sessionData,
    currentData:
      sessionQueryUnresolved || sessionDataIsStaleForCurrentArgs
        ? undefined
        : {
            space_id: "space-1",
            agent_instance_id: "agent-1",
            agent_deleted: false,
            messages_url: "/runtime/messages",
            ...sessionData,
          },
    refetch: refetchSessionMock,
    isError: false,
  }),
  useUpdateSessionMutation: () => [
    (args: unknown) => {
      patchSessionCalls.push(args);
      return mockMutationResult(patchSessionImpl(args));
    },
    { isLoading: false },
  ],
  useCreateSessionMutation: () => [
    (args: unknown) => {
      registerSessionCalls.push(args);
      return mockMutationResult(registerSessionImpl(args));
    },
    { isLoading: false },
  ],
}));

import { useManagedChat } from "./useManagedChat";
import { clearSessionHistoryCache, getCachedSessionHistory } from "./sessionHistoryCache";
import { hasToolApprovalGrants, rememberToolApprovalGrants } from "@core/utils/toolApprovalGrants";

function TestHost({ onRender }: { onRender: (hook: ReturnType<typeof useManagedChat>) => void }) {
  const hook = useManagedChat({ teamId: "team-1", agentInstanceId: "agent-1", spaceId: "space-1" });
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

  it("sends the pinned draft revision and permits a clean restart after a configuration refusal", async () => {
    registerSessionImpl = async () => {
      throw { status: 409, data: { code: "agent_configuration_changed" } };
    };
    mount();
    act(() => latest.setInput("old draft"));
    await act(async () => {
      await latest.handleSend();
    });
    expect(registerSessionCalls[0]).toMatchObject({ createSessionRequest: { agent_configuration_revision: 7 } });
    expect(latest.agentConfigurationChanged).toBe(true);
    expect(latest.executionDisabled).toBe(true);
    expect(sendMock).not.toHaveBeenCalled();
    act(() => latest.startNewConversation());
    expect(latest.sessionId).toBeNull();
    expect(latest.input).toBe("");
    expect(composerValue.discardDraft).toHaveBeenCalled();
    expect(composerResetMock).toHaveBeenCalledWith(null, []);
    expect(chatAttachmentsValue.clearLocalAttachments).toHaveBeenCalled();
    expect(chatAttachmentsValue.deletePersistedAttachment).not.toHaveBeenCalled();
    expect(latest.agentConfigurationChanged).toBe(false);
  });

  beforeEach(() => {
    postponeNavigation = false;
    commitNavigation = undefined;
    localStorage.clear();
    composerValue.documentSelection = null;
    composerValue.askUser = true;
    composerValue.reasoning = false;
    composerValue.chatProfileId = null;
    chatSseChatControls = [];
    hostModels = undefined;
    preparedModelChoice = null;
    clearSessionHistoryCache();
    chatSseMessages = [];
    chatSseWaitResponse = false;
    chatSseMaxChatInputChars = undefined;
    registerSessionImpl = async () => ({});
    patchSessionImpl = async () => ({});
    registerSessionCalls.length = 0;
    patchSessionCalls.length = 0;
    sessionData = undefined;
    sessionQueryUnresolved = false;
    refetchSessionMock.mockClear();
    sessionDataIsStaleForCurrentArgs = false;
    // `mockReset`, not `mockClear`: `mockClear` empties the call history and
    // NOTHING else (@vitest/spy `mockClear` — `state.calls = []` and friends).
    // It leaves `config.onceMockImplementations` intact, so a
    // `mockResolvedValueOnce`/`mockImplementationOnce` that its own test never
    // consumed — a rejected send, a never-resolving resume — stays queued and
    // fires in whichever LATER test happens to call the mock first. That is a
    // failure attributed to the wrong test, in a different file section, and
    // it has already happened once on this branch (in useChatSse.test.tsx).
    // `mockReset` drains that queue and restores the implementation passed to
    // `vi.fn(impl)`, which is why every mock below is declared with the default
    // it needs.
    // Reset EVERY mock the suite shares, not just the ones a test happens to
    // assert on: an uncleared spy is a silent cross-test dependency either way.
    for (const mock of [
      sendMock,
      steerActiveTurnMock,
      sendHitlResumeMock,
      prepareChatControlsMock,
      chatSseResetMock,
      abortMock,
      replaceAllMessagesMock,
      composerResetMock,
      composerBindSessionMock,
      showErrorMock,
      notifyApiErrorMock,
      chatAttachmentsValue.clearReadyAttachments,
      chatAttachmentsValue.clearLocalAttachments,
      chatAttachmentsValue.deletePersistedAttachment,
      composerValue.discardDraft,
      composerValue.acceptPreparation,
      chatAttachmentsValue.addFiles,
    ]) {
      mock.mockReset();
    }
    // Captured callbacks are per-mount; leaving a previous test's copy behind
    // lets an assertion pass against a component that is already unmounted.
    capturedOnTurnStarted = undefined;
    capturedOnTurnRejected = undefined;
    capturedIsTurnCurrent = undefined;
    capturedOnError = undefined;
    capturedOnAwaitingHuman = undefined;
    capturedOnSteeredMessage = undefined;
  });

  afterEach(async () => {
    await act(async () => {
      root.unmount();
    });
    container.remove();
  });

  // #2221: ConversationThread is React.memo'd to stop it re-rendering (and
  // re-parsing every historical message's markdown) on every composer
  // keystroke. That memo only holds if the callbacks useManagedChat hands
  // to useChatSse — and everything derived from them, like handleHitlAnswer
  // — keep a stable identity across a keystroke-only render. An inline
  // arrow at the useChatSse() call site would defeat this silently (no
  // test failure anywhere else would catch it, since behavior stays
  // correct — only the render count regresses).
  it("callbacks passed to useChatSse, and handleHitlAnswer, keep referential identity across a composer keystroke", async () => {
    mount();
    const firstOnError = capturedOnError;
    const firstOnAwaitingHuman = capturedOnAwaitingHuman;
    const firstOnTurnStarted = capturedOnTurnStarted;
    const firstHandleHitlAnswer = latest.handleHitlAnswer;
    expect(firstOnError).toBeDefined();
    expect(firstOnAwaitingHuman).toBeDefined();
    expect(firstOnTurnStarted).toBeDefined();

    act(() => {
      latest.setInput("o");
    });
    rerender();
    act(() => {
      latest.setInput("ok");
    });
    rerender();

    expect(capturedOnError).toBe(firstOnError);
    expect(capturedOnAwaitingHuman).toBe(firstOnAwaitingHuman);
    expect(capturedOnTurnStarted).toBe(firstOnTurnStarted);
    expect(latest.handleHitlAnswer).toBe(firstHandleHitlAnswer);
  });

  it("counts trimmed Unicode code points and blocks an over-limit draft without clearing it", async () => {
    chatSseMaxChatInputChars = 5;
    mount();

    act(() => {
      latest.setInput("  🙂🙂🙂🙂🙂🙂  ");
    });
    rerender();

    expect(latest.inputCharacterCount).toBe(6);
    expect(latest.inputTooLong).toBe(true);
    await act(async () => {
      await latest.handleSend();
    });

    expect(sendMock).not.toHaveBeenCalled();
    expect(registerSessionCalls).toHaveLength(0);
    expect(latest.input).toBe("  🙂🙂🙂🙂🙂🙂  ");
  });

  it("starts the first send after an intermediate render before router binding", async () => {
    sessionQueryUnresolved = true;
    mount();
    act(() => latest.setInput("hello"));
    const create = deferred<unknown>();
    registerSessionImpl = () => create.promise;
    postponeNavigation = true;
    const first = latest.handleSend();
    await tick();
    expect(registerSessionCalls).toHaveLength(1);
    // Mutation updates can render before the router commits its new search params.
    rerender();
    act(() => commitNavigation?.());
    expect(latest.executionDisabled).toBe(false);
    await act(async () => {
      create.resolve({});
      await first;
    });
    expect(sendMock).toHaveBeenCalledOnce();
    expect(capturedIsTurnCurrent?.(latest.sessionId!)).toBe(true);
  });

  it("keeps the effective first-turn identity when preparation precedes router binding", async () => {
    sessionQueryUnresolved = true;
    mount();
    act(() => latest.setInput("first draft"));
    postponeNavigation = true;
    sendMock.mockImplementationOnce(async (_text, sid) => {
      expect(capturedIsTurnCurrent?.(sid as string)).toBe(true);
      capturedOnTurnStarted?.();
      return true;
    });
    await act(async () => {
      await latest.handleSend();
    });
    expect(latest.sessionId).toBeNull();
    expect(latest.input).toBe("");
    act(() => commitNavigation?.());
    expect(latest.executionDisabled).toBe(false);
    expect(sendMock).toHaveBeenCalledOnce();
  });

  it.each([false, true])(
    "revokes a pending first send on navigation, including return to its sid (%s)",
    async (returnToOrigin) => {
      sessionQueryUnresolved = true;
      mount();
      act(() => latest.setInput("first draft"));
      const create = deferred<unknown>();
      registerSessionImpl = () => create.promise;
      const first = latest.handleSend();
      await tick();
      const sid = latest.sessionId!;
      sessionQueryUnresolved = false;
      act(() => capturedSetSearchParams?.(new URLSearchParams("session=other")));
      if (returnToOrigin) act(() => capturedSetSearchParams?.(new URLSearchParams(`session=${sid}`)));
      act(() => capturedOnAwaitingHuman?.(awaitingHumanEvent));
      const question = latest.pendingHitl;
      await act(async () => {
        create.resolve({});
        await first;
      });
      expect(sendMock).not.toHaveBeenCalled();
      expect(latest.pendingHitl).toBe(question);
    },
  );

  it("revokes a deferred draft handoff when starting another new conversation", async () => {
    sessionQueryUnresolved = true;
    mount();
    act(() => latest.setInput("first draft"));
    postponeNavigation = true;
    const create = deferred<unknown>();
    registerSessionImpl = () => create.promise;
    const first = latest.handleSend();
    await tick();
    act(() => latest.startNewConversation());
    await act(async () => {
      create.resolve({});
      await first;
    });
    expect(sendMock).not.toHaveBeenCalled();
    expect(latest.sessionId).toBeNull();
    expect(latest.input).toBe("");
  });

  it("does not mark a new draft incompatible when an abandoned creation fails late", async () => {
    sessionQueryUnresolved = true;
    const creation = deferred<unknown>();
    registerSessionImpl = () => creation.promise;
    mount();
    act(() => latest.setInput("old draft"));
    let first!: Promise<void>;
    await act(async () => {
      first = latest.handleSend();
      await Promise.resolve();
    });
    act(() => latest.startNewConversation());
    await act(async () => {
      creation.reject({ status: 409, data: { code: "agent_configuration_changed" } });
      await first;
    });
    expect(latest.sessionId).toBeNull();
    expect(latest.agentConfigurationChanged).toBe(false);
    expect(sendMock).not.toHaveBeenCalled();
  });

  it("does not start a first turn when session creation finishes after unmount", async () => {
    sessionQueryUnresolved = true;
    mount();
    act(() => latest.setInput("first draft"));
    const create = deferred<unknown>();
    registerSessionImpl = () => create.promise;
    const first = latest.handleSend();
    await tick();
    act(() => root.unmount());
    await act(async () => {
      create.resolve({});
      await first;
    });
    expect(sendMock).not.toHaveBeenCalled();
  });

  it("accepts an exact-limit Unicode draft", async () => {
    chatSseMaxChatInputChars = 5;
    mount();

    act(() => {
      latest.setInput("🙂🙂🙂🙂🙂");
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });

    expect(latest.inputTooLong).toBe(false);
    expect(sendMock).toHaveBeenCalledTimes(1);
  });

  it.each([true, false])("does not send unadvertised ask_user control on the Weaver path (%s)", async (askUser) => {
    composerValue.askUser = askUser;
    mount();
    act(() => {
      latest.setInput("first question");
    });
    rerender();

    await act(async () => {
      await latest.handleSend();
    });

    expect(sendMock).toHaveBeenCalledTimes(1);
    expect(sendMock.mock.calls[0][2]).not.toHaveProperty("ask_user");
  });

  it.each([false, true])(
    "sends the composite model choice and explicit reasoning=%s when allowed",
    async (reasoning) => {
      const key = { source_id: "source-1", upstream_model_id: "large" };
      composerValue.chatProfileId = modelChoiceKey(key);
      preparedModelChoice = key;
      composerValue.reasoning = reasoning;
      chatSseChatControls = [{ capability_id: "platform", widget: "reasoning_toggle", params: {} }];
      hostModels = {
        default: null,
        fallback: null,
        legacy_profile_id: null,
        recommendation: null,
        offers: [
          {
            key,
            permitted: true,
            candidate: true,
            reasoning_enabled: true,
            diagnostics: [],
            metadata: null,
            selectable: true,
          },
        ],
        options: {},
        requires_reselection: false,
      };
      mount();
      act(() => latest.setInput("question"));
      await act(async () => latest.handleSend());
      expect(sendMock).toHaveBeenCalledOnce();
      expect(sendMock.mock.calls[0][2]).toEqual({ model_choice: key, reasoning });
    },
  );

  it("sends no reasoning override when the recommended model cannot reason", async () => {
    const key = { source_id: "source-1", upstream_model_id: "normal" };
    composerValue.reasoning = true;
    chatSseChatControls = [{ capability_id: "platform", widget: "reasoning_toggle", params: {} }];
    hostModels = {
      default: key,
      fallback: null,
      legacy_profile_id: null,
      recommendation: null,
      offers: [
        {
          key,
          permitted: true,
          candidate: true,
          reasoning_enabled: false,
          diagnostics: [],
          metadata: null,
          selectable: true,
        },
      ],
      options: {},
      requires_reselection: false,
    };
    mount();
    act(() => latest.setInput("question"));
    await act(async () => latest.handleSend());
    expect(sendMock).toHaveBeenCalledOnce();
    expect(sendMock.mock.calls[0][2]).toEqual({});
  });

  // #2369: a brand-new conversation's composer settings live only in memory —
  // there is no session id to key sessionStorage on until handleSend mints
  // one. So the mint must both hand that id to the composer (making the pick
  // durable) and NOT trigger the sessionId-change reset(), which would rebuild
  // the composer from that session's still-empty storage and revert the pick.
  // Both halves are this hook's job and invisible from useComposerSettings'
  // own tests, which can only simulate the bind.
  it("waits for preparation matching the selected composite model before sending", async () => {
    const key = { source_id: "source-1", upstream_model_id: "large" };
    composerValue.chatProfileId = modelChoiceKey(key);
    mount();
    act(() => latest.setInput("preserved question"));
    await act(async () => latest.handleSend());
    expect(latest.modelPreparationPending).toBe(true);
    expect(registerSessionCalls).toEqual([]);
    expect(sendMock).not.toHaveBeenCalled();
    expect(latest.input).toBe("preserved question");
    preparedModelChoice = key;
    rerender();
    await act(async () => latest.handleSend());
    expect(sendMock).toHaveBeenCalledOnce();
    expect(sendMock.mock.calls[0][2]).toEqual({ model_choice: key });
  });

  it("rejects a legacy model profile instead of translating it into an offer", async () => {
    composerValue.chatProfileId = "chat.large";
    mount();
    act(() => latest.setInput("preserved question"));
    await act(async () => latest.handleSend());
    expect(latest.modelPreparationError).toBe("The saved model choice must be selected again in the Models menu.");
    expect(registerSessionCalls).toEqual([]);
    expect(sendMock).not.toHaveBeenCalled();
    expect(prepareChatControlsMock).toHaveBeenCalledWith(null, undefined);
  });

  it("sends combined selection on first and following messages, then explicit empty and reset", async () => {
    chatSseChatControls = [{ capability_id: "document_access", widget: "document_scope", params: {} }];
    composerValue.documentSelection = { folderIds: ["folder"], documentIds: ["doc"] };
    mount();
    for (const selection of [composerValue.documentSelection, { folderIds: [], documentIds: [] }, null]) {
      composerValue.documentSelection = selection;
      act(() => latest.setInput("question"));
      rerender();
      await act(async () => {
        await latest.handleSend();
      });
      const call = sendMock.mock.calls[sendMock.mock.calls.length - 1];
      expect(call[3]).toEqual({
        document_access: {
          library_tag_ids: selection?.folderIds ?? null,
          document_uids: selection?.documentIds ?? null,
        },
      });
      expect(call[2]).not.toHaveProperty("selected_document_libraries_ids");
      expect(call[2]).not.toHaveProperty("selected_document_uids");
    }
  });

  it("preserves an explicitly empty scope on human-input resume after restoration", async () => {
    composerValue.documentSelection = { folderIds: [], documentIds: [] };
    mount();
    bindSession("session-1");
    act(() => capturedOnAwaitingHuman?.(awaitingHumanEvent));
    await act(async () => latest.handleHitlAnswer("proceed"));
    expect(sendHitlResumeMock.mock.calls[sendHitlResumeMock.mock.calls.length - 1]?.[4]).toEqual({
      document_access: { library_tag_ids: [], document_uids: [] },
    });
  });

  it("hands a handleSend-minted session id to the composer instead of resetting it", async () => {
    mount();
    act(() => {
      latest.setInput("first question");
    });
    rerender();
    // The mount itself legitimately resets (entering a session, here the empty
    // one) — only what the send adds on top is under test.
    const resetsBeforeSend = composerResetMock.mock.calls.length;

    await act(async () => {
      await latest.handleSend();
    });
    rerender();

    const sid = (registerSessionCalls[0] as { createSessionRequest: { session_id: string } }).createSessionRequest
      .session_id;
    expect(composerBindSessionMock).toHaveBeenCalledWith(sid);
    expect(composerResetMock.mock.calls.length).toBe(resetsBeforeSend);
  });

  // A command turn sends the prompt's body, and the composer may hold only the
  // partial query Enter matched — neither is the session's name.
  it("titles a command-launched session from what was run", async () => {
    mount();
    // What `Enter` matched on: the user never finished typing the command.
    act(() => {
      latest.setInput("/ro");
    });
    rerender();

    await act(async () => {
      await latest.runCommand({
        text: "Liste la racine :\n\n33 lignes",
        command: {
          command: "root-ls",
          appended_text: "33 lignes",
          prompt_id: "p-1",
          prompt_name: "Lister la racine",
        },
      });
    });

    const created = registerSessionCalls[0] as { createSessionRequest: { title: string } };
    expect(created.createSessionRequest.title).toBe("Lister la racine — 33 lignes");
    // The prompt's body is what actually goes on the wire.
    expect(sendMock.mock.calls[0][0]).toBe("Liste la racine :\n\n33 lignes");
  });

  it("falls back to the command itself when the prompt has no name to show", async () => {
    mount();
    act(() => {
      latest.setInput("/ro");
    });
    rerender();

    await act(async () => {
      await latest.runCommand({
        text: "Liste la racine :",
        command: { command: "root-ls", prompt_id: "p-1" },
      });
    });

    const created = registerSessionCalls[0] as { createSessionRequest: { title: string } };
    expect(created.createSessionRequest.title).toBe("/root-ls");
  });

  it("refuses a command whose assembled text is over the limit, without a round trip", async () => {
    chatSseMaxChatInputChars = 20;
    mount();
    act(() => {
      latest.setInput("/summary");
    });
    rerender();

    await act(async () => {
      await latest.runCommand({
        text: "x".repeat(21),
        command: { command: "summary", prompt_id: "p-1" },
      });
    });

    expect(sendMock).not.toHaveBeenCalled();
    expect(registerSessionCalls).toHaveLength(0);
    expect(showErrorMock).toHaveBeenCalledTimes(1);
  });

  it("measures the assembled text of a turn with several prompt commands, not the typed line", async () => {
    chatSseMaxChatInputChars = 40;
    mount();
    const draft = "/summary and /tone";
    act(() => {
      latest.setInput(draft);
    });
    rerender();
    const run = assemblePromptTurn(draft, [
      { command: "summary", promptId: "p-1", promptName: "Summary", from: 0, to: 8, text: "x".repeat(20) },
      { command: "tone", promptId: "p-2", promptName: "Tone", from: 13, to: 18, text: "y".repeat(20) },
    ]);
    expect(draft.length).toBeLessThan(40);
    expect(run.text.length).toBeGreaterThan(40);

    await act(async () => {
      await latest.runCommand(run);
    });

    expect(sendMock).not.toHaveBeenCalled();
    expect(registerSessionCalls).toHaveLength(0);
    expect(showErrorMock).toHaveBeenCalledTimes(1);
  });

  it("titles a session started with several prompt commands from the first one and the user's own text", async () => {
    mount();
    const draft = "/summary /tone the Q3 report";
    act(() => {
      latest.setInput(draft);
    });
    rerender();

    await act(async () => {
      await latest.runCommand(
        assemblePromptTurn(draft, [
          { command: "summary", promptId: "p-1", promptName: "Weekly review", from: 0, to: 8, text: "Summarise." },
          { command: "tone", promptId: "p-2", promptName: "Formal", from: 9, to: 14, text: "Be formal." },
        ]),
      );
    });

    const created = registerSessionCalls[0] as { createSessionRequest: { title: string } };
    expect(created.createSessionRequest.title).toBe("Weekly review — the Q3 report");
    expect(sendMock.mock.calls[0][0]).toBe("Summarise.\n\nBe formal.\n\nthe Q3 report");
  });

  it("restores the complete ordinary draft after a backend length rejection", async () => {
    mount();
    const draft = "  full draft 🙂  ";

    act(() => {
      latest.setInput(draft);
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });
    act(() => capturedOnTurnStarted?.());
    rerender();
    expect(latest.input).toBe("");

    const sentSessionId = sendMock.mock.calls[0][1] as string;
    expect(capturedIsTurnCurrent?.(sentSessionId)).toBe(true);
    expect(capturedIsTurnCurrent?.("another-session")).toBe(false);
    act(() => capturedOnTurnRejected?.(draft.trim(), "another-session"));
    rerender();
    expect(latest.input).toBe("");

    act(() => capturedOnTurnRejected?.(draft.trim(), sentSessionId));
    rerender();
    expect(latest.input).toBe(draft);
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
    sessionQueryUnresolved = true;
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
    sessionQueryUnresolved = true;
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
    expect(latest.sessionId).toBeNull();
    expect(registerSessionCalls).toHaveLength(1);

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

  it("does not promote a displayed thread into an authorized history snapshot on departure", () => {
    mount();
    bindSession("session-a");
    chatSseMessages = [{ id: "x:1" }];
    rerender();
    act(() => latest.startNewConversation());
    expect(getCachedSessionHistory(JSON.stringify(["alice-session", "space-1", "session-a"]))).toBeUndefined();
  });

  // handleHitlAnswer clears pendingHitl BEFORE awaiting the resume, so the
  // prompt disappears from the UI immediately. When the resume never reaches
  // the backend (token refusal, prepare-execution failure) the checkpoint is
  // still paused server-side with nobody able to answer it — the prompt has to
  // come back, or the turn is stranded until the session is abandoned.
  const awaitingHumanEvent = {
    type: "awaiting_human" as const,
    session_id: "session-1",
    exchange_id: "exch-1",
    payload: { interrupt_id: "interrupt-a" },
  };

  // A HITL prompt always belongs to the ACTIVE session in production, and the
  // restore guard enforces exactly that — so these tests bind the session
  // param before dispatching the event, as the real flow does.
  const bindSession = (sid: string) => {
    act(() => {
      capturedSetSearchParams?.((prev: URLSearchParams) => {
        const next = new URLSearchParams(prev);
        next.set("session", sid);
        return next;
      });
    });
    rerender();
  };

  it("queues, edits, and removes text while the agent is working", async () => {
    chatSseWaitResponse = true;
    mount();
    bindSession("session-1");
    act(() => latest.setInput("first"));
    await act(async () => latest.handleSend());
    expect(latest.pendingMessages.map((message) => message.text)).toEqual(["first"]);
    expect(latest.input).toBe("");
    expect(sendMock).not.toHaveBeenCalled();

    const id = latest.pendingMessages[0].id;
    act(() => latest.editPendingMessage(id));
    expect(latest.input).toBe("first");
    expect(latest.pendingMessages).toEqual([]);
    await act(async () => latest.handleSend());
    act(() => latest.removePendingMessage(latest.pendingMessages[0].id));
    expect(latest.pendingMessages).toEqual([]);
  });

  it("queues text when files already belong to the conversation", async () => {
    chatSseWaitResponse = true;
    chatAttachmentsValue.attachmentsMarkdown = "## Attached files for this conversation\n- report.txt";
    try {
      mount();
      bindSession("session-1");
      act(() => latest.setInput("focus on Marseille"));
      await act(async () => latest.handleSend());
      expect(latest.pendingMessages.map((message) => message.text)).toEqual(["focus on Marseille"]);
      expect(sendMock).not.toHaveBeenCalled();
    } finally {
      chatAttachmentsValue.attachmentsMarkdown = null;
    }
  });

  it("keeps a forced row until the runtime confirms delivery", async () => {
    chatSseWaitResponse = true;
    mount();
    bindSession("session-1");
    act(() => latest.setInput("change course"));
    await act(async () => latest.handleSend());
    const id = latest.pendingMessages[0].id;
    await act(async () => latest.forcePendingMessage(id));
    expect(steerActiveTurnMock).toHaveBeenCalledWith("session-1", id, "change course");
    expect(latest.pendingMessages[0].status).toBe("offered");
    act(() => capturedOnSteeredMessage?.(id, "session-1"));
    expect(latest.pendingMessages).toEqual([]);
  });

  it("holds uncertain delivery until the person retries", async () => {
    chatSseWaitResponse = true;
    steerActiveTurnMock.mockResolvedValueOnce("uncertain");
    mount();
    bindSession("session-1");
    act(() => latest.setInput("change course"));
    await act(async () => latest.handleSend());
    const id = latest.pendingMessages[0].id;
    await act(async () => latest.forcePendingMessage(id));
    expect(latest.pendingMessages[0].status).toBe("uncertain");
    chatSseWaitResponse = false;
    await act(async () => rerender());
    expect(sendMock).not.toHaveBeenCalled();
    act(() => latest.retryPendingMessage(id));
    await act(async () => rerender());
    expect(sendMock).toHaveBeenCalledWith("change course", "session-1", expect.anything(), undefined, undefined);
  });

  it("sends queued text after the active turn ends", async () => {
    chatSseWaitResponse = true;
    mount();
    bindSession("session-1");
    act(() => latest.setInput("next"));
    await act(async () => latest.handleSend());
    sendMock.mockImplementationOnce(async () => {
      capturedOnTurnStarted?.();
      return true;
    });
    chatSseWaitResponse = false;
    await act(async () => rerender());
    expect(sendMock).toHaveBeenCalledTimes(1);
    expect(sendMock.mock.calls[0][0]).toBe("next");
    expect(latest.pendingMessages).toEqual([]);
  });

  it("holds queued text while a human-input prompt is pending", async () => {
    chatSseWaitResponse = true;
    mount();
    bindSession("session-1");
    act(() => latest.setInput("next"));
    await act(async () => latest.handleSend());
    act(() => capturedOnAwaitingHuman?.(awaitingHumanEvent));
    chatSseWaitResponse = false;
    await act(async () => rerender());
    expect(sendMock).not.toHaveBeenCalled();
    expect(latest.pendingMessages[0]).toMatchObject({ text: "next", status: "waiting" });
  });

  it("keeps a forced row offered while a human-input resume is preparing", async () => {
    chatSseWaitResponse = true;
    let resolveResume: (reached: boolean) => void = () => {};
    sendHitlResumeMock.mockImplementationOnce(() => new Promise<boolean>((resolve) => (resolveResume = resolve)));
    mount();
    bindSession("session-1");
    act(() => latest.setInput("focus on Marseille"));
    await act(async () => latest.handleSend());
    const id = latest.pendingMessages[0].id;
    await act(async () => latest.forcePendingMessage(id));
    act(() => capturedOnAwaitingHuman?.(awaitingHumanEvent));
    chatSseWaitResponse = false;
    await act(async () => rerender());

    act(() => latest.handleHitlAnswer("proceed"));
    rerender();
    expect(latest.pendingHitl).toBeNull();
    expect(latest.pendingMessages[0]).toMatchObject({ id, status: "offered" });
    expect(sendMock).not.toHaveBeenCalled();

    chatSseWaitResponse = true;
    await act(async () => {
      resolveResume(true);
      await Promise.resolve();
    });
    rerender();
    act(() => capturedOnSteeredMessage?.(id, "session-1"));
    expect(latest.pendingMessages).toEqual([]);
  });

  it("starts a new turn when an accepted steer misses the final model boundary after HITL", async () => {
    chatSseWaitResponse = true;
    let resolveResume: (reached: boolean) => void = () => {};
    sendHitlResumeMock.mockImplementationOnce(() => new Promise<boolean>((resolve) => (resolveResume = resolve)));
    mount();
    bindSession("session-1");
    act(() => latest.setInput("focus on Marseille"));
    await act(async () => latest.handleSend());
    const id = latest.pendingMessages[0].id;
    await act(async () => latest.forcePendingMessage(id));
    act(() => capturedOnAwaitingHuman?.(awaitingHumanEvent));
    chatSseWaitResponse = false;
    await act(async () => rerender());

    act(() => latest.handleHitlAnswer("proceed"));
    chatSseWaitResponse = true;
    await act(async () => {
      resolveResume(true);
      await Promise.resolve();
    });
    expect(latest.pendingMessages[0]).toMatchObject({ id, status: "offered" });

    sendMock.mockImplementationOnce(async () => {
      capturedOnTurnStarted?.();
      return true;
    });
    chatSseWaitResponse = false;
    await act(async () => rerender());
    await act(async () => rerender());
    expect(sendMock).toHaveBeenCalledWith("focus on Marseille", "session-1", expect.anything(), undefined, undefined);
    expect(latest.pendingMessages).toEqual([]);
  });

  it("keeps a forced row offered when human-input resume preflight fails", async () => {
    chatSseWaitResponse = true;
    let resolveResume: (reached: boolean) => void = () => {};
    sendHitlResumeMock.mockImplementationOnce(() => new Promise<boolean>((resolve) => (resolveResume = resolve)));
    mount();
    bindSession("session-1");
    act(() => latest.setInput("focus on Marseille"));
    await act(async () => latest.handleSend());
    const id = latest.pendingMessages[0].id;
    await act(async () => latest.forcePendingMessage(id));
    act(() => capturedOnAwaitingHuman?.(awaitingHumanEvent));

    act(() => latest.handleHitlAnswer("proceed"));
    act(() => capturedOnError?.("Could not resume"));
    expect(latest.pendingMessages[0]).toMatchObject({ id, status: "offered" });
    expect(sendMock).not.toHaveBeenCalled();

    chatSseWaitResponse = false;
    await act(async () => {
      resolveResume(false);
      await Promise.resolve();
    });
    rerender();
    expect(latest.pendingHitl).toEqual(awaitingHumanEvent);
    expect(latest.pendingMessages[0]).toMatchObject({ id, status: "offered" });
  });

  it("marks a forced row uncertain when the resumed stream fails after acceptance", async () => {
    chatSseWaitResponse = true;
    sendHitlResumeMock.mockImplementationOnce(async (...args) => {
      (args[6] as () => void)();
      return true;
    });
    mount();
    bindSession("session-1");
    act(() => latest.setInput("focus on Marseille"));
    await act(async () => latest.handleSend());
    const id = latest.pendingMessages[0].id;
    await act(async () => latest.forcePendingMessage(id));
    act(() => capturedOnAwaitingHuman?.(awaitingHumanEvent));

    await act(async () => latest.handleHitlAnswer("proceed"));
    act(() => capturedOnError?.("Resumed stream failed"));
    expect(latest.pendingMessages[0]).toMatchObject({ id, status: "uncertain" });
  });

  it("starts only the first queued turn while it is running", async () => {
    chatSseWaitResponse = true;
    mount();
    bindSession("session-1");
    act(() => latest.setInput("first"));
    await act(async () => latest.handleSend());
    act(() => latest.setInput("second"));
    await act(async () => latest.handleSend());
    let finishFirst: ((accepted: boolean) => void) | undefined;
    sendMock.mockImplementationOnce(async () => {
      capturedOnTurnStarted?.();
      return new Promise<boolean>((resolve) => {
        finishFirst = resolve;
      });
    });
    chatSseWaitResponse = false;
    await act(async () => rerender());
    expect(sendMock).toHaveBeenCalledTimes(1);
    expect(sendMock.mock.calls[0][0]).toBe("first");
    expect(latest.pendingMessages.map((message) => message.text)).toEqual(["second"]);
    await act(async () => finishFirst?.(true));
  });

  it("pauses a rejected queued turn until an explicit resend", async () => {
    chatSseWaitResponse = true;
    mount();
    bindSession("session-1");
    act(() => latest.setInput("next"));
    await act(async () => latest.handleSend());
    sendMock.mockImplementationOnce(async () => {
      capturedOnTurnStarted?.();
      capturedOnTurnRejected?.("next", "session-1");
      return false;
    });
    chatSseWaitResponse = false;
    await act(async () => rerender());
    await act(async () => rerender());
    expect(sendMock).toHaveBeenCalledTimes(1);
    expect(latest.pendingMessages[0]).toMatchObject({ text: "next", status: "uncertain" });
  });

  it("restores a queued turn when the stream fails before acceptance", async () => {
    chatSseWaitResponse = true;
    mount();
    bindSession("session-1");
    act(() => latest.setInput("next"));
    await act(async () => latest.handleSend());
    sendMock.mockImplementationOnce(async () => {
      capturedOnTurnStarted?.();
      capturedOnError?.("network failure");
      return false;
    });
    chatSseWaitResponse = false;
    await act(async () => rerender());
    expect(latest.pendingMessages[0]).toMatchObject({ text: "next", status: "uncertain" });
    expect(sendMock).toHaveBeenCalledTimes(1);
  });

  const toolApprovalEvent = {
    ...awaitingHumanEvent,
    payload: {
      ...awaitingHumanEvent.payload,
      stage: "tool_approval",
      pending_calls: [{ tool_call_id: "call-1", tool_name: "write_file", args_preview: "{}" }],
      choices: [
        { id: "proceed", label: "Accept" },
        { id: "cancel", label: "Reject" },
      ],
    },
  };
  const grantScope = { userId: "alice", agentInstanceId: "agent-1", sessionId: "session-1" };

  const interruptedEvent = {
    type: "awaiting_human",
    session_id: "session-1",
    exchange_id: "exchange-1",
    payload: {
      stage: "execution_interrupted",
      choices: [
        { id: "continue", label: "Continue" },
        { id: "restart", label: "Restart" },
      ],
      metadata: { node_id: "publish", interruption_id: "int-1" },
    },
  };

  it("Later dismisses unfinished work without sending or losing the draft", () => {
    mount();
    bindSession("session-1");
    act(() => latest.setInput("draft"));
    act(() => capturedOnAwaitingHuman?.(interruptedEvent));
    rerender();
    act(() => latest.handleHitlAnswer("later"));
    expect(latest.pendingHitl).toBeNull();
    expect(latest.input).toBe("draft");
    expect(sendMock).not.toHaveBeenCalled();
    expect(sendHitlResumeMock).not.toHaveBeenCalled();
    act(() => capturedOnAwaitingHuman?.(interruptedEvent));
    expect(latest.pendingHitl).toEqual(interruptedEvent);
  });

  it("continues an interrupted run with the restored document restriction", async () => {
    composerValue.documentSelection = { folderIds: [], documentIds: [] };
    mount();
    bindSession("session-1");
    act(() => capturedOnAwaitingHuman?.(interruptedEvent));
    await act(async () => {
      latest.handleHitlAnswer("continue");
      await Promise.resolve();
    });
    expect(sendMock).toHaveBeenCalledWith(
      "",
      "session-1",
      expect.any(Object),
      {
        document_access: { library_tag_ids: [], document_uids: [] },
      },
      { action: "continue", interruptionId: "int-1" },
    );
  });

  it("continue on an interrupted run sends the interruption, not a HITL resume, and keeps the draft", async () => {
    mount();
    bindSession("session-1");
    act(() => latest.setInput("again"));
    act(() => capturedOnAwaitingHuman?.(interruptedEvent));
    rerender();

    await act(async () => {
      latest.handleHitlAnswer("continue");
      await Promise.resolve();
    });

    expect(sendHitlResumeMock).not.toHaveBeenCalled();
    expect(sendMock).toHaveBeenCalledWith("", "session-1", expect.any(Object), undefined, {
      action: "continue",
      interruptionId: "int-1",
    });
    expect(latest.pendingHitl).toBeNull();
    expect(latest.input).toBe("again");
  });

  it("keeps offering the choice when the continue request never started", async () => {
    sendMock.mockResolvedValueOnce(false);
    mount();
    bindSession("session-1");
    act(() => capturedOnAwaitingHuman?.(interruptedEvent));
    rerender();

    await act(async () => {
      latest.handleHitlAnswer("continue");
      await Promise.resolve();
    });
    rerender();

    expect(latest.pendingHitl).toEqual(interruptedEvent);
  });

  it("restart on an interrupted run re-sends the same turn, command included, with restart", async () => {
    mount();
    bindSession("session-1");
    const command = { command: "plan", prompt_name: "Plan", appended_text: "" };
    act(() => latest.setInput("/plan"));
    rerender();
    await act(async () => {
      await latest.runCommand({ text: "assembled prompt", command } as never);
    });
    act(() => capturedOnAwaitingHuman?.(interruptedEvent));
    rerender();

    await act(async () => {
      latest.handleHitlAnswer("restart");
      await Promise.resolve();
    });

    expect(sendHitlResumeMock).not.toHaveBeenCalled();
    const restart = sendMock.mock.calls[1];
    expect(restart[0]).toBe("assembled prompt");
    expect(restart[2]).toMatchObject({ command });
    expect(restart[4]).toEqual({ action: "restart" });
  });

  it("submits Other text alone after a single question choice", async () => {
    const question = {
      ...awaitingHumanEvent,
      payload: {
        ...awaitingHumanEvent.payload,
        stage: "agent_question",
        choices: [{ id: "paris", label: "Paris" }],
        free_text: true,
      },
    };
    mount();
    bindSession("session-1");
    act(() => capturedOnAwaitingHuman?.(question));
    rerender();

    await act(async () => {
      latest.handleHitlAnswer("paris", "Lyon");
      await Promise.resolve();
    });

    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      question,
      undefined,
      "Lyon",
      expect.any(Object),
      undefined,
      false,
      expect.any(Function),
    );
  });

  it("replaces a staged choice with Other text in a grouped answer", async () => {
    const first = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Destination?",
        interrupt_id: "interrupt-a",
        occurrence_id: "call-a",
        choices: [{ id: "paris", label: "Paris" }],
        free_text: true,
      },
    };
    const second = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Budget?",
        interrupt_id: "interrupt-b",
        occurrence_id: "call-b",
        choices: [{ id: "low", label: "Low" }],
        free_text: true,
      },
    };
    mount();
    bindSession("session-1");
    act(() => {
      capturedOnAwaitingHuman?.(first);
      capturedOnAwaitingHuman?.(second);
    });
    rerender();
    act(() => latest.stageHitlAnswer("paris"));
    act(() => latest.selectHitlTab(first));
    act(() => latest.setHitlFreeText("Lyon"));
    // Typing withdraws the staged choice; the text counts once validated.
    expect(latest.stagedHitlAnswer).toBeUndefined();
    act(() => latest.stageHitlAnswer(undefined, "Lyon"));
    act(() => latest.stageHitlAnswer("low"));

    await act(async () => {
      latest.handleSendAllHitl();
      await Promise.resolve();
    });

    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      first,
      undefined,
      undefined,
      expect.any(Object),
      undefined,
      false,
      expect.any(Function),
      [
        { event: first, answer: undefined, freeText: "Lyon", skipped: false },
        { event: second, answer: "low", freeText: undefined, skipped: false },
      ],
    );
  });

  it("wraps Next to the first unanswered question tab", () => {
    const questions = ["first", "second", "third", "fourth"].map((id) => ({
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: `${id}?`,
        interrupt_id: `interrupt-${id}`,
        occurrence_id: `call-${id}`,
        choices: [{ id, label: id }],
        free_text: true,
      },
    }));
    mount();
    bindSession("session-1");
    act(() => questions.forEach((question) => capturedOnAwaitingHuman?.(question)));
    rerender();

    act(() => latest.selectHitlTab(questions[3]));
    act(() => latest.stageHitlAnswer("fourth"));
    expect(latest.pendingHitl).toEqual(questions[0]);
    act(() => latest.stageHitlAnswer("first"));
    expect(latest.pendingHitl).toEqual(questions[1]);
    act(() => latest.selectHitlTab(questions[3]));
    act(() => latest.stageHitlAnswer("fourth"));
    expect(latest.pendingHitl).toEqual(questions[1]);
    act(() => latest.stageHitlAnswer("second"));
    expect(latest.pendingHitl).toEqual(questions[2]);
  });

  it("replaces a validated Other text with a later choice", () => {
    const first = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Destination?",
        interrupt_id: "interrupt-a",
        occurrence_id: "call-a",
        choices: [{ id: "paris", label: "Paris" }],
        free_text: true,
      },
    };
    const second = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Budget?",
        interrupt_id: "interrupt-b",
        occurrence_id: "call-b",
        free_text: true,
      },
    };
    mount();
    bindSession("session-1");
    act(() => {
      capturedOnAwaitingHuman?.(first);
      capturedOnAwaitingHuman?.(second);
    });
    rerender();
    act(() => latest.setHitlFreeText("Lyon"));
    act(() => latest.stageHitlAnswer(undefined, "Lyon"));
    act(() => latest.selectHitlTab(first));
    // What the card does on a choice click: clear the Other field, then stage the choice.
    act(() => latest.setHitlFreeText(""));
    act(() => latest.stageHitlAnswer("paris"));
    act(() => latest.selectHitlTab(first));
    expect(latest.stagedHitlAnswer).toEqual({ answer: "paris", freeText: undefined, skipped: false });
    expect(latest.hitlFreeText).toBe("");
  });

  it("stages simultaneous answers, permits revision, then resumes once", async () => {
    const first = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Destination?",
        interrupt_id: "interrupt-a",
        occurrence_id: "call-a",
        choices: [
          { id: "paris", label: "Paris" },
          { id: "rome", label: "Rome" },
        ],
        free_text: true,
      },
    };
    const second = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Budget?",
        interrupt_id: "interrupt-b",
        occurrence_id: "call-b",
        free_text: true,
      },
    };
    mount();
    bindSession("session-1");
    act(() => {
      capturedOnAwaitingHuman?.(first);
      capturedOnAwaitingHuman?.(second);
    });
    rerender();
    expect(latest.pendingHitlTabs).toEqual([first, second]);
    act(() => latest.stageHitlAnswer("paris"));
    expect(latest.pendingHitl).toEqual(second);
    expect(latest.canSendAllHitl).toBe(false);
    expect(sendHitlResumeMock).not.toHaveBeenCalled();

    act(() => latest.setHitlFreeText("No limit"));
    expect(latest.pendingHitl).toEqual(second);
    // Typed text is only a draft until validated.
    expect(latest.stagedHitlCount).toBe(1);
    expect(latest.canSendAllHitl).toBe(false);
    act(() => latest.stageHitlAnswer(undefined, "No limit"));
    expect(latest.stagedHitlCount).toBe(2);
    expect(latest.canSendAllHitl).toBe(true);
    expect(sendHitlResumeMock).not.toHaveBeenCalled();
    act(() => latest.setHitlFreeText("  "));
    expect(latest.canSendAllHitl).toBe(false);
    act(() => latest.setHitlFreeText("No limit"));
    act(() => latest.stageHitlAnswer(undefined, "No limit"));
    expect(latest.canSendAllHitl).toBe(true);
    act(() => latest.selectHitlTab(first));
    act(() => latest.stageHitlAnswer("rome"));
    expect(latest.stagedHitlAnswer?.answer).toBe("rome");

    await act(async () => {
      latest.handleSendAllHitl();
      await Promise.resolve();
    });
    expect(sendHitlResumeMock).toHaveBeenCalledTimes(1);
    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      first,
      undefined,
      undefined,
      expect.any(Object),
      undefined,
      false,
      expect.any(Function),
      [
        { event: first, answer: "rome", freeText: undefined, skipped: false },
        { event: second, answer: undefined, freeText: "No limit", skipped: false },
      ],
    );
    expect(latest.pendingHitl).toBeNull();
  });

  it("skips every simultaneous question when the card is closed", async () => {
    const first = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Destination?",
        interrupt_id: "interrupt-a",
        occurrence_id: "call-a",
        free_text: true,
      },
    };
    const second = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Budget?",
        interrupt_id: "interrupt-b",
        occurrence_id: "call-b",
        free_text: true,
      },
    };
    mount();
    bindSession("session-1");
    act(() => {
      capturedOnAwaitingHuman?.(first);
      capturedOnAwaitingHuman?.(second);
    });
    rerender();
    act(() => latest.setHitlFreeText("Paris"));
    act(() => latest.selectHitlTab(second));
    expect(latest.canSendAllHitl).toBe(false);

    await act(async () => {
      latest.handleSkipAllHitl();
      await Promise.resolve();
    });
    expect(sendHitlResumeMock).toHaveBeenCalledTimes(1);
    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      first,
      undefined,
      undefined,
      expect.any(Object),
      undefined,
      false,
      expect.any(Function),
      [
        { event: first, answer: undefined, freeText: undefined, skipped: true },
        { event: second, answer: undefined, freeText: undefined, skipped: true },
      ],
    );
    expect(latest.pendingHitl).toBeNull();
  });

  it("removes an accepted batch before the stream finishes and preserves new questions", async () => {
    const first = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Destination?",
        interrupt_id: "interrupt-a",
        occurrence_id: "call-a",
        free_text: true,
      },
    };
    const second = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Budget?",
        interrupt_id: "interrupt-b",
        occurrence_id: "call-b",
        free_text: true,
      },
    };
    const followup = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Transport?",
        interrupt_id: "interrupt-c",
        occurrence_id: "call-c",
        free_text: true,
      },
    };
    let acceptResume: (() => void) | undefined;
    let finishResume: (accepted: boolean) => void = () => {};
    sendHitlResumeMock.mockImplementationOnce(
      (...args: unknown[]) =>
        new Promise<boolean>((resolve) => {
          acceptResume = args[6] as () => void;
          finishResume = resolve;
        }),
    );
    mount();
    bindSession("session-1");
    act(() => {
      capturedOnAwaitingHuman?.(first);
      capturedOnAwaitingHuman?.(second);
    });
    rerender();
    act(() => latest.setHitlFreeText("Paris"));
    act(() => latest.stageHitlAnswer(undefined, "Paris"));
    act(() => latest.setHitlFreeText("No limit"));
    act(() => latest.stageHitlAnswer(undefined, "No limit"));
    act(() => latest.handleSendAllHitl());
    expect(latest.pendingHitlTabs).toEqual([first, second]);

    act(() => {
      capturedOnAwaitingHuman?.(followup);
      acceptResume?.();
    });
    expect(latest.pendingHitlTabs).toEqual([followup]);
    expect(latest.pendingHitl).toEqual(followup);
    act(() => capturedOnAwaitingHuman?.(first));
    expect(latest.pendingHitlTabs).toEqual([followup]);

    await act(async () => {
      finishResume(true);
      await Promise.resolve();
    });
    expect(latest.pendingHitlTabs).toEqual([followup]);
    expect(latest.hitlFreeText).toBe("");
  });

  it("keeps all staged answers editable when a batch resume fails", async () => {
    const first = {
      ...awaitingHumanEvent,
      payload: { stage: "agent_question", question: "Duration?", interrupt_id: "interrupt-a", occurrence_id: "call-a" },
    };
    const second = {
      ...awaitingHumanEvent,
      payload: {
        stage: "agent_question",
        question: "Budget?",
        interrupt_id: "interrupt-b",
        occurrence_id: "call-b",
        free_text: true,
      },
    };
    sendHitlResumeMock.mockResolvedValueOnce(false);
    mount();
    bindSession("session-1");
    act(() => {
      capturedOnAwaitingHuman?.(first);
      capturedOnAwaitingHuman?.(second);
    });
    rerender();
    act(() => latest.stageHitlAnswer(undefined, undefined, true));
    act(() => latest.stageHitlAnswer(undefined, undefined, true));
    expect(latest.canSendAllHitl).toBe(true);
    await act(async () => {
      latest.handleSendAllHitl();
      await Promise.resolve();
    });
    expect(latest.pendingHitlTabs).toEqual([first, second]);
    expect(latest.canSendAllHitl).toBe(true);
    expect(sendHitlResumeMock).toHaveBeenCalledTimes(1);
    act(() => latest.setHitlFreeText("A different answer"));
    // Editing withdraws the staged skip until the new text is validated.
    expect(latest.stagedHitlAnswer).toBeUndefined();
    act(() => latest.stageHitlAnswer(undefined, "A different answer"));
    expect(latest.stagedHitlAnswer).toEqual({
      answer: undefined,
      freeText: "A different answer",
      skipped: false,
    });
    act(() => latest.setHitlFreeText(""));
    expect(latest.canSendAllHitl).toBe(false);
  });

  it("remembers only the gated tool after the approval resume is accepted", async () => {
    localStorage.clear();
    sendHitlResumeMock.mockImplementationOnce(async (...args: unknown[]) => {
      (args[6] as (() => void) | undefined)?.();
      return true;
    });
    mount();
    bindSession("session-1");
    act(() => capturedOnAwaitingHuman?.(toolApprovalEvent));
    rerender();

    await act(async () => {
      latest.handleHitlAnswer("proceed", undefined, false, true);
      await Promise.resolve();
    });

    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      toolApprovalEvent,
      "proceed",
      undefined,
      expect.any(Object),
      undefined,
      false,
      expect.any(Function),
    );
    expect(hasToolApprovalGrants(grantScope, ["write_file"])).toBe(true);
    expect(hasToolApprovalGrants(grantScope, ["delete"])).toBe(false);
  });

  it("does not remember a conversation approval when the resume was not accepted", async () => {
    sendHitlResumeMock.mockResolvedValueOnce(false);
    mount();
    bindSession("session-1");
    act(() => capturedOnAwaitingHuman?.(toolApprovalEvent));
    rerender();

    await act(async () => {
      latest.handleHitlAnswer("proceed", undefined, false, true);
      await Promise.resolve();
    });

    expect(hasToolApprovalGrants(grantScope, ["write_file"])).toBe(false);
    expect(latest.pendingHitl).toEqual(toolApprovalEvent);
  });

  it("automatically resumes only when every gated tool was remembered", async () => {
    localStorage.clear();
    rememberToolApprovalGrants(grantScope, ["write_file"]);
    mount();
    bindSession("session-1");
    act(() => capturedOnAwaitingHuman?.(toolApprovalEvent));
    rerender();
    await tick();
    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      toolApprovalEvent,
      "proceed",
      undefined,
      expect.any(Object),
      undefined,
      false,
      expect.any(Function),
    );

    const mixedBatch = {
      ...toolApprovalEvent,
      exchange_id: "exch-2",
      payload: {
        ...toolApprovalEvent.payload,
        interrupt_id: "interrupt-b",
        pending_calls: [
          ...toolApprovalEvent.payload.pending_calls,
          { tool_call_id: "call-2", tool_name: "delete", args_preview: "{}" },
        ],
      },
    };
    act(() => capturedOnAwaitingHuman?.(mixedBatch));
    rerender();
    expect(latest.pendingHitl).toEqual(mixedBatch);
    expect(sendHitlResumeMock).toHaveBeenCalledTimes(1);
  });

  it("restores a failed automatic resume without retrying the same occurrence", async () => {
    localStorage.clear();
    rememberToolApprovalGrants(grantScope, ["write_file"]);
    sendHitlResumeMock.mockResolvedValueOnce(false);
    mount();
    bindSession("session-1");
    await act(async () => {
      capturedOnAwaitingHuman?.(toolApprovalEvent);
      await Promise.resolve();
    });
    rerender();
    expect(latest.pendingHitl).toEqual(toolApprovalEvent);
    expect(sendHitlResumeMock).toHaveBeenCalledTimes(1);
  });

  it("blocks over-limit HITL free text locally while leaving fixed choices available", async () => {
    chatSseMaxChatInputChars = 5;
    mount();
    bindSession("session-1");
    const freeTextEvent = {
      ...awaitingHumanEvent,
      payload: {
        ...awaitingHumanEvent.payload,
        free_text: true,
        choices: [{ id: "proceed", label: "Proceed" }],
      },
    };

    act(() => {
      capturedOnAwaitingHuman?.(freeTextEvent);
      latest.setHitlFreeText("🙂🙂🙂🙂🙂🙂");
    });
    rerender();
    act(() => latest.handleHitlAnswer(undefined, latest.hitlFreeText));

    expect(sendHitlResumeMock).not.toHaveBeenCalled();
    expect(latest.pendingHitl).toEqual(freeTextEvent);
    expect(latest.hitlFreeText).toBe("🙂🙂🙂🙂🙂🙂");

    await act(async () => {
      latest.handleHitlAnswer("proceed");
    });
    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      freeTextEvent,
      "proceed",
      undefined,
      expect.any(Object),
      undefined,
      false,
      expect.any(Function),
    );
  });

  it("accepts HITL free text at the exact configured code-point limit", async () => {
    chatSseMaxChatInputChars = 5;
    sendHitlResumeMock.mockResolvedValueOnce(true);
    mount();
    bindSession("session-1");
    const freeTextEvent = {
      ...awaitingHumanEvent,
      payload: { ...awaitingHumanEvent.payload, free_text: true },
    };

    act(() => {
      capturedOnAwaitingHuman?.(freeTextEvent);
      latest.setHitlFreeText("🙂🙂🙂🙂🙂");
    });
    rerender();
    await act(async () => {
      latest.handleHitlAnswer(undefined, latest.hitlFreeText);
      await Promise.resolve();
    });

    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      freeTextEvent,
      undefined,
      "🙂🙂🙂🙂🙂",
      expect.any(Object),
      undefined,
      false,
      expect.any(Function),
    );
  });

  it.each([
    { exchangeId: "exch-1", invocation: { name: "meeting-minutes" } },
    { exchangeId: "older-exchange", invocation: { name: "meeting-minutes" } },
    { exchangeId: "exch-1", invocation: { name: 42 } },
  ])("does not turn stored skill metadata into resume authority ($exchangeId)", async ({ exchangeId, invocation }) => {
    chatSseMessages = [
      {
        session_id: "session-1",
        exchange_id: exchangeId,
        timestamp: "2026-10-09T00:00:00Z",
        rank: 0,
        role: "user",
        channel: "final",
        parts: [{ type: "text", text: "/meeting-minutes notes" }],
        metadata: { extras: { skill_invocation: invocation } },
      },
    ];
    mount();
    bindSession("session-1");
    act(() => capturedOnAwaitingHuman?.(awaitingHumanEvent));
    rerender();
    await act(async () => latest.handleHitlAnswer("proceed"));
    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      awaitingHumanEvent,
      "proceed",
      undefined,
      expect.not.objectContaining({ skills: expect.anything() }),
      undefined,
      false,
      expect.any(Function),
    );
    act(() => latest.setInput("follow up"));
    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).toHaveBeenCalledOnce();
    expect(sendMock.mock.calls[0]?.[2]).not.toHaveProperty("skill");
  });

  it("sends explicit command skills but does not infer resume authority from stored metadata", async () => {
    const skills = [{ name: "meeting-minutes" }, { name: "mermaid" }];
    const command = {
      command: "summary",
      prompt_id: "p-summary",
      draft_text: "Before /summary /meeting-minutes /mermaid after",
      draft_command_offset: 7,
    };
    mount();
    bindSession("session-1");
    await act(async () =>
      latest.runCommand({ text: "Before\n\nPrompt instructions\n\n/meeting-minutes /mermaid after", command, skills }),
    );
    expect(sendMock.mock.calls[sendMock.mock.calls.length - 1]?.[2]).toEqual(
      expect.objectContaining({ command, skills }),
    );
    chatSseMessages = [
      {
        session_id: "session-1",
        exchange_id: "exch-1",
        timestamp: "2026-10-09T00:00:00Z",
        rank: 0,
        role: "user",
        channel: "final",
        parts: [{ type: "text", text: "assembled prompt" }],
        metadata: { command, extras: { skill_invocations: skills } },
      },
    ];
    rerender();
    act(() => capturedOnAwaitingHuman?.(awaitingHumanEvent));
    rerender();
    await act(async () => latest.handleHitlAnswer("proceed"));
    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      awaitingHumanEvent,
      "proceed",
      undefined,
      expect.not.objectContaining({ skills: expect.anything() }),
      undefined,
      false,
      expect.any(Function),
    );
    act(() => latest.setInput("follow up"));
    await act(async () => latest.handleSend());
    expect(sendMock.mock.calls[sendMock.mock.calls.length - 1]?.[2]).not.toHaveProperty("skills");
  });

  it("blocks new turns while an agent question is pending and during its resume", async () => {
    let resolveResume: (reached: boolean) => void = () => {};
    sendHitlResumeMock.mockImplementationOnce(() => new Promise<boolean>((resolve) => (resolveResume = resolve)));
    mount();
    bindSession("session-1");
    const question = {
      ...awaitingHumanEvent,
      payload: { ...awaitingHumanEvent.payload, stage: "agent_question" },
    };
    act(() => {
      latest.setInput("next message");
      capturedOnAwaitingHuman?.(question);
    });
    rerender();

    await act(async () => {
      await latest.handleSend();
      await latest.runCommand({ text: "command body", command: { command: "test" } });
    });
    expect(sendMock).not.toHaveBeenCalled();

    act(() => latest.handleHitlAnswer(undefined, undefined, true));
    rerender();
    expect(latest.pendingHitl).toBeNull();
    expect(latest.resumingAgentQuestionSessionId).toBe("session-1");
    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).not.toHaveBeenCalled();

    await act(async () => {
      resolveResume(true);
      await Promise.resolve();
    });
    rerender();
    expect(latest.resumingAgentQuestionSessionId).toBeNull();
    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).toHaveBeenCalledOnce();
  });

  it("restores the HITL prompt when the resume never reached the backend", async () => {
    sendHitlResumeMock.mockResolvedValueOnce(false);
    mount();
    bindSession("session-1");

    act(() => {
      capturedOnAwaitingHuman?.(awaitingHumanEvent);
      latest.setHitlFreeText("  complete answer 🙂  ");
    });
    rerender();
    expect(latest.pendingHitl).toEqual(awaitingHumanEvent);

    await act(async () => {
      latest.handleHitlAnswer(undefined, latest.hitlFreeText);
    });
    rerender();

    expect(sendHitlResumeMock).toHaveBeenCalledTimes(1);
    expect(sendHitlResumeMock).toHaveBeenCalledWith(
      awaitingHumanEvent,
      undefined,
      "  complete answer 🙂  ",
      expect.any(Object),
      undefined,
      false,
      expect.any(Function),
    );
    expect(latest.pendingHitl).toEqual(awaitingHumanEvent);
    expect(latest.hitlFreeText).toBe("  complete answer 🙂  ");
  });

  it("does not resurrect the prompt over a new turn started in the same session", async () => {
    // The common abort: the user answers, then immediately sends a new
    // message. That aborts the resume, which now reports not-reached — but
    // re-displaying the old confirmation card over the streaming reply would
    // let them answer an exchange they have already moved past.
    let resolveResume: (v: boolean) => void = () => {};
    sendHitlResumeMock.mockImplementationOnce(() => new Promise<boolean>((r) => (resolveResume = r)));
    mount();
    bindSession("session-1");

    act(() => {
      capturedOnAwaitingHuman?.(awaitingHumanEvent);
    });
    rerender();

    act(() => {
      latest.handleHitlAnswer("proceed");
    });
    // The user sends a new message while the resume is still in flight. The
    // supersede must land HERE, synchronously at the point of intent — waiting
    // for onTurnStarted (a preflight + prepare-execution round trip later)
    // loses the race against the aborted resume's continuation.
    // A turn that genuinely starts appends its optimistic user message under a
    // NEW exchange_id — that, not a counter, is what marks the prompt stale.
    chatSseMessages = [{ session_id: "session-1", exchange_id: "exch-2", rank: 1 }];
    act(() => {
      latest.setInput("a new message");
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });

    await act(async () => {
      resolveResume(false);
      await Promise.resolve();
    });
    rerender();

    expect(latest.pendingHitl).toBeNull();
  });

  it("restores the prompt when a superseding send fails without starting a turn", async () => {
    // The generation bump has to be synchronous (before the resume's
    // continuation), but a send can still fail asynchronously afterwards — at
    // prepare-execution, the token floor, or the write barrier. A failed send
    // supersedes nothing, so the bump must be rolled back or the HITL prompt is
    // suppressed forever with no turn having replaced it.
    let resolveResume: (v: boolean) => void = () => {};
    sendHitlResumeMock.mockImplementationOnce(() => new Promise<boolean>((r) => (resolveResume = r)));
    // A send that fails before committing appends NOTHING to the thread, so
    // the last message still belongs to the HITL prompt's own exchange.
    chatSseMessages = [{ session_id: "session-1", exchange_id: "exch-1", rank: 1 }];
    mount();
    bindSession("session-1");

    act(() => {
      capturedOnAwaitingHuman?.(awaitingHumanEvent);
    });
    rerender();

    act(() => {
      latest.handleHitlAnswer("proceed");
    });
    act(() => {
      latest.setInput("a new message");
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });

    await act(async () => {
      resolveResume(false);
      await Promise.resolve();
    });
    rerender();

    expect(latest.pendingHitl).toEqual(awaitingHumanEvent);
  });

  it("restores the prompt when a superseding send never reaches the backend", async () => {
    // The write-barrier bail: a failed session write aborts handleSend before
    // send() is ever called. The old generation counter was already bumped by
    // then and nothing rolled it back, so the prompt was suppressed forever.
    // Deriving staleness from the thread has no such hole — nothing was
    // appended, so the last message still belongs to the prompt's exchange.
    let resolveResume: (v: boolean) => void = () => {};
    sendHitlResumeMock.mockImplementationOnce(() => new Promise<boolean>((r) => (resolveResume = r)));
    chatSseMessages = [{ session_id: "session-1", exchange_id: "exch-1", rank: 1 }];
    patchSessionImpl = async () => {
      throw new Error("PATCH failed");
    };
    mount();
    bindSession("session-1");

    act(() => {
      capturedOnAwaitingHuman?.(awaitingHumanEvent);
    });
    rerender();

    act(() => {
      latest.handleHitlAnswer("proceed");
    });
    act(() => {
      latest.setInput("a new message");
    });
    rerender();
    await act(async () => {
      await latest.handleSend();
    });

    await act(async () => {
      resolveResume(false);
      await Promise.resolve();
    });
    rerender();

    expect(latest.pendingHitl).toEqual(awaitingHumanEvent);
  });

  it("restores the prompt when the resume rejects outright", async () => {
    // pendingHitl is cleared before awaiting, so a rejection with no .catch()
    // would strand the paused checkpoint and raise an unhandled rejection.
    sendHitlResumeMock.mockRejectedValueOnce(new Error("boom"));
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mount();
    bindSession("session-1");

    act(() => {
      capturedOnAwaitingHuman?.(awaitingHumanEvent);
    });
    rerender();

    await act(async () => {
      latest.handleHitlAnswer("cancel");
      await Promise.resolve();
    });
    rerender();

    expect(latest.pendingHitl).toEqual(awaitingHumanEvent);
    errorSpy.mockRestore();
  });

  it("does not resurrect the prompt into another session after navigating away", async () => {
    let resolveResume: (v: boolean) => void = () => {};
    sendHitlResumeMock.mockImplementationOnce(() => new Promise<boolean>((r) => (resolveResume = r)));
    mount();
    bindSession("session-1");

    act(() => {
      capturedOnAwaitingHuman?.(awaitingHumanEvent);
    });
    rerender();

    act(() => {
      latest.handleHitlAnswer("cancel");
    });
    // The user navigates to a fresh conversation while the resume is still
    // in flight; its late "not reached" must not stomp the new view.
    act(() => {
      latest.startNewConversation();
    });
    rerender();

    await act(async () => {
      resolveResume(false);
      await Promise.resolve();
    });
    rerender();

    expect(latest.pendingHitl).toBeNull();
  });

  it("keeps the HITL prompt cleared once the resume has reached the backend", async () => {
    sendHitlResumeMock.mockResolvedValueOnce(true);
    mount();
    bindSession("session-1");

    act(() => {
      capturedOnAwaitingHuman?.(awaitingHumanEvent);
    });
    rerender();
    expect(latest.pendingHitl).toEqual(awaitingHumanEvent);

    await act(async () => {
      latest.handleHitlAnswer("proceed");
    });
    rerender();

    expect(sendHitlResumeMock).toHaveBeenCalledTimes(1);
    expect(latest.pendingHitl).toBeNull();
  });

  it("does not clear a newer HITL prompt's draft when an older resume settles", async () => {
    let resolveResume: (v: boolean) => void = () => {};
    sendHitlResumeMock.mockImplementationOnce(() => new Promise<boolean>((r) => (resolveResume = r)));
    mount();
    bindSession("session-1");

    act(() => {
      capturedOnAwaitingHuman?.(awaitingHumanEvent);
      latest.setHitlFreeText("answer for the first prompt");
    });
    rerender();
    act(() => latest.handleHitlAnswer(undefined, latest.hitlFreeText));

    const newerPrompt = {
      ...awaitingHumanEvent,
      exchange_id: "exch-2",
      payload: { ...awaitingHumanEvent.payload, interrupt_id: "interrupt-b" },
    };
    act(() => {
      capturedOnAwaitingHuman?.(newerPrompt);
      latest.setHitlFreeText("answer for the newer prompt");
    });
    rerender();

    await act(async () => {
      resolveResume(true);
      await Promise.resolve();
    });
    rerender();

    expect(latest.pendingHitl).toEqual(newerPrompt);
    expect(latest.hitlFreeText).toBe("answer for the newer prompt");
  });
  // The page reads the model list before it knows whether the conversation can
  // run; that answer must not drop the stored choice (and warn) meanwhile.
  it("does not prepare or send when session metadata is deleted, mismatched or unresolved", async () => {
    mount();
    bindSession("saved");
    for (const state of [{ agent_deleted: true }, { agent_instance_id: "other" }, undefined]) {
      sessionData = state;
      sessionQueryUnresolved = state === undefined;
      rerender();
      const count = prepareChatControlsMock.mock.calls.length;
      act(() => latest.setInput("blocked"));
      await act(async () => latest.handleSend());
      expect(latest.executionDisabled).toBe(true);
      expect(prepareChatControlsMock).toHaveBeenCalledTimes(count);
      expect(sendMock).not.toHaveBeenCalled();
    }
  });

  it("freezes an existing conversation after deletion and resumes normal behavior on a live conversation", async () => {
    mount();
    act(() => capturedSetSearchParams?.(new URLSearchParams("session=saved")));
    act(() => latest.setInput("draft to preserve"));
    const retainedSend = latest.handleSend;
    const retainedUpload = latest.handleAddAttachments;
    sessionData = { agent_deleted: true, agent_display_name: "Preserved assistant", title: "Preserved title" };
    rerender();
    expect(latest.isReadOnly).toBe(true);
    expect(latest.agentDisplayName).toBe("Preserved assistant");
    const prepCalls = prepareChatControlsMock.mock.calls.length;
    const writes = patchSessionCalls.length;
    await act(async () => {
      await retainedSend();
    });
    act(() => {
      retainedUpload([new File(["content"], "file.txt")], "picker");
      latest.setContextPrompts(["blocked"]);
      latest.setAskUser(false);
      latest.setChatProfileId("chat.fast");
      latest.startNewConversation();
    });
    expect(sendMock).not.toHaveBeenCalled();
    expect(composerValue.setChatProfileId).not.toHaveBeenCalled();
    expect(chatAttachmentsValue.addFiles).not.toHaveBeenCalled();
    expect(patchSessionCalls).toHaveLength(writes);
    expect(latest.sessionId).toBe("saved");
    expect(latest.input).toBe("draft to preserve");
    expect(prepareChatControlsMock).toHaveBeenCalledTimes(prepCalls);
    await act(async () => latest.commitTitle("Readable title"));
    expect(patchSessionCalls[patchSessionCalls.length - 1]).toMatchObject({
      updateSessionRequest: { title: "Readable title" },
    });
    sessionData = { agent_deleted: false };
    act(() => capturedSetSearchParams?.(new URLSearchParams("session=live")));
    expect(latest.isReadOnly).toBe(false);
    expect(latest.executionDisabled).toBe(false);
    act(() => latest.setInput("send to live agent"));
    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).toHaveBeenCalledOnce();
  });

  it.each(["agent_question", "tool_approval", "execution_interrupted"] as const)(
    "blocks retained single, batch, skip and interruption callbacks after deletion (%s)",
    async (stage) => {
      mount();
      act(() => capturedSetSearchParams?.(new URLSearchParams("session=saved")));
      act(() =>
        capturedOnAwaitingHuman?.({
          type: "awaiting_human",
          session_id: "saved",
          exchange_id: "exchange",
          payload: {
            stage,
            question: "Preserved question",
            interrupt_id: "interrupt",
            occurrence_id: "occurrence",
            free_text: true,
          },
        }),
      );
      const answer = latest.handleHitlAnswer;
      const skipAll = latest.handleSkipAllHitl;
      sessionData = { agent_deleted: true };
      rerender();
      act(() => {
        answer(stage === "execution_interrupted" ? "continue" : "yes");
        answer("restart");
        skipAll();
        latest.handleSendAllHitl();
        latest.stageHitlAnswer("yes");
        latest.setHitlFreeText("blocked answer");
      });
      await tick();
      expect(sendMock).not.toHaveBeenCalled();
      expect(sendHitlResumeMock).not.toHaveBeenCalled();
      expect(latest.pendingHitl?.payload.question).toBe("Preserved question");
      expect(latest.hitlFreeText).toBe("");
    },
  );

  it("still permits retrying a known failed local creation after leaving and returning", async () => {
    mount();
    sessionQueryUnresolved = true;
    registerSessionImpl = async () => {
      throw new Error("creation failed");
    };
    act(() => latest.setInput("preserved draft"));
    await act(async () => {
      await latest.handleSend();
    });
    const failed = latest.sessionId!;
    act(() => capturedSetSearchParams?.(new URLSearchParams("session=other")));
    act(() => capturedSetSearchParams?.(new URLSearchParams(`session=${failed}`)));
    expect(latest.executionDisabled).toBe(false);
    registerSessionImpl = async () => ({});
    act(() => latest.setInput("retry after creation failure"));
    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).toHaveBeenCalledOnce();
  });

  it("ends the local exemption after an idempotent creation retry confirms the saved session", async () => {
    mount();
    sessionQueryUnresolved = true;
    registerSessionImpl = async () => {
      throw new Error("POST response lost after commit");
    };
    act(() => latest.setInput("preserved draft"));
    await act(async () => {
      await latest.handleSend();
    });
    const created = latest.sessionId!;
    registerSessionImpl = async () => ({});
    sessionQueryUnresolved = false;
    rerender();
    await act(async () => {
      await latest.handleSend();
    });
    expect(registerSessionCalls).toHaveLength(2);
    expect(registerSessionCalls[1]).toEqual(registerSessionCalls[0]);
    expect(sendMock).toHaveBeenCalledOnce();
    act(() => capturedSetSearchParams?.(new URLSearchParams("session=other")));
    sessionQueryUnresolved = true;
    act(() => capturedSetSearchParams?.(new URLSearchParams(`session=${created}`)));
    expect(latest.executionDisabled).toBe(true);
    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).toHaveBeenCalledOnce();
  });

  it("limits the local creation exemption to its first handoff and blocks a later unresolved visit", async () => {
    mount();
    sessionQueryUnresolved = true;
    act(() => latest.setInput("first question"));
    await act(async () => latest.handleSend());
    const created = latest.sessionId!;
    expect(latest.executionDisabled).toBe(false);
    sessionQueryUnresolved = false;
    rerender();
    act(() => capturedSetSearchParams?.(new URLSearchParams("session=other")));
    sessionQueryUnresolved = true;
    act(() => capturedSetSearchParams?.(new URLSearchParams(`session=${created}`)));
    expect(latest.executionDisabled).toBe(true);
    expect(latest.isReadOnly).toBe(false);
  });

  it.each([false, true])("does not read or write legacy context prompts (saved=%s)", async (saved) => {
    mount();
    if (saved) bindSession("saved");
    sessionData = { context_prompt_ids: ["legacy"] };
    rerender();
    act(() => latest.setContextPrompts(["new"]));
    await tick();
    expect(latest.contextPromptIds).toEqual([]);
    expect(registerSessionCalls).toEqual([]);
    expect(patchSessionCalls).toEqual([]);
    expect(sendMock).not.toHaveBeenCalled();
  });

  it.each([false, true])("ignores a late title response after navigation (failed=%s)", async (failed) => {
    const update = deferred<{ title: string }>();
    patchSessionImpl = () => update.promise;
    mount();
    bindSession("session-a");
    let pending: Promise<void>;
    act(() => {
      pending = latest.commitTitle("A title");
    });
    sessionData = { title: "B title" };
    bindSession("session-b");
    await act(async () => {
      if (failed) update.reject(new Error("old request failed"));
      else update.resolve({ title: "A title" });
      await pending;
    });
    expect(latest.sessionTitle).toBe("B title");
    expect(notifyApiErrorMock).not.toHaveBeenCalled();
  });

  it("does not interpret unresolved session metadata as a deleted agent", async () => {
    mount();
    sessionQueryUnresolved = true;
    act(() => capturedSetSearchParams?.(new URLSearchParams("session=loading")));
    expect(latest.isReadOnly).toBe(false);
    expect(latest.executionDisabled).toBe(true);
    const before = prepareChatControlsMock.mock.calls.length;
    act(() => latest.setInput("waiting"));
    await act(async () => {
      await latest.handleSend();
    });
    expect(sendMock).not.toHaveBeenCalled();
    expect(prepareChatControlsMock).toHaveBeenCalledTimes(before);
    act(() => window.dispatchEvent(new Event("focus")));
    expect(refetchSessionMock).toHaveBeenCalled();
  });
});
