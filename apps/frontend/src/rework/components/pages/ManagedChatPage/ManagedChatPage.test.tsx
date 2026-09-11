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

import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-router-dom", () => ({ useParams: () => ({ teamId: "team-1", agentInstanceId: "agent-1" }) }));
vi.mock("react-redux", () => ({ useSelector: () => ({ requestId: 0, key: null }) }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

let chatValue: Record<string, unknown>;
vi.mock("./useManagedChat", () => ({ useManagedChat: () => chatValue }));
vi.mock("@shared/molecules/RichInputField/RichInputField", () => ({
  RichInputField: (props: {
    sendDisabled?: boolean;
    characterCount?: number;
    characterLimit?: number;
    focusEndRequestId?: number;
  }) => (
    <div
      data-testid="composer"
      data-send-disabled={props.sendDisabled}
      data-character-count={props.characterCount}
      data-character-limit={props.characterLimit}
      data-focus-request={props.focusEndRequestId}
    />
  ),
}));
vi.mock("./ConversationThread/ConversationThread", () => ({
  ConversationThread: (props: {
    maxChatInputChars?: number;
    hitlFreeText: string;
    onHitlFreeTextChange: unknown;
    isLoading?: boolean;
  }) => (
    <div
      data-testid="thread"
      data-character-limit={props.maxChatInputChars}
      data-hitl-draft={props.hitlFreeText}
      data-has-hitl-change-handler={typeof props.onHitlFreeTextChange === "function"}
      data-loading={props.isLoading}
    />
  ),
}));

vi.mock("@shared/molecules/ThoughtTrace/traceDrawerContext", () => ({
  TraceDrawerProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("../../../../hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({ activeTeam: { id: "team-1" } }),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: undefined }),
  // #2387 — the composer's model label. Undefined here: this file covers the
  // chat-input policy wiring, and the label's own behaviour is covered in
  // ReasoningChip.test.tsx.
  useEffectiveChatModelQuery: () => ({ data: undefined }),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: () => [
    () => ({ unwrap: async () => ({ text: "" }) }),
  ],
  // Read by the prompt-selection panel the page mounts; it is closed here, so
  // the queries are skipped and only their shape matters.
  useGetContextPromptsEarlyControlPlaneV1TeamsTeamIdPromptsContextGetQuery: () => ({
    data: [],
    isLoading: false,
  }),
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery: () => ({ data: [] }),
}));
vi.mock("@hooks/useTeamCapabilities.ts", () => ({
  useTeamCapabilities: () => ({ canAdministerAdmins: false }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: () => undefined }),
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
vi.mock("@shared/molecules/DebugRawDrawer/DebugRawDrawer", () => ({ DebugRawDrawer: () => null }));
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
vi.mock("@shared/atoms/IconButton/IconButton", () => ({ default: () => null }));
vi.mock("@shared/molecules/TokenUsageBadge/TokenUsageBadge", () => ({ TokenUsageBadge: () => null }));
vi.mock("../../../features/capabilities/CapabilitySidePanelHost", () => ({
  CapabilitySidePanelHost: () => null,
}));
vi.mock("../../../features/capabilities/ChatLauncherRail", () => ({ ChatLauncherRail: () => null }));
vi.mock("../../../features/capabilities/ComposerControlSlot", () => ({ ComposerControlSlot: () => null }));
vi.mock("../../../features/capabilities/ComposerOptionChips", () => ({
  COMPOSER_CHIP_WIDGETS: new Set<string>(),
  ComposerOptionChips: () => null,
}));
vi.mock("@shared/molecules/ComposerActionsMenu/ComposerActionsMenu", () => ({
  ComposerActionsMenu: () => null,
}));

import ManagedChatPage from "./ManagedChatPage";

// The page reads the last turn (auto-scroll, outline rail), so a stand-in has
// to carry the fields it looks at, not just an id.
const renderedTurn = { id: "m1", role: "assistant", text: "hello", isStreaming: false, traceMessages: [] };

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
