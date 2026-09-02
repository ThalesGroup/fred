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

import { DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import { ConversationThread } from "./ConversationThread/ConversationThread";
import { RichInputField } from "@shared/molecules/RichInputField/RichInputField";
import { SessionTitleEditor } from "@shared/molecules/SessionTitleEditor/SessionTitleEditor";
import { DebugRawDrawer } from "@shared/molecules/DebugRawDrawer/DebugRawDrawer";
import { AttachmentChips } from "@shared/molecules/AttachmentChips/AttachmentChips";
import { SessionAttachmentsDrawer } from "@shared/molecules/SessionAttachmentsDrawer/SessionAttachmentsDrawer";
import { DocumentScopePanel } from "@shared/molecules/DocumentScopePanel/DocumentScopePanel";
import { TraceDetailDrawer } from "@shared/molecules/ThoughtTrace/TraceDetailDrawer/TraceDetailDrawer";
import { TraceDrawerProvider } from "@shared/molecules/ThoughtTrace/traceDrawerContext";
import { findTraceEntry, traceEntryKey, type TraceEntry } from "../../../utils/traceUtils";
import { ComposerActionsMenu } from "@shared/molecules/ComposerActionsMenu/ComposerActionsMenu";
import { UploadWarningAckDialog } from "@shared/molecules/UploadWarningAckDialog/UploadWarningAckDialog";
import IconButton from "@shared/atoms/IconButton/IconButton";
import {
  CapabilityLauncherRail,
  CapabilitySidePanelHost,
} from "../../../features/capabilities/CapabilitySidePanelHost";
import { ComposerControlSlot } from "../../../features/capabilities/ComposerControlSlot";
import { COMPOSER_CHIP_WIDGETS, ReasoningChip } from "../../../features/capabilities/ReasoningChip";
import { selectSidePanelOpenRequest } from "../../../features/capabilities/sidePanelOpenRequestSlice";
import { conversationTokenTotals } from "./toThreadMessages";
import { useManagedChat } from "./useManagedChat";
import { useUploadWarningAcknowledgement } from "../../../core/hooks/useUploadWarningAcknowledgement";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap";
import {
  useEffectiveChatModelQuery,
  useGetTeamQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
  type ContextPromptSummary,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { useTranscribeAudioKnowledgeFlowV1AudioTranscriptionsPostMutation } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { transcribeAudioClip } from "./knowledgeFlowTranscription";
import styles from "./ManagedChatPage.module.css";

const WELCOME_VARIANT_KEYS = [
  "chatbot.startConversationVariantAnalyze",
  "chatbot.startConversationVariantDraft",
  "chatbot.startConversationVariantExplore",
  "chatbot.startConversationVariantSearch",
] as const;

function pickWelcomeVariant(previous: number | null): number {
  const next = Math.floor(Math.random() * WELCOME_VARIANT_KEYS.length);
  if (previous == null || WELCOME_VARIANT_KEYS.length < 2 || next !== previous) {
    return next;
  }
  return (next + 1) % WELCOME_VARIANT_KEYS.length;
}

function ManagedChatWelcome() {
  const { t } = useTranslation();
  const firstName = KeyCloakService.GetUserGivenName();
  const [variantIndex] = useState(() => pickWelcomeVariant(null));
  const welcomeName = firstName ?? t("chatbot.welcomeFallback");

  return (
    <div className={styles.welcomeBlock}>
      <p className={styles.welcomeTitle}>{t(WELCOME_VARIANT_KEYS[variantIndex], { username: welcomeName })}</p>
    </div>
  );
}

export default function ManagedChatPage() {
  const { t, i18n } = useTranslation();
  const { teamId, agentInstanceId } = useParams<{ teamId: string; agentInstanceId: string }>();
  const { showError } = useToast();

  if (!teamId || !agentInstanceId) {
    return <div className={styles.error}>{t("chatbot.errors.missingContext")}</div>;
  }

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  // The capability side-panel and the session attachments drawer are both
  // `InlineDrawer layout="push"` — sharing one slot keeps at most one open at
  // a time so their widths never cumulate.
  const [activePushDrawer, setActivePushDrawer] = useState<
    { kind: "attachments" } | { kind: "capability"; key: string } | { kind: "document-scope" } | null
  >(null);
  const attachmentsDrawerOpen = activePushDrawer?.kind === "attachments";

  // Capability part renderers may request their own panel to open (#1903,
  // e.g. the ppt_filler preview card after a fill): watch the request counter
  // and open the named panel — this page stays the single open-state authority.
  const sidePanelOpenRequest = useSelector(selectSidePanelOpenRequest);
  const lastSidePanelRequestId = useRef(sidePanelOpenRequest.requestId);
  useEffect(() => {
    if (sidePanelOpenRequest.requestId === lastSidePanelRequestId.current) return;
    lastSidePanelRequestId.current = sidePanelOpenRequest.requestId;
    if (sidePanelOpenRequest.key) {
      setActivePushDrawer({ kind: "capability", key: sidePanelOpenRequest.key });
    }
  }, [sidePanelOpenRequest]);
  const [dragActive, setDragActive] = useState(false);
  // Trace detail panel state is lifted here so the drawer is a sibling of the main
  // column. We store the selected entry's *key* (not a snapshot) and re-resolve it
  // against the live message list below, so reasoning streams into the open drawer
  // as deltas arrive. Trace rows open it through TraceDrawerProvider.
  const [selectedTraceKey, setSelectedTraceKey] = useState<string | null>(null);
  const traceDrawerApi = useMemo(
    () => ({ openTrace: (entry: TraceEntry) => setSelectedTraceKey(traceEntryKey(entry)) }),
    [],
  );

  const { activeTeam } = useFrontendBootstrap();
  const isPersonalTeam = teamId === activeTeam?.id;
  const { data: fetchedTeam } = useGetTeamQuery({ teamId }, { skip: isPersonalTeam });
  const team = isPersonalTeam ? activeTeam : fetchedTeam;
  const { canAdministerAdmins } = useTeamCapabilities(team);
  const isAdmin = isPersonalTeam || canAdministerAdmins;

  const chat = useManagedChat({ teamId, agentInstanceId });

  // Opening a push drawer is a statement about ONE conversation, so switching
  // conversations closes it: the panels (capability, attachments, document
  // scope) all read the open session, and a drawer carried across would sit
  // there empty. A capability whose new conversation warrants its panel asks
  // for it again through the request counter above.
  const lastDrawerSessionId = useRef(chat.sessionId);
  useEffect(() => {
    if (lastDrawerSessionId.current === chat.sessionId) return;
    // Binding the FIRST conversation of a page load is not a switch - a panel a
    // probe just asked for must not be closed under it.
    const wasBound = Boolean(lastDrawerSessionId.current);
    lastDrawerSessionId.current = chat.sessionId;
    if (wasBound) setActivePushDrawer(null);
  }, [chat.sessionId]);
  // The model this agent's next turn will actually route to (#2387) — the
  // composer's label. Its own read rather than part of prepare-execution:
  // prepare runs on every send and is contractually free of pod-catalog
  // fetches, while resolving the pod-owned precedence levels needs one.
  // Tagged ControlPlaneRoutingPolicy/teamId, so saving a routing policy
  // refetches this instead of leaving a stale model name on screen.
  const { data: effectiveChatModel } = useEffectiveChatModelQuery({ teamId, agentInstanceId });
  const [transcribeAudio] = useTranscribeAudioKnowledgeFlowV1AudioTranscriptionsPostMutation();
  // Re-resolved every render from the live messages so the open drawer streams.
  const selectedTraceEntry = selectedTraceKey ? findTraceEntry(chat.messages, selectedTraceKey) : null;
  const isInitialState =
    chat.threadMessages.length === 0 && !chat.waitResponse && !chat.isLoadingHistory && chat.pendingHitl == null;

  const attachmentsCount = chat.persistedAttachments.length;

  const conversationTokens = useMemo(() => conversationTokenTotals(chat.threadMessages), [chat.threadMessages]);
  // CAPAB-01 #1976: attachments are allowed when the resolved chat controls
  // (ExecutionPreparation.chat_controls) include an `attach_files` descriptor —
  // supersedes the retired `EffectiveChatOptions.attach_files`.
  const allowChatAttachments = chat.chatControls.some((control) => control.widget === "attach_files");
  // The composer options menu always renders: even when an agent exposes no
  // search options, the prompt-library row is always available (personal +
  // team library + platform defaults).

  // Picking a library prompt inserts its content straight into the composer draft
  // (it is not attached as a session-context chip). The prompt text lives on the
  // full record, not the summary, so we fetch it on demand; personal-scope prompts
  // are stored under the user's personal team, team-scope under the chat team.
  const [fetchPrompt] = useLazyGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery();
  // Bumped alongside chat.setInput below to ask RichInputField to refocus with
  // the caret at the end of the just-inserted prompt (batched into one render).
  const [focusEndRequestId, setFocusEndRequestId] = useState(0);
  const insertContextPrompt = async (prompt: ContextPromptSummary) => {
    const promptTeamId = prompt.scope === "personal" ? activeTeam?.id : teamId;
    if (!promptTeamId) return;
    try {
      const detail = await fetchPrompt({ teamId: promptTeamId, promptId: prompt.id }).unwrap();
      const text = detail.text?.trim();
      if (!text) return;
      chat.setInput(chat.input.trim().length > 0 ? `${chat.input}\n\n${text}` : text);
      setFocusEndRequestId((n) => n + 1);
    } catch {
      showError({
        summary: t("chatbot.contextPrompts.insertErrorSummary"),
        detail: t("chatbot.contextPrompts.insertErrorDetail"),
      });
    }
  };

  const reportVoiceInputError = (message: string) => {
    showError({
      summary: t("chatbot.voiceInputErrorSummary"),
      detail: message,
    });
  };

  const handleTranscribeAudio = async (file: File): Promise<string> => {
    const language = i18n.language?.split("-")[0] || undefined;
    return transcribeAudioClip(
      (formData) =>
        transcribeAudio({ bodyTranscribeAudioKnowledgeFlowV1AudioTranscriptionsPost: formData as never }).unwrap(),
      file,
      { language },
    );
  };

  // First-file gate: while the deployer-configured upload warning is
  // unacknowledged, adds from both entry points (picker and drop) are parked
  // here and only forwarded once the user accepts the dialog. Cancel drops them.
  const { requiresAcknowledgement, acknowledge } = useUploadWarningAcknowledgement();
  const [pendingAttachments, setPendingAttachments] = useState<{ files: File[]; source: "picker" | "drop" } | null>(
    null,
  );

  const addAttachments = (files: File[], source: "picker" | "drop") => {
    if (requiresAcknowledgement) {
      setPendingAttachments({ files, source });
      return;
    }
    chat.handleAddAttachments(files, source);
  };

  const handleFilesSelected = (files: FileList | null) => {
    if (!allowChatAttachments) return;
    const selected = Array.from(files ?? []);
    if (selected.length > 0) addAttachments(selected, "picker");
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (!allowChatAttachments) return;
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDragActive(true);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    if (!allowChatAttachments) return;
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDragActive(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) addAttachments(files, "drop");
  };

  // Resolve the `document_scope` widget's params once (#2259) — shared by the
  // tune-menu launcher row, the tune badge, and the side panel. `libraries` /
  // `documents` gate which sections the picker shows; `bound_library_ids`
  // (non-null) means the agent binds specific libraries at creation, so the
  // library scope is read-only and reset returns to that bound baseline.
  const documentScopeParams = chat.chatControls.find((c) => c.widget === "document_scope")?.params as
    | { libraries?: boolean; documents?: boolean; bound_library_ids?: string[] | null }
    | undefined;
  const documentScopeBoundLibraryIds = documentScopeParams?.bound_library_ids ?? [];
  const documentScopeHasBound = documentScopeBoundLibraryIds.length > 0;
  // A ponctual (per-turn) narrowing exists when the user selected something
  // beyond the agent's configured scope. A bound agent can't change libraries
  // (read-only), so only a document narrowing counts there. Drives the tune
  // badge and the panel's reset-enabled state.
  const hasPonctualDocumentScope =
    (!documentScopeHasBound && chat.selectedLibraryIds.length > 0) || chat.selectedDocumentUids.length > 0;

  // Shared composer state read/written by every chat-turn control, mounted in
  // both the "add" (primary) and "tune" (tools) popovers.
  const composerState = {
    teamId,
    onAttach: () => fileInputRef.current?.click(),
    selectedLibraryIds: chat.selectedLibraryIds,
    onSelectedLibraryIdsChange: chat.setSelectedLibraryIds,
    selectedDocumentUids: chat.selectedDocumentUids,
    onSelectedDocumentUidsChange: chat.setSelectedDocumentUids,
    // The document_scope tune row calls this to open the side panel (#2259).
    onOpenDocumentScopePanel: () => setActivePushDrawer({ kind: "document-scope" }),
    searchPolicy: chat.searchPolicy,
    onSearchPolicyChange: chat.setSearchPolicy,
    ragScope: chat.ragScope,
    onRagScopeChange: chat.setRagScope,
    reasoning: chat.reasoning,
    onReasoningChange: chat.setReasoning,
  };
  // The "tune" button only appears when the agent exposes tool controls the
  // tune popover actually renders — i.e. any chat control that isn't the
  // attach action (lives in the "add" menu) and isn't one of
  // COMPOSER_CHIP_WIDGETS (promoted to the always-visible right-edge
  // ReasoningChip instead, see below) — otherwise an agent exposing only
  // those two would show a "tune" button that opens onto an empty popover.
  const hasToolControls = chat.chatControls.some(
    (control) => control.widget !== "attach_files" && !COMPOSER_CHIP_WIDGETS.has(control.widget),
  );
  const composerControlsDisabled = chat.waitResponse || chat.isLoadingHistory;

  const composer = (
    <RichInputField
      value={chat.input}
      onChange={chat.setInput}
      onSend={chat.handleSend}
      onInterrupt={chat.handleAbort}
      disabled={chat.waitResponse || chat.isLoadingHistory}
      sendDisabled={chat.attachmentsUploading || chat.inputTooLong}
      characterCount={chat.inputCharacterCount}
      characterLimit={chat.maxChatInputChars}
      enableVoiceInput
      onTranscribeAudio={handleTranscribeAudio}
      voiceInputDisabled={chat.waitResponse || chat.isLoadingHistory}
      onVoiceInputError={reportVoiceInputError}
      focusEndRequestId={focusEndRequestId}
      showSendButton
      aboveTextSlot={
        chat.attachments.length > 0 ? (
          <AttachmentChips attachments={chat.attachments} onRemove={chat.removeAttachment} />
        ) : undefined
      }
      rightExtraSlot={
        <ReasoningChip
          chatControls={chat.chatControls}
          composer={composerState}
          disabled={composerControlsDisabled}
          effectiveModel={effectiveChatModel}
        />
      }
      leftSlot={
        <>
          <ComposerActionsMenu disabled={composerControlsDisabled}>
            {({ closeMenu }) => (
              <ComposerControlSlot
                part="primary"
                chatControls={chat.chatControls}
                onRequestClose={closeMenu}
                composer={composerState}
                contextPrompts={chat.contextPrompts}
                onInsertContextPrompt={insertContextPrompt}
              />
            )}
          </ComposerActionsMenu>
          {hasToolControls && (
            <ComposerActionsMenu
              disabled={composerControlsDisabled}
              icon={{ category: "outlined", type: "tune" }}
              openAriaLabel={t("chatbot.composerActions.tuneOpenAria")}
              dialogAriaLabel={t("chatbot.composerActions.tuneDialogAria")}
              badge={hasPonctualDocumentScope}
            >
              {({ closeMenu }) => (
                <ComposerControlSlot
                  part="tools"
                  chatControls={chat.chatControls}
                  onRequestClose={closeMenu}
                  composer={composerState}
                />
              )}
            </ComposerActionsMenu>
          )}
        </>
      }
    />
  );

  return (
    <TraceDrawerProvider value={traceDrawerApi}>
      <div
        className={styles.page}
        onDragEnter={handleDragOver}
        onDragOver={handleDragOver}
        onDragLeave={(event) => {
          if (!allowChatAttachments) return;
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
          setDragActive(false);
        }}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          hidden
          onChange={(event) => {
            handleFilesSelected(event.currentTarget.files);
            event.currentTarget.value = "";
          }}
        />
        {/* Page body — a row of [ left stack ][ full-height push drawers ]. A
            side panel now reflows the WHOLE left stack (header included) instead
            of sliding under the header, so viewers span the full page height. */}
        <div className={styles.pageBody}>
          <div className={styles.leftStack}>
            {/* Conversation header. When a side panel opens it reflows left
            together with the content below — the panel sits at the page body's
            right edge at full height, no longer under this bar. The inner row is
            capped to the composer field width so title and composer stay aligned.
            data-picker-top-boundary: the composer's anchored pickers
            (usePickerMenuMaxHeight) stop just below this bar. */}
            <div className={styles.topBar} data-picker-top-boundary>
              <div className={styles.topBarInner}>
                <div className={styles.topBarTitle}>
                  {chat.sessionId && chat.sessionTitle != null && (
                    <div className={styles.topBarTitleRow}>
                      <span className={styles.titleLabel}>
                        {chat.sessionTitle || t("chatbot.sessionTitleEditor.untitled")}
                      </span>
                      {/* Absolutely positioned: reserves no layout space, revealed on topBar hover */}
                      <span className={styles.editButtonSlot}>
                        <SessionTitleEditor title={chat.sessionTitle} onCommit={chat.commitTitle} />
                      </span>
                    </div>
                  )}
                  <div className={styles.topBarAgentName}>{chat.agentDisplayName}</div>
                </div>
                <div className={styles.topBarRight}>
                  {conversationTokens.total_tokens > 0 && (
                    <span className={styles.conversationTokens}>
                      {t("chatbot.conversationTokenUsage.total", { count: conversationTokens.total_tokens })}
                    </span>
                  )}
                  <div className={styles.topBarActions}>
                    {attachmentsCount > 0 && (
                      <button
                        type="button"
                        className={styles.conversationFilesButton}
                        onClick={() =>
                          setActivePushDrawer((v) => (v?.kind === "attachments" ? null : { kind: "attachments" }))
                        }
                      >
                        <span className={styles.conversationFilesLabel}>{t("chatbot.conversationFiles")}</span>
                        <span className={styles.conversationFilesBadge}>{attachmentsCount}</span>
                      </button>
                    )}
                    {isAdmin && (
                      <IconButton
                        variant="icon"
                        size="small"
                        icon={{ category: "outlined", type: "build" }}
                        aria-label={t("chatbot.toggleDebugDrawer")}
                        onClick={() => setDebugOpen((v) => !v)}
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Conversation column — holds only the main column now; the push drawers
            moved up to the page body so they reflow the header too. */}
            <div className={styles.contentRow}>
              <div className={styles.mainColumn}>
                {allowChatAttachments && dragActive && (
                  <div className={styles.dropOverlay} aria-hidden>
                    <div className={styles.dropOverlayContent}>
                      <span className={styles.dropOverlayPlus}>+</span>
                      <span className={styles.dropOverlayLabel}>{t("chatbot.dropFilesHere")}</span>
                    </div>
                  </div>
                )}

                <div
                  className={`${styles.chatArea} ${isInitialState ? styles.chatAreaInitial : ""}`}
                  ref={scrollContainerRef}
                >
                  {isInitialState ? (
                    <div className={styles.initialStage}>
                      <ManagedChatWelcome />
                      <div className={styles.initialComposer}>
                        {composer}
                        <div className={styles.aiDisclaimer}>{t("chatbot.aiDisclaimer")}</div>
                      </div>
                    </div>
                  ) : (
                    <ConversationThread
                      messages={chat.threadMessages}
                      pendingHitl={chat.pendingHitl}
                      isLoading={chat.isLoadingHistory}
                      isStreaming={chat.waitResponse}
                      scrollContainerRef={scrollContainerRef}
                      onHitlAnswer={chat.handleHitlAnswer}
                      maxChatInputChars={chat.maxChatInputChars}
                      hitlFreeText={chat.hitlFreeText}
                      onHitlFreeTextChange={chat.setHitlFreeText}
                    />
                  )}
                </div>

                {!isInitialState && (
                  <div className={styles.inputOverlay}>
                    {composer}
                    <div className={styles.aiDisclaimer}>{t("chatbot.aiDisclaimer")}</div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Capability side-panel slot — full-height sibling of the left stack:
            its push drawer reflows the header and the conversation together. */}
          <CapabilitySidePanelHost
            capabilityIds={chat.capabilityIds}
            activeKey={activePushDrawer?.kind === "capability" ? activePushDrawer.key : null}
            onActiveKeyChange={(key) => setActivePushDrawer(key ? { kind: "capability", key } : null)}
          />

          <SessionAttachmentsDrawer
            open={attachmentsDrawerOpen}
            onClose={() => setActivePushDrawer((v) => (v?.kind === "attachments" ? null : v))}
            attachments={chat.persistedAttachments}
            isLoading={chat.isHydratingAttachments}
            onDelete={(attachmentId) => {
              void chat.deletePersistedAttachment(attachmentId);
            }}
          />

          {/* Document-scope side panel (#2259) — opened from the tune menu's
            document_scope row, sharing the single push-drawer slot above so it
            never stacks with the attachments / capability panels. Only mounted
            when the agent exposes the control. */}
          {documentScopeParams && (
            <DocumentScopePanel
              open={activePushDrawer?.kind === "document-scope"}
              onClose={() => setActivePushDrawer((v) => (v?.kind === "document-scope" ? null : v))}
              teamId={teamId}
              showLibraries={documentScopeParams.libraries === true}
              showDocuments={documentScopeParams.documents === true}
              boundLibraryIds={documentScopeBoundLibraryIds}
              selectedLibraryIds={chat.selectedLibraryIds}
              onSelectedLibraryIdsChange={chat.setSelectedLibraryIds}
              selectedDocumentUids={chat.selectedDocumentUids}
              onSelectedDocumentUidsChange={chat.setSelectedDocumentUids}
              canReset={hasPonctualDocumentScope}
              onReset={() => {
                chat.setSelectedLibraryIds([]);
                chat.setSelectedDocumentUids([]);
              }}
            />
          )}
        </div>
        {/* /pageBody */}

        {/* Launcher rail — page-root sibling of the body (not inside it) so it
            reserves its own in-flow column at the far right. */}
        <CapabilityLauncherRail
          capabilityIds={chat.capabilityIds}
          activeKey={activePushDrawer?.kind === "capability" ? activePushDrawer.key : null}
          onActiveKeyChange={(key) => setActivePushDrawer(key ? { kind: "capability", key } : null)}
        />

        <TraceDetailDrawer entry={selectedTraceEntry} onClose={() => setSelectedTraceKey(null)} />
        {isAdmin && <DebugRawDrawer open={debugOpen} onClose={() => setDebugOpen(false)} messages={chat.messages} />}
        <UploadWarningAckDialog
          open={pendingAttachments !== null}
          onConfirm={() => {
            acknowledge();
            if (pendingAttachments) chat.handleAddAttachments(pendingAttachments.files, pendingAttachments.source);
            setPendingAttachments(null);
          }}
          onCancel={() => setPendingAttachments(null)}
        />
      </div>
    </TraceDrawerProvider>
  );
}
