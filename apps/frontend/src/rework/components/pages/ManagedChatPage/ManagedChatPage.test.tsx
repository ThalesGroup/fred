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

import { type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-router-dom", () => ({ useParams: () => ({ teamId: "team-1", agentInstanceId: "agent-1" }) }));
vi.mock("react-redux", () => ({ useSelector: () => ({ requestId: 0, key: null }) }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

let chatValue: Record<string, unknown>;
vi.mock("./useManagedChat", () => ({ useManagedChat: () => chatValue }));
vi.mock("@shared/molecules/RichInputField/RichInputField", () => ({
  RichInputField: (props: { sendDisabled?: boolean; characterCount?: number; characterLimit?: number }) => (
    <div
      data-testid="composer"
      data-send-disabled={props.sendDisabled}
      data-character-count={props.characterCount}
      data-character-limit={props.characterLimit}
    />
  ),
}));
vi.mock("./ConversationThread/ConversationThread", () => ({
  ConversationThread: (props: { maxChatInputChars?: number; hitlFreeText: string; onHitlFreeTextChange: unknown }) => (
    <div
      data-testid="thread"
      data-character-limit={props.maxChatInputChars}
      data-hitl-draft={props.hitlFreeText}
      data-has-hitl-change-handler={typeof props.onHitlFreeTextChange === "function"}
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
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery: () => [
    () => ({ unwrap: async () => ({ text: "" }) }),
  ],
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
vi.mock("../../../features/capabilities/CapabilitySidePanelHost", () => ({ CapabilitySidePanelHost: () => null }));
vi.mock("../../../features/capabilities/ComposerControlSlot", () => ({ ComposerControlSlot: () => null }));
vi.mock("../../../features/capabilities/ComposerOptionChips", () => ({
  COMPOSER_CHIP_WIDGETS: new Set<string>(),
  ComposerOptionChips: () => null,
}));
vi.mock("@shared/molecules/ComposerActionsMenu/ComposerActionsMenu", () => ({
  ComposerActionsMenu: () => null,
}));

import ManagedChatPage from "./ManagedChatPage";

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
      contextPrompts: [],
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
