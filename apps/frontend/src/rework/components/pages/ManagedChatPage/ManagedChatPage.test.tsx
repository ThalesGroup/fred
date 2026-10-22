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

import { SkillBadge } from "@shared/molecules/SkillBadge/SkillBadge";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../../../../slices/runtime/runtimeOpenApi";
import type { ThreadMessage } from "../../../types/thread";
import { ThoughtTrace } from "@shared/molecules/ThoughtTrace/ThoughtTrace";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// The capability side-panel open request the page watches, mutable so a test
// can raise the counter the way a capability renderer's dispatch does.
const openRequest = vi.hoisted(() => ({ requestId: 0, key: null as string | null }));

// The launcher rail's buttons, captured so a test can press one the way the
// user does. They open the other push drawers, which share the capability
// panel's one slot.
type CapturedLauncher = { key: string; icon?: string; iconFilled?: boolean; onOpen: () => void };
const rail = vi.hoisted(() => ({ launchers: [] as CapturedLauncher[], footerLaunchers: [] as CapturedLauncher[] }));
// The personal team's id: a chat in it counts as administered by its owner.
const bootstrap = vi.hoisted(() => ({ activeTeamId: "team-1" }));
// The composer's recall handler, captured so a test can press an arrow on it.
const composerKeys = vi.hoisted(() => ({
  recall: undefined as undefined | ((event: unknown) => boolean),
  send: undefined as undefined | (() => void),
}));
// The composer's model read: refetched when the window regains focus or a conversation opens.
const modelRead = vi.hoisted(() => ({
  refetch: vi.fn(),
  fulfilledTimeStamp: undefined as number | undefined,
  options: undefined as { skip?: boolean } | undefined,
}));
// The thread's opener for a sent prompt badge, and the error toast.
const threadProps = vi.hoisted(() => ({
  openCommandPrompt: undefined as
    | undefined
    | ((turn: { text: string; command: { command: string }; promptIndex?: number }) => void),
}));
const showError = vi.hoisted(() => vi.fn());

vi.mock("react-router-dom", () => ({ useParams: () => ({ teamId: "team-1", agentInstanceId: "agent-1" }) }));
// A fresh object per read, like a real selector over changing store state: the
// page's effect compares the snapshot by reference, so a mutated singleton
// would never look like a new request.
vi.mock("react-redux", () => ({ useSelector: () => ({ ...openRequest }) }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    // The values a command error is built from are part of the message.
    t: (key: string, options?: { command?: string; limit?: number }) =>
      key.startsWith("chatbot.commandMenu.runError") && options ? `${key}:${options.command ?? options.limit}` : key,
    i18n: { language: "en" },
  }),
}));

let chatValue: Record<string, unknown>;
vi.mock("./useManagedChat", () => ({ useManagedChat: () => chatValue }));
vi.mock("@shared/molecules/RichInputField/RichInputField", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@shared/molecules/RichInputField/RichInputField")>()),
  RichInputField: (props: {
    placeholder?: string;
    accessibleDescription?: string;
    sendDisabled?: boolean;
    disabled?: boolean;
    characterCount?: number;
    characterLimit?: number;
    focusEndRequestId?: number;
    inlineSkills?: {
      tokens: { name: string; description?: string; onOpen: (name: string) => void }[];
      promptTokens?: {
        name: string;
        promptId: string;
        promptTeamId: string;
        from: number;
        to: number;
        teamName?: string;
      }[];
      onOpenPrompt?: (target: { promptId: string; promptTeamId: string; name: string; command: string }) => void;
    };
    value?: string;
    onSend?: () => void;
    onRecallKeyDown?: (event: unknown) => boolean;
  }) => {
    composerKeys.recall = props.onRecallKeyDown;
    composerKeys.send = props.onSend;
    return (
      <div
        data-testid="composer"
        data-placeholder={props.placeholder}
        data-description={props.accessibleDescription}
        data-send-disabled={props.sendDisabled}
        data-composer-disabled={props.disabled}
        data-character-count={props.characterCount}
        data-character-limit={props.characterLimit}
        data-focus-request={props.focusEndRequestId}
      >
        {props.inlineSkills?.tokens.map((token) => <SkillBadge key={token.name} {...token} />)}
        {props.inlineSkills?.promptTokens?.map((token) => (
          <button
            key={token.from}
            type="button"
            data-testid="prompt-token"
            data-team-name={token.teamName}
            onClick={() =>
              props.inlineSkills?.onOpenPrompt?.({
                promptId: token.promptId,
                promptTeamId: token.promptTeamId,
                name: token.name,
                command: (props.value ?? "").slice(token.from + 1, token.to),
              })
            }
          >
            {token.name}
          </button>
        ))}
      </div>
    );
  },
}));
vi.mock("./ConversationThread/ConversationThread", () => ({
  ConversationThread: (props: {
    messages: ThreadMessage[];
    maxChatInputChars?: number;
    hitlFreeText: string;
    onHitlFreeTextChange: unknown;
    isLoading?: boolean;
    readOnly?: boolean;
    onOpenCommandPrompt?: typeof threadProps.openCommandPrompt;
  }) => {
    threadProps.openCommandPrompt = props.onOpenCommandPrompt;
    return (
      <div
        data-testid="thread"
        data-character-limit={props.maxChatInputChars}
        data-hitl-draft={props.hitlFreeText}
        data-has-hitl-change-handler={typeof props.onHitlFreeTextChange === "function"}
        data-readonly={props.readOnly}
        data-loading={props.isLoading}
      >
        {props.messages.map((message) => (
          <ThoughtTrace key={message.id} messages={message.traceMessages ?? []} />
        ))}
      </div>
    );
  },
}));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ agentIconName: "person", agentsNicknameSingular: "" }),
}));
vi.mock("../../../../hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({ activeTeam: { id: bootstrap.activeTeamId } }),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: fetchedTeam.current }),
  // #2387 — the composer's model label. Undefined here: this file covers the
  // chat-input policy wiring, and the label's own behaviour is covered in
  // ReasoningChip.test.tsx.
  useEffectiveChatModelQuery: (_: unknown, options?: { skip?: boolean }) => {
    modelRead.options = options;
    return {
      data: undefined,
      currentData: undefined,
      fulfilledTimeStamp: modelRead.fulfilledTimeStamp,
      refetch: modelRead.refetch,
    };
  },
  useAddPromptFavoriteMutation: () => [vi.fn()],
  useRemovePromptFavoriteMutation: () => [vi.fn()],
}));
const commandQueries = vi.hoisted(() => vi.fn());
const fetchedTeam = vi.hoisted(() => ({ current: undefined as { id: string; name: string } | undefined }));
const teamCommands = vi.hoisted(() => ({ current: [] as unknown[] }));
const promptPreviewFetch = vi.hoisted(() => vi.fn());
// What reading a prompt answers when a command runs; a rejection is a failed read.
const promptRead = vi.hoisted(() => ({
  current: (async () => ({ text: "" })) as (args: { promptId: string }) => Promise<{ text: string }>,
}));
const promptPreviewResult = vi.hoisted(() => ({
  currentData: undefined as { text: string } | undefined,
  isFetching: false,
  isError: false,
  originalArgs: undefined as { promptId: string } | undefined,
}));
const skillPreviewQuery = vi.hoisted(() => vi.fn());
const previewResult = vi.hoisted(() => ({
  currentData: undefined as unknown,
  isFetching: false,
  error: undefined as unknown,
  refetch: vi.fn(),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetAgentInstanceSkillsQuery: () => ({
    currentData: {
      supported: true,
      skills: [
        { name: "compare-options", description: "Compare", argument_hint: "[options]" },
        { name: "review", description: "Review" },
      ],
    },
  }),
  useGetAgentInstanceSkillDetailQuery: (args: unknown, options: unknown) => {
    skillPreviewQuery(args, options);
    return previewResult;
  },

  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: () => [
    (args: { promptId: string }) => {
      promptPreviewFetch(args);
      promptPreviewResult.originalArgs = args;
      return { unwrap: () => promptRead.current(args) };
    },
    promptPreviewResult,
  ],
  // Read by the prompt-selection panel the page mounts; it is closed here, so
  // the queries are skipped and only their shape matters.
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery: () => ({
    data: [],
    isLoading: false,
  }),
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery: () => ({ data: [] }),
  // The composer's command list — no prompt carries a command here, so the
  // trigger stays closed and the composer behaves as it did before.
  useGetTeamPromptCommandsControlPlaneV1TeamsTeamIdPromptCommandsGetQuery: (args: unknown, options: unknown) => {
    commandQueries(args, options);
    return { currentData: (args as { teamId: string }).teamId === "team-1" ? teamCommands.current : [] };
  },
}));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => ({ canAdministerAdmins: false }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError }),
}));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetUserGivenName: () => "Ada" },
}));
vi.mock("../../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useTranscribeAudioKnowledgeFlowV1AudioTranscriptionsPostMutation: () => [() => ({ unwrap: async () => ({}) })],
}));
vi.mock("../../../core/hooks/useUploadWarningAcknowledgement", () => ({
  useUploadWarningAcknowledgement: () => ({ requiresAcknowledgement: false, acknowledge: () => undefined }),
}));

vi.mock("@shared/molecules/SessionTitleEditor/SessionTitleEditor", () => ({ SessionTitleEditor: () => null }));
vi.mock("@shared/molecules/AgentTodoPanel/AgentTodoPanel", () => ({
  AgentTodoPanel: ({ sessionId, todos }: { sessionId: string; todos: { content: string }[] }) => (
    <div data-testid="agent-todo-panel" data-session-id={sessionId}>
      {todos.map((todo) => todo.content).join("|")}
    </div>
  ),
}));
vi.mock("@shared/molecules/DebugRawDrawer/DebugRawDrawer", () => ({ DebugRawDrawer: () => null }));
vi.mock("@shared/molecules/FullReasoningPanel/FullReasoningPanel", () => ({ FullReasoningPanel: () => null }));
vi.mock("@shared/molecules/AttachmentChips/AttachmentChips", () => ({ AttachmentChips: () => null }));
vi.mock("@shared/molecules/SessionAttachmentsDrawer/SessionAttachmentsDrawer", () => ({
  SessionAttachmentsDrawer: () => null,
}));
vi.mock("@shared/molecules/DocumentScopePanel/DocumentScopePanel", () => ({ DocumentScopePanel: () => null }));
vi.mock("@shared/molecules/ThoughtTrace/TraceDetailDrawer/TraceDetailDrawer", () => ({
  TraceDetailDrawer: () => null,
}));
vi.mock("@shared/molecules/UploadWarningAckDialog/UploadWarningAckDialog", () => ({
  UploadWarningAckDialog: () => null,
}));
vi.mock("@shared/molecules/TokenUsageBadge/TokenUsageBadge", () => ({ TokenUsageBadge: () => null }));
// Stands in for the real host on the one thing the page owns: which panel key
// it is told to show. Rendering that back is what lets a test see the drawer
// open (or stay shut) without mounting a capability's editor.
vi.mock("../../../features/capabilities/CapabilitySidePanelHost", () => ({
  CapabilitySidePanelHost: ({ activeKey }: { activeKey: string | null }) =>
    activeKey ? <div data-testid="capability-panel" data-key={activeKey} /> : null,
}));
vi.mock("../../../features/capabilities/ChatLauncherRail", () => ({
  ChatLauncherRail: ({
    launchers,
    footerLaunchers,
  }: {
    launchers: CapturedLauncher[];
    footerLaunchers: CapturedLauncher[];
  }) => {
    rail.launchers = launchers;
    rail.footerLaunchers = footerLaunchers;
    return null;
  },
}));
vi.mock("../../../features/capabilities/ComposerControlSlot", () => ({ ComposerControlSlot: () => null }));
vi.mock("../../../features/capabilities/ComposerOptionChips", () => ({
  COMPOSER_CHIP_WIDGETS: new Set<string>(),
  ComposerOptionChips: () => null,
}));
vi.mock("@shared/molecules/ComposerActionsMenu/ComposerActionsMenu", () => ({
  ComposerActionsMenu: () => null,
}));

import ManagedChatPage from "./ManagedChatPage";

const PANEL_KEY = "writable_document:writable_document_pane";
// The page reads the last turn (auto-scroll, outline rail), so a stand-in has
// to carry the fields it looks at, not just an id.
const renderedTurn = { id: "m1", role: "assistant", text: "hello", isStreaming: false, traceMessages: [] };
const OTHER_PANEL_KEY = "ppt_filler:ppt_preview_pane";

describe("ManagedChatPage chat-input policy wiring", () => {
  it("passes the runtime policy to both the composer and active HITL prompt", () => {
    const noop = () => undefined;
    chatValue = {
      agentDisplayName: "Agent",
      attachments: [],
      attachmentsUploading: false,
      capabilityIds: [],
      chatControls: [],
      commitTitle: noop,
      deletePersistedAttachment: noop,
      handleAbort: noop,
      handleAddAttachments: noop,
      handleHitlAnswer: noop,
      handleSend: noop,
      hitlFreeText: "complete HITL draft",
      input: "six!!",
      inputCharacterCount: 6,
      inputTooLong: true,
      isHydratingAttachments: false,
      isLoadingHistory: false,
      maxChatInputChars: 5,
      messages: [],
      pendingHitl: { session_id: "session-1", exchange_id: "exchange-1", payload: { free_text: true } },
      persistedAttachments: [],
      ragScope: "all",
      reasoning: false,
      removeAttachment: noop,
      searchPolicy: "hybrid",
      selectedDocumentUids: [],
      selectedLibraryIds: [],
      sessionId: "session-1",
      sessionTitle: "Chat",
      setHitlFreeText: noop,
      setInput: noop,
      setRagScope: noop,
      setReasoning: noop,
      setSearchPolicy: noop,
      setSelectedDocumentUids: noop,
      setSelectedLibraryIds: noop,
      threadMessages: [],
      waitResponse: false,
    };

    const html = renderToStaticMarkup(<ManagedChatPage />);

    expect(html).toContain('data-testid="composer"');
    expect(html).toContain('data-send-disabled="true"');
    expect(html).toContain('data-character-count="6"');
    expect(html.match(/data-character-limit="5"/g)).toHaveLength(2);
    expect(html).toContain('data-testid="thread"');
    expect(html).toContain('data-hitl-draft="complete HITL draft"');
    expect(html).toContain('data-has-hitl-change-handler="true"');

    chatValue.pendingHitl = {
      session_id: "session-1",
      exchange_id: "exchange-1",
      payload: { stage: "agent_question", free_text: true },
    };
    const pendingQuestionHtml = renderToStaticMarkup(<ManagedChatPage />);
    expect(pendingQuestionHtml).toContain('data-composer-disabled="true"');
  });
});

const baseChatValue = (messages: Record<string, unknown>[]) => {
  const noop = () => undefined;
  return {
    agentDisplayName: "Agent",
    attachments: [],
    attachmentsUploading: false,
    capabilityIds: [],
    chatControls: [],
    commitTitle: noop,
    deletePersistedAttachment: noop,
    handleAbort: noop,
    handleAddAttachments: noop,
    handleHitlAnswer: noop,
    handleSend: noop,
    hitlFreeText: "",
    input: "",
    inputCharacterCount: 0,
    inputTooLong: false,
    isHistorySettled: true,
    isHydratingAttachments: false,
    isLoadingHistory: false,
    messages,
    pendingHitl: null,
    persistedAttachments: [],
    ragScope: "all",
    reasoning: false,
    removeAttachment: noop,
    searchPolicy: "hybrid",
    selectedDocumentUids: [],
    selectedLibraryIds: [],
    sessionId: "session-1",
    sessionTitle: "Chat",
    setHitlFreeText: noop,
    setInput: noop,
    setRagScope: noop,
    setReasoning: noop,
    setSearchPolicy: noop,
    setSelectedDocumentUids: noop,
    setSelectedLibraryIds: noop,
    threadMessages: [renderedTurn],
    waitResponse: false,
  };
};

describe("ManagedChatPage agent todo panel", () => {
  const todoCall = (todos: Record<string, unknown>[]) => ({
    session_id: "session-1",
    exchange_id: "exchange-1",
    rank: 1,
    timestamp: "2026-09-17T00:00:00.000Z",
    role: "assistant",
    channel: "tool_call",
    parts: [{ type: "tool_call", call_id: "todo-1", name: "write_todos", args: { todos } }],
  });

  it("mounts the latest live or restored snapshot between the thread and composer", () => {
    chatValue = baseChatValue([
      todoCall([{ content: "First plan", status: "pending" }]),
      { ...todoCall([{ content: "Current plan", status: "in_progress" }]), rank: 2 },
    ]);

    const html = renderToStaticMarkup(<ManagedChatPage />);
    expect(html).toContain('data-testid="agent-todo-panel"');
    expect(html).toContain("Current plan");
    expect(html).not.toContain("First plan");
    expect(html.indexOf('data-testid="thread"')).toBeLessThan(html.indexOf('data-testid="agent-todo-panel"'));
    expect(html.indexOf('data-testid="agent-todo-panel"')).toBeLessThan(html.indexOf('data-testid="composer"'));
  });

  it("removes the panel when the final answer settles its only remaining task", () => {
    chatValue = baseChatValue([
      todoCall([{ content: "Current plan", status: "in_progress" }]),
      {
        session_id: "session-1",
        exchange_id: "exchange-1",
        rank: 2,
        timestamp: "2026-09-17T00:00:01.000Z",
        role: "assistant",
        channel: "final",
        parts: [{ type: "text", text: "Done" }],
      },
    ]);

    const html = renderToStaticMarkup(<ManagedChatPage />);
    expect(html).not.toContain('data-testid="agent-todo-panel"');
    expect(html).toContain("rework.agentTodoPanel.announcementComplete");
  });

  it("removes the panel when the streamed final retains an earlier array slot", () => {
    chatValue = baseChatValue([
      {
        session_id: "session-1",
        exchange_id: "exchange-1",
        rank: 0,
        timestamp: "2026-09-17T00:00:01.000Z",
        role: "assistant",
        channel: "final",
        parts: [{ type: "text", text: "Done" }],
      },
      todoCall([{ content: "Current plan", status: "in_progress" }]),
    ]);

    const html = renderToStaticMarkup(<ManagedChatPage />);
    expect(html).not.toContain('data-testid="agent-todo-panel"');
    expect(html).toContain("rework.agentTodoPanel.announcementComplete");
  });

  it("does not mount a panel for an explicit empty snapshot", () => {
    chatValue = baseChatValue([todoCall([])]);

    const html = renderToStaticMarkup(<ManagedChatPage />);
    expect(html).not.toContain('data-testid="agent-todo-panel"');
    expect(html).toContain("rework.agentTodoPanel.announcementComplete");
  });
});

describe("ManagedChatPage deleted agent", () => {
  it("labels the preserved name, freezes the thread and disables the composer without a redundant banner", () => {
    chatValue = {
      ...baseChatValue([]),
      executionDisabled: true,
      isReadOnly: true,
      agentDisplayName: "Preserved assistant",
      isHistorySettled: true,
    };
    const html = renderToStaticMarkup(<ManagedChatPage />);
    expect(html).toContain("Preserved assistant");
    expect(html).toContain("chatbot.deletedAgentSuffix");
    expect(html).toContain('data-agent-deleted="true"');
    expect(html).toContain('data-placeholder="chatbot.readOnlyComposerPlaceholder"');
    expect(html).toContain('data-description="chatbot.deletedAgentTooltip"');
    const rendered = document.createElement("div");
    rendered.innerHTML = html;
    expect(rendered.textContent).not.toContain("chatbot.deletedAgentTooltip");
    expect(html).toContain('data-composer-disabled="true"');
    expect(html).toContain('data-send-disabled="true"');
    expect(html).toContain('data-readonly="true"');
    expect(html).not.toContain('aria-label="chatbot.newConversation"');
  });
  it("shows history failure without labeling a live agent as deleted", () => {
    chatValue = { ...baseChatValue([]), historyUnavailable: true, isReadOnly: false, isHistorySettled: true };
    const html = renderToStaticMarkup(<ManagedChatPage />);
    expect(html).toContain("chatbot.historyUnavailable");
    expect(html).not.toContain("chatbot.deletedAgentTooltip");
  });
});

describe("ManagedChatPage new conversation action", () => {
  it("keeps the header on a bound session whose history came back empty", () => {
    chatValue = { ...baseChatValue([]), threadMessages: [], startNewConversation: vi.fn() };
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(<ManagedChatPage />);
    });
    expect(container.querySelector('[class*="topBar"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="chatbot.newConversation"]')).not.toBeNull();

    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it("starts an empty chat that names the same agent and hides the action there", () => {
    const startNewConversation = vi.fn();
    chatValue = { ...baseChatValue([]), startNewConversation };
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(<ManagedChatPage />);
    });
    const button = container.querySelector<HTMLButtonElement>('button[aria-label="chatbot.newConversation"]');
    expect(button).not.toBeNull();
    expect(container.textContent).toContain("Agent");

    act(() => {
      button?.click();
    });
    expect(startNewConversation).toHaveBeenCalledOnce();

    chatValue = {
      ...chatValue,
      agentInstance: { display_name: "Contract Reviewer", role: "Reviews supplier contracts" },
      sessionId: null,
      sessionTitle: null,
      threadMessages: [],
    };
    act(() => {
      root.render(<ManagedChatPage />);
    });
    expect(container.textContent).toContain("Contract Reviewer");
    expect(container.textContent).toContain("Reviews supplier contracts");
    expect(container.querySelector('[class*="topBar"]')).toBeNull();
    expect(container.querySelector('[data-testid="composer"]')).not.toBeNull();
    expect(container.querySelector('button[aria-label="chatbot.newConversation"]')).toBeNull();

    act(() => {
      root.unmount();
    });
    container.remove();
  });
});

// A capability can ask for its own panel back (the document card's opener, a
// live agent write). That path bypasses the page's open/close handler, so
// without recording here a panel the user then left open would not be restored
// on re-entry — the record would only ever reflect openings they clicked.
const memoryStorage = (): Storage => {
  const map = new Map<string, string>();
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => {
      map.set(k, v);
    },
    removeItem: (k: string) => {
      map.delete(k);
    },
    clear: () => map.clear(),
    key: (i: number) => [...map.keys()][i] ?? null,
    get length() {
      return map.size;
    },
  } as Storage;
};

describe("ManagedChatPage capability panel memory", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
    openRequest.requestId = 0;
    openRequest.key = null;
    chatValue = {
      ...chatValue,
      capabilityIds: ["writable_document", "ppt_filler"],
      sessionId: "session-1",
      isHistorySettled: true,
    };
  });

  const mount = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<ManagedChatPage />);
    });
  };

  const rerender = () =>
    act(() => {
      root.render(<ManagedChatPage />);
    });

  const openPanel = (key: string) => {
    openRequest.requestId += 1;
    openRequest.key = key;
    rerender();
  };

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("records the panel as open when a capability asks for it to be opened", async () => {
    const { wasPanelOpen } = await import("../../../features/capabilities/capabilityPanelMemory");
    mount();

    expect(wasPanelOpen("session-1", PANEL_KEY)).toBe(false);

    openPanel(PANEL_KEY);

    expect(wasPanelOpen("session-1", PANEL_KEY)).toBe(true);
  });

  it("retires the panel it replaces — only one drawer is open, so only one can be remembered", async () => {
    const { wasPanelOpen } = await import("../../../features/capabilities/capabilityPanelMemory");
    mount();
    openPanel(PANEL_KEY);
    openPanel(OTHER_PANEL_KEY);

    expect(wasPanelOpen("session-1", OTHER_PANEL_KEY)).toBe(true);
    expect(wasPanelOpen("session-1", PANEL_KEY)).toBe(false);
  });

  // The page closes the drawer itself on a conversation switch. That close is
  // ours, not the user's, and it lands while the state still describes the
  // conversation being left — so it must touch neither side's record.
  it("leaves both conversations' records alone when the user switches between them", async () => {
    const { rememberPanelOpen, wasPanelOpen } = await import("../../../features/capabilities/capabilityPanelMemory");
    rememberPanelOpen("session-2", PANEL_KEY);
    mount();
    openPanel(PANEL_KEY);

    chatValue = { ...chatValue, sessionId: "session-2" };
    rerender();
    rerender();

    // The one being entered keeps the record that will restore its panel...
    expect(wasPanelOpen("session-2", PANEL_KEY)).toBe(true);
    // ...and the one being left keeps the panel it was left with.
    expect(wasPanelOpen("session-1", PANEL_KEY)).toBe(true);
  });

  // A panel opened on a blank chat, then the first send mints the session. The
  // drawer is deliberately kept across that bind, so what is open belongs to
  // the conversation just created — and has to be recorded under it.
  it("records a panel that was already open when the first send bound the session", async () => {
    const { wasPanelOpen } = await import("../../../features/capabilities/capabilityPanelMemory");
    chatValue = { ...chatValue, sessionId: null };
    mount();
    openPanel(PANEL_KEY);

    chatValue = { ...chatValue, sessionId: "session-1" };
    rerender();
    rerender();

    expect(wasPanelOpen("session-1", PANEL_KEY)).toBe(true);
  });

  it("records nothing for a conversation whose panel was never opened", async () => {
    const { wasPanelOpen } = await import("../../../features/capabilities/capabilityPanelMemory");
    mount();
    rerender();

    expect(wasPanelOpen("session-1", PANEL_KEY)).toBe(false);
  });
});

// Restoring a panel mounts an editor whose first render is one long synchronous
// task. On a conversation whose thread is still loading it lands on an empty
// column and delays the messages — which is what the user actually opened.
describe("ManagedChatPage restores a panel behind the conversation", () => {
  let container: HTMLDivElement;
  let root: Root;

  const mount = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<ManagedChatPage />);
    });
  };

  const rerender = () =>
    act(() => {
      root.render(<ManagedChatPage />);
    });

  const requestOpen = (key: string) => {
    openRequest.requestId += 1;
    openRequest.key = key;
    rerender();
  };

  const panelIsOpen = () => container.querySelector('[data-testid="capability-panel"]') !== null;

  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
    openRequest.requestId = 0;
    openRequest.key = null;
    chatValue = {
      ...chatValue,
      capabilityIds: ["writable_document"],
      sessionId: "session-1",
      threadMessages: [],
      isHistorySettled: false,
    };
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("holds the restore while the thread is still loading, then applies it", () => {
    mount();
    requestOpen(PANEL_KEY);

    expect(panelIsOpen()).toBe(false);

    // The history lands: the thread renders, and the held request goes through.
    chatValue = { ...chatValue, threadMessages: [renderedTurn], isHistorySettled: true };
    rerender();

    expect(panelIsOpen()).toBe(true);
  });

  it("applies immediately once the conversation is on screen — a live write must not wait", () => {
    chatValue = { ...chatValue, threadMessages: [renderedTurn], isHistorySettled: true };
    mount();
    requestOpen(PANEL_KEY);

    expect(panelIsOpen()).toBe(true);
  });

  it("applies on an empty conversation once history has settled with nothing to show", () => {
    chatValue = { ...chatValue, isHistorySettled: true };
    mount();
    requestOpen(PANEL_KEY);

    expect(panelIsOpen()).toBe(true);
  });

  // Without the hold this could not happen: the request applied on the spot and
  // anything the user did afterwards simply won. Holding it opens a window in
  // which they can act, so the request has to yield to them rather than land a
  // second later on top of whatever they chose.
  it("drops a held request when the user opens another drawer while it waits", () => {
    mount();
    requestOpen(PANEL_KEY);

    act(() => {
      const promptLibrary = rail.launchers.find((l) => l.key === "prompt-library");
      expect(promptLibrary).toBeDefined();
      promptLibrary?.onOpen();
    });
    chatValue = { ...chatValue, threadMessages: [renderedTurn], isHistorySettled: true };
    rerender();

    expect(panelIsOpen()).toBe(false);
  });

  it.each([
    ["an admin", "team-1", ["full-reasoning", "debug"]],
    ["a member of a shared team", "personal-team", ["full-reasoning"]],
  ])("offers %s the full reasoning at the rail's foot", (_label, activeTeamId, keys) => {
    bootstrap.activeTeamId = activeTeamId;
    try {
      mount();
      expect(rail.footerLaunchers.map((l) => l.key)).toEqual(keys);
      // The glyph a reasoning row carries in the chain of thought.
      expect(rail.footerLaunchers[0]).toMatchObject({ icon: "settings", iconFilled: true });
    } finally {
      bootstrap.activeTeamId = "team-1";
    }
  });

  it("drops a held request when the user leaves for another conversation", () => {
    mount();
    requestOpen(PANEL_KEY);

    chatValue = { ...chatValue, sessionId: "session-2" };
    rerender();
    chatValue = { ...chatValue, threadMessages: [renderedTurn], isHistorySettled: true };
    rerender();

    expect(panelIsOpen()).toBe(false);
  });
});

// Entering a conversation, its messages land a moment after the click. For that
// moment the page held no messages and nothing said a load was under way, so it
// rendered the welcome stage — "start a new conversation" flashing on the way
// into an existing one.
describe("ManagedChatPage — the welcome stage waits for the history to answer", () => {
  let container: HTMLDivElement;
  let root: Root;

  const show = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<ManagedChatPage />);
    });
  };

  const threadEl = () => container.querySelector('[data-testid="thread"]');
  const welcomeIsShown = () => threadEl() === null;

  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
    openRequest.requestId = 0;
    openRequest.key = null;
    chatValue = {
      ...chatValue,
      capabilityIds: [],
      pendingHitl: null,
      waitResponse: false,
      threadMessages: [],
      sessionId: "session-1",
      isHistorySettled: false,
    };
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("shows the loading state, not the welcome, while the conversation is unresolved", () => {
    show();

    expect(welcomeIsShown()).toBe(false);
    expect(threadEl()?.getAttribute("data-loading")).toBe("true");
  });

  it("shows the welcome once the history has answered that there is nothing", () => {
    chatValue = { ...chatValue, isHistorySettled: true };
    show();

    expect(welcomeIsShown()).toBe(true);
  });

  it("stops loading as soon as the messages are there", () => {
    chatValue = { ...chatValue, threadMessages: [renderedTurn] };
    show();

    expect(threadEl()?.getAttribute("data-loading")).toBe("false");
  });

  // A chat with no session has no history to resolve — making it wait would put
  // a spinner in front of the one screen that is genuinely empty by nature.
  it("shows the welcome straight away on a conversation that has not been minted yet", () => {
    chatValue = { ...chatValue, sessionId: null, isHistorySettled: true };
    show();

    expect(welcomeIsShown()).toBe(true);
  });
});

// Focus used to fall out of the composer being RE-ENABLED after a history load,
// so it happened only when a load actually ran — a conversation served from the
// cache silently got none, and which conversations those are is arbitrary.
describe("ManagedChatPage — entering a conversation puts the cursor in the composer", () => {
  let container: HTMLDivElement;
  let root: Root;

  const show = () =>
    act(() => {
      root.render(<ManagedChatPage />);
    });

  const focusRequest = () => container.querySelector('[data-testid="composer"]')?.getAttribute("data-focus-request");

  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
    openRequest.requestId = 0;
    openRequest.key = null;
    chatValue = { ...chatValue, capabilityIds: [], sessionId: "session-1", isHistorySettled: true };
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    show();
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("asks the composer to focus when the conversation changes", () => {
    const before = focusRequest();

    chatValue = { ...chatValue, sessionId: "session-2" };
    show();

    expect(focusRequest()).not.toBe(before);
  });

  it("does not ask again while the same conversation stays open", () => {
    chatValue = { ...chatValue, sessionId: "session-2" };
    show();
    const after = focusRequest();

    show();

    expect(focusRequest()).toBe(after);
  });
});

describe("ManagedChatPage — arrow keys recall sent messages", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("puts the last sent line back in the composer, a command turn as typed", () => {
    vi.stubGlobal("localStorage", memoryStorage());
    const setInput = vi.fn();
    chatValue = {
      ...chatValue,
      capabilityIds: [],
      sessionId: "session-1",
      isHistorySettled: true,
      input: "",
      setInput,
      waitResponse: false,
      isLoadingHistory: false,
      pendingHitl: null,
      threadMessages: [
        { id: "u1", role: "user", text: "Hello", isStreaming: false, traceMessages: [] },
        {
          id: "u2",
          role: "user",
          text: "Résume le document en :\n\nfocus on risks",
          isStreaming: false,
          traceMessages: [],
          command: { command: "summary", appended_text: "focus on risks", prompt_id: "p", prompt_name: "Résumé" },
        },
      ],
    };
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<ManagedChatPage />);
    });

    const preventDefault = vi.fn();
    let consumed = false;
    act(() => {
      consumed =
        composerKeys.recall?.({ key: "ArrowUp", preventDefault, nativeEvent: { isComposing: false } }) ?? false;
    });

    expect(consumed).toBe(true);
    expect(setInput).toHaveBeenCalledWith("/summary focus on risks");
  });
});

describe("ManagedChatPage — the model list follows admin changes made elsewhere", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.stubGlobal("localStorage", memoryStorage());
    modelRead.refetch.mockClear();
    modelRead.fulfilledTimeStamp = Date.now() - 31_000;
    chatValue = { ...chatValue, sessionId: "session-1", isHistorySettled: true };
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<ManagedChatPage />);
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("refetches the model list when the window regains focus", () => {
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });

    expect(modelRead.refetch).toHaveBeenCalledTimes(1);
  });

  // Each read also asks the pod for its catalog: tab switching must not hammer it.
  it("skips a focus refetch when the last read is under 30 seconds old", () => {
    modelRead.fulfilledTimeStamp = Date.now() - 5_000;
    act(() => {
      root.render(<ManagedChatPage />);
    });
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });

    expect(modelRead.refetch).not.toHaveBeenCalled();
  });

  it("refetches the model list when another conversation opens, not on a plain re-render", () => {
    act(() => {
      root.render(<ManagedChatPage />);
    });
    expect(modelRead.refetch).not.toHaveBeenCalled();

    chatValue = { ...chatValue, sessionId: "session-2" };
    act(() => {
      root.render(<ManagedChatPage />);
    });

    expect(modelRead.refetch).toHaveBeenCalledTimes(1);
  });

  it("stops reading the model list once the conversation's agent is deleted", () => {
    expect(modelRead.options?.skip).toBeFalsy();

    chatValue = { ...chatValue, sessionId: "session-2", isReadOnly: true, executionDisabled: true };
    act(() => {
      root.render(<ManagedChatPage />);
    });
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });

    expect(modelRead.options?.skip).toBe(true);
    expect(modelRead.refetch).not.toHaveBeenCalled();
  });
});

describe("ManagedChatPage skill preview", () => {
  it.each([
    { origin: "user", child: false },
    { origin: "agent", child: false },
    { origin: "agent", child: true },
  ])("previews a $origin load from its trace row and toggles it closed (child: $child)", ({ origin, child }) => {
    const load: ChatMessage = {
      session_id: "session-1",
      exchange_id: "exchange-1",
      rank: 1,
      timestamp: "2026-10-07T10:00:00Z",
      role: "system",
      channel: "system_note",
      parts: [{ type: "text", text: "Loaded instructions" }],
      metadata: { extras: { skill_load: { name: "meeting-minutes", origin, load_id: "load", child } } },
    };
    chatValue = baseChatValue([load]);
    chatValue.threadMessages = [{ ...renderedTurn, traceMessages: [load] }];
    chatValue.input = "Keep my draft";
    const setInput = vi.fn();
    const handleSend = vi.fn();
    chatValue.setInput = setInput;
    chatValue.handleSend = handleSend;
    previewResult.currentData = {
      skill: { name: "meeting-minutes", description: "Prepare meeting minutes", argument_hint: "[notes]" },
      revision: "snapshot",
      content: "## Minutes\nRead **notes**.",
    };
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    try {
      act(() => root.render(<ManagedChatPage />));
      const skill = container.querySelector<HTMLButtonElement>(
        '[aria-label="1. chatbot.skills.loaded: meeting-minutes"]',
      );
      expect(skill?.type).toBe("button");
      act(() => skill!.click());
      expect(skillPreviewQuery).toHaveBeenLastCalledWith(
        { teamId: "team-1", agentInstanceId: "agent-1", skillName: "meeting-minutes" },
        { skip: false, refetchOnMountOrArgChange: true },
      );
      expect(container.querySelector('aside[data-open="true"]')?.textContent).toContain("Prepare meeting minutes");
      expect(container.querySelector("strong")?.textContent).toBe("notes");
      act(() => skill!.click());
      expect(container.textContent).not.toContain("Prepare meeting minutes");
      expect(setInput).not.toHaveBeenCalled();
      expect(handleSend).not.toHaveBeenCalled();
    } finally {
      act(() => root.unmount());
      container.remove();
      previewResult.currentData = undefined;
    }
  });

  it("opens the exclusive right-hand panel without sending or changing the selected request", () => {
    chatValue = baseChatValue([]);
    chatValue.input = "/compare-options Keep this request";
    const setInput = vi.fn();
    const handleSend = vi.fn();
    chatValue.setInput = setInput;
    chatValue.handleSend = handleSend;
    previewResult.currentData = {
      skill: { name: "compare-options", description: "Compare alternatives", argument_hint: "[options]" },
      revision: "snapshot",
      content: "---\nname: compare-options\n---\n## Procedure\nRead **evidence**.",
    };
    previewResult.error = undefined;
    previewResult.isFetching = false;
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    try {
      act(() => root.render(<ManagedChatPage />));
      expect(skillPreviewQuery).toHaveBeenLastCalledWith(
        { teamId: "team-1", agentInstanceId: "agent-1", skillName: "" },
        { skip: true, refetchOnMountOrArgChange: true },
      );
      const skill = container.querySelector<HTMLButtonElement>('[aria-label="chatbot.skills.open"]');
      expect(skill).not.toBeNull();
      expect(skill?.title).toBe("chatbot.skills.platformProvided\nCompare");
      expect(container.querySelector('[data-testid="composer"]')?.getAttribute("data-placeholder")).toBe("[options]");
      act(() => skill!.click());
      expect(skillPreviewQuery).toHaveBeenLastCalledWith(
        { teamId: "team-1", agentInstanceId: "agent-1", skillName: "compare-options" },
        { skip: false, refetchOnMountOrArgChange: true },
      );
      expect(container.textContent).not.toContain("chatbot.skills.currentVersion");
      expect(container.querySelector('aside[data-open="true"]')?.getAttribute("data-title-size")).toBe("large");
      expect(container.textContent).toContain("Compare alternatives");
      expect(container.querySelector("strong")?.textContent).toBe("evidence");
      expect(container.textContent).not.toContain("name: compare-options");
      expect(setInput).not.toHaveBeenCalled();
      expect(handleSend).not.toHaveBeenCalled();
      act(() => skill!.click());
      expect(container.textContent).not.toContain("Compare alternatives");
      expect(skillPreviewQuery).toHaveBeenLastCalledWith(
        { teamId: "team-1", agentInstanceId: "agent-1", skillName: "" },
        { skip: true, refetchOnMountOrArgChange: true },
      );
      act(() => skill!.click());
      expect(container.textContent).toContain("Compare alternatives");
      act(() => rail.footerLaunchers.find((launcher) => launcher.key === "full-reasoning")!.onOpen());
      expect(container.textContent).not.toContain("Compare alternatives");
      chatValue.input = "/review ";
      act(() => root.render(<ManagedChatPage />));
      expect(container.querySelector('[data-testid="composer"]')?.getAttribute("data-placeholder")).toBe(
        "chatbot.skills.requestPlaceholder",
      );
      chatValue.input = "";
      act(() => root.render(<ManagedChatPage />));
      expect(container.querySelector('[data-testid="composer"]')?.getAttribute("data-placeholder")).toBe(
        "chatbot.composerPlaceholder",
      );
      expect(setInput).not.toHaveBeenCalled();
      expect(handleSend).not.toHaveBeenCalled();
    } finally {
      act(() => root.unmount());
      container.remove();
      previewResult.currentData = undefined;
    }
  });
});

describe("ManagedChatPage skill reference preview", () => {
  it.each(["read_skill_file", "read_file"])(
    "opens stored file text from %s by keyboard, replaces the skill and toggles closed without changing the draft",
    (toolName) => {
      const common = { session_id: "session-1", exchange_id: "exchange-1", timestamp: "2026-10-07T10:00:00Z" };
      const call: ChatMessage = {
        ...common,
        rank: 1,
        role: "assistant",
        channel: "tool_call",
        parts: [
          {
            type: "tool_call",
            call_id: "ref",
            name: toolName,
            args:
              toolName === "read_file"
                ? { file_path: "/skills/compare-options/references/model.md", offset: 1, limit: 1 }
                : { name: "compare-options", path: "references/model.md" },
          },
        ],
      };
      const result: ChatMessage = {
        ...common,
        rank: 2,
        role: "tool",
        channel: "tool_result",
        parts: [{ type: "tool_result", call_id: "ref", ok: true, content: "## Stored reference\n**Historical** text" }],
      };
      chatValue = baseChatValue([call, result]);
      chatValue.threadMessages = [{ ...renderedTurn, traceMessages: [call, result] }];
      chatValue.input = "/compare-options Keep draft";
      const setInput = vi.fn();
      chatValue.setInput = setInput;
      const handleSend = vi.fn();
      chatValue.handleSend = handleSend;
      previewResult.currentData = {
        skill: { name: "compare-options", description: "Current skill description" },
        revision: "now",
        content: "Current instructions",
      };
      const container = document.createElement("div");
      document.body.appendChild(container);
      const root = createRoot(container);
      try {
        act(() => root.render(<ManagedChatPage />));
        act(() => container.querySelector<HTMLButtonElement>('[aria-label="chatbot.skills.open"]')!.click());
        expect(container.textContent).toContain("Current skill description");
        const row = container.querySelector<HTMLElement>(
          '[aria-label="1. rework.chatTrace.toolLabels.platform.readSkillFile: references/model.md"]',
        );
        expect(row).not.toBeNull();
        act(() => row!.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true })));
        expect(container.textContent).not.toContain("Current skill description");
        expect(container.querySelector('aside[data-open="true"]')?.textContent).toContain("Historical");
        expect(skillPreviewQuery).toHaveBeenLastCalledWith(
          expect.objectContaining({ skillName: "" }),
          expect.objectContaining({ skip: true }),
        );
        act(() => row!.click());
        expect(container.querySelector('aside[data-open="true"]')).toBeNull();
        expect(setInput).not.toHaveBeenCalled();
        expect(handleSend).not.toHaveBeenCalled();
      } finally {
        act(() => root.unmount());
        container.remove();
        previewResult.currentData = undefined;
      }
    },
  );
});

describe("ManagedChatPage slash prompt sources", () => {
  it("reads the personal commands in a team chat without waiting for the agent's kind", () => {
    bootstrap.activeTeamId = "personal-1";
    chatValue = { ...baseChatValue([]), agentInstance: { template_id: "runtime:agent-1" } };
    commandQueries.mockClear();
    renderToStaticMarkup(<ManagedChatPage />);
    expect(commandQueries.mock.calls.slice(-2)).toEqual([
      [{ teamId: "team-1" }, { skip: false }],
      [{ teamId: "personal-1" }, { skip: false }],
    ]);
    bootstrap.activeTeamId = "team-1";
  });
});

describe("ManagedChatPage prompt token preview", () => {
  it("opens the prompt behind the composer token in the side panel and toggles it closed", () => {
    teamCommands.current = [
      { prompt_id: "p-summary", name: "Résumé", command: "summary", description: "Résumer", emoji: null },
    ];
    fetchedTeam.current = { id: "team-1", name: "Finance" };
    bootstrap.activeTeamId = "personal-1";
    chatValue = baseChatValue([]);
    chatValue.input = "/summary keep this";
    const setInput = vi.fn();
    const handleSend = vi.fn();
    chatValue.setInput = setInput;
    chatValue.handleSend = handleSend;
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    const panel = () => container.querySelector('aside[data-open="true"]');
    try {
      act(() => root.render(<ManagedChatPage />));
      const token = container.querySelector<HTMLButtonElement>('[data-testid="prompt-token"]')!;
      expect(token.dataset.teamName).toBe("Finance");
      expect(panel()).toBeNull();

      promptPreviewResult.isFetching = true;
      act(() => token.click());
      expect(promptPreviewFetch).toHaveBeenCalledWith({ teamId: "team-1", promptId: "p-summary" });
      expect(panel()?.textContent).toContain("Résumé");
      expect(panel()?.textContent).toContain("/summary");
      expect(panel()?.querySelector('[role="status"]')?.textContent).toBe("chatbot.commandTurn.previewLoading");

      promptPreviewResult.isFetching = false;
      promptPreviewResult.currentData = { text: "Résume le document en trois points." };
      act(() => root.render(<ManagedChatPage />));
      expect(panel()?.querySelector('[role="status"]')).toBeNull();
      // Name, then command, then the instructions.
      expect(panel()?.textContent).toMatch(/Résumé\/summaryRésume le document en trois points\.$/);

      promptPreviewResult.isError = true;
      act(() => root.render(<ManagedChatPage />));
      expect(panel()?.querySelector('[role="status"]')?.textContent).toBe("chatbot.commandTurn.previewError");
      expect(panel()?.textContent).not.toContain("trois points");

      act(() => token.click());
      expect(panel()).toBeNull();
      expect(promptPreviewFetch).toHaveBeenCalledOnce();
      expect(setInput).not.toHaveBeenCalled();
      expect(handleSend).not.toHaveBeenCalled();
    } finally {
      act(() => root.unmount());
      container.remove();
      teamCommands.current = [];
      fetchedTeam.current = undefined;
      bootstrap.activeTeamId = "team-1";
      Object.assign(promptPreviewResult, { currentData: undefined, isFetching: false, isError: false });
    }
  });
});

describe("ManagedChatPage with several prompt commands", () => {
  let container: HTMLDivElement;
  let root: Root;
  const panel = () => container.querySelector('aside[data-open="true"]');
  const tokens = () => Array.from(container.querySelectorAll<HTMLButtonElement>('[data-testid="prompt-token"]'));

  function mount(input: string) {
    teamCommands.current = [
      { prompt_id: "p-summary", name: "Résumé", command: "summary", description: "Résumer", emoji: null },
      { prompt_id: "p-tone", name: "Ton", command: "tone", description: "Ton formel", emoji: null },
    ];
    chatValue = baseChatValue([]);
    chatValue.input = input;
    chatValue.setInput = vi.fn();
    chatValue.handleSend = vi.fn();
    chatValue.runCommand = vi.fn();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root.render(<ManagedChatPage />));
  }

  beforeEach(() => {
    showError.mockClear();
    promptPreviewFetch.mockClear();
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    teamCommands.current = [];
    promptRead.current = async () => ({ text: "" });
    Object.assign(promptPreviewResult, { currentData: undefined, isFetching: false, isError: false });
  });

  it("previews the prompt of the activated composer token, and closes on a second click", () => {
    mount("/summary then /tone now");
    expect(tokens().map((token) => token.textContent)).toEqual(["Résumé", "Ton"]);

    act(() => tokens()[1].click());
    expect(promptPreviewFetch).toHaveBeenLastCalledWith({ teamId: "team-1", promptId: "p-tone" });
    expect(panel()?.textContent).toContain("Ton/tone");

    act(() => tokens()[0].click());
    expect(promptPreviewFetch).toHaveBeenLastCalledWith({ teamId: "team-1", promptId: "p-summary" });
    expect(panel()?.textContent).toContain("Résumé/summary");
    expect(panel()?.textContent).not.toContain("/tone");

    act(() => tokens()[0].click());
    expect(panel()).toBeNull();
    expect(promptPreviewFetch).toHaveBeenCalledTimes(2);
    expect(chatValue.runCommand).not.toHaveBeenCalled();
  });

  it.each([
    { status: 404, key: "chatbot.commandMenu.runErrorStale" },
    { status: 500, key: "chatbot.commandMenu.runErrorDetail" },
  ])("names the command that held the message back when its read answers $status", async ({ status, key }) => {
    mount("/summary then /tone now");
    promptRead.current = ({ promptId }) =>
      promptId === "p-tone" ? Promise.reject({ status, data: {} }) : Promise.resolve({ text: "Summarise." });
    await act(async () => composerKeys.send?.());

    expect(showError).toHaveBeenCalledExactlyOnceWith({
      summary: "chatbot.commandMenu.runErrorSummary",
      detail: `${key}:tone`,
    });
    expect(chatValue.runCommand).not.toHaveBeenCalled();
    expect(chatValue.handleSend).not.toHaveBeenCalled();
  });

  it("states the limit when the message holds too many prompt commands", async () => {
    mount(Array.from({ length: 17 }, () => "/summary").join(" ") + " end");
    promptRead.current = async () => ({ text: "Summarise." });
    await act(async () => composerKeys.send?.());

    expect(showError).toHaveBeenCalledExactlyOnceWith({
      summary: "chatbot.commandMenu.runErrorSummary",
      detail: "chatbot.commandMenu.runErrorTooMany:16",
    });
    expect(chatValue.runCommand).not.toHaveBeenCalled();
  });

  it("sends the assembled text of every prompt with its list", async () => {
    mount("/summary then /tone now");
    promptRead.current = async ({ promptId }) => ({ text: promptId === "p-tone" ? "Be formal." : "Summarise." });
    await act(async () => composerKeys.send?.());

    expect(showError).not.toHaveBeenCalled();
    expect(chatValue.runCommand).toHaveBeenCalledExactlyOnceWith({
      text: "Summarise.\n\nthen\n\nBe formal.\n\nnow",
      command: expect.objectContaining({
        command: "summary",
        appended_text: "then\n\nnow",
        prompts: [
          expect.objectContaining({ command: "summary", text_offset: 0, text_length: 10 }),
          expect.objectContaining({ command: "tone", text_offset: 18, text_length: 10 }),
        ],
      }),
    });
  });

  describe("the panel of a sent message", () => {
    const text = "First\n\nSummarise the document.\n\nthen\n\nUse a formal tone.\n\nplease";
    const command = {
      command: "summary",
      prompt_id: "p-summary",
      prompt_name: "Weekly review",
      appended_text: "First\n\nthen\n\nplease",
      draft_text: "First /summary then /tone please",
      draft_command_offset: 6,
      prompts: [
        {
          command: "summary",
          prompt_id: "p-summary",
          prompt_name: "Weekly review",
          draft_offset: 6,
          text_offset: 7,
          text_length: 23,
        },
        {
          command: "tone",
          prompt_id: "p-tone",
          prompt_name: "Formal",
          draft_offset: 20,
          text_offset: 38,
          text_length: 18,
        },
      ],
    };

    it("shows only the text of the activated prompt, under its own name and command", () => {
      mount("");
      act(() => threadProps.openCommandPrompt?.({ text, command, promptIndex: 1 }));
      expect(panel()?.textContent).toMatch(/Formal\/toneUse a formal tone\.$/);
      for (const other of ["First", "then", "please", "Summarise", "Weekly review"])
        expect(panel()?.textContent).not.toContain(other);

      act(() => threadProps.openCommandPrompt?.({ text, command, promptIndex: 0 }));
      expect(panel()?.textContent).toMatch(/Weekly review\/summarySummarise the document\.$/);
      expect(panel()?.textContent).not.toContain("formal tone");
      // The library is never read for a sent message.
      expect(promptPreviewFetch).not.toHaveBeenCalled();
    });

    it("no longer shows the user's words for a single listed prompt", () => {
      mount("");
      const single = {
        command: "summary",
        prompt_name: "Weekly review",
        appended_text: "the report",
        draft_text: "/summary the report",
        draft_command_offset: 0,
        prompts: [
          { command: "summary", prompt_name: "Weekly review", draft_offset: 0, text_offset: 0, text_length: 23 },
        ],
      };
      act(() =>
        threadProps.openCommandPrompt?.({
          text: "Summarise the document.\n\nthe report",
          command: single,
          promptIndex: 0,
        }),
      );
      expect(panel()?.textContent).toMatch(/Weekly review\/summarySummarise the document\.$/);
      expect(panel()?.textContent).not.toContain("the report");
    });

    it("shows the whole sent text for a turn that has no usable list", () => {
      mount("");
      const { prompts: _prompts, ...old } = command;
      act(() => threadProps.openCommandPrompt?.({ text, command: old }));
      expect(panel()?.textContent).toContain("Weekly review/summary");
      expect(panel()?.textContent).toContain("Use a formal tone.");
      expect(panel()?.textContent).toContain("please");

      // A list that does not fit the stored text is ignored the same way.
      act(() => threadProps.openCommandPrompt?.({ text: "short", command, promptIndex: 1 }));
      expect(panel()?.textContent).toMatch(/Weekly review\/summaryshort$/);
    });
  });
});
