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
import { ContextPromptChips } from "@shared/molecules/ContextPromptChips/ContextPromptChips";
import { SessionAttachmentsDrawer } from "@shared/molecules/SessionAttachmentsDrawer/SessionAttachmentsDrawer";
import { TraceDetailDrawer } from "@shared/molecules/ThoughtTrace/TraceDetailDrawer/TraceDetailDrawer";
import { TraceDrawerProvider } from "@shared/molecules/ThoughtTrace/traceDrawerContext";
import { findTraceEntry, traceEntryKey, type TraceEntry } from "../../../utils/traceUtils";
import { ComposerActionsMenu } from "@shared/molecules/ComposerActionsMenu/ComposerActionsMenu";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { CapabilitySidePanelHost } from "../../../features/capabilities/CapabilitySidePanelHost";
import { ComposerControlSlot } from "../../../features/capabilities/ComposerControlSlot";
import { selectSidePanelOpenRequest } from "../../../features/capabilities/sidePanelOpenRequestSlice";
import { useManagedChat } from "./useManagedChat";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
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
    { kind: "attachments" } | { kind: "capability"; key: string } | null
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
  const [transcribeAudio] = useTranscribeAudioKnowledgeFlowV1AudioTranscriptionsPostMutation();
  // Re-resolved every render from the live messages so the open drawer streams.
  const selectedTraceEntry = selectedTraceKey ? findTraceEntry(chat.messages, selectedTraceKey) : null;
  const isInitialState =
    chat.threadMessages.length === 0 && !chat.waitResponse && !chat.isLoadingHistory && chat.pendingHitl == null;

  const attachmentsCount = chat.persistedAttachments.length;
  // CAPAB-01 #1976: attachments are allowed when the resolved chat controls
  // (ExecutionPreparation.chat_controls) include an `attach_files` descriptor —
  // supersedes the retired `EffectiveChatOptions.attach_files`.
  const allowChatAttachments = chat.chatControls.some((control) => control.widget === "attach_files");
  // The composer options menu always renders: even when an agent exposes no
  // search options, the chat-context prompts row is always available (personal +
  // team library + platform defaults).

  // Attached chat-context prompts resolved to their summaries, in selection order.
  const attachedContextPrompts = chat.contextPromptIds
    .map((id) => chat.contextPrompts.find((prompt) => prompt.id === id))
    .filter((prompt): prompt is (typeof chat.contextPrompts)[number] => prompt != null);

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

  const handleFilesSelected = (files: FileList | null) => {
    if (!allowChatAttachments) return;
    const selected = Array.from(files ?? []);
    if (selected.length > 0) chat.handleAddAttachments(selected, "picker");
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
    if (files.length > 0) chat.handleAddAttachments(files, "drop");
  };

  const composer = (
    <RichInputField
      value={chat.input}
      onChange={chat.setInput}
      onSend={chat.handleSend}
      onInterrupt={chat.handleAbort}
      disabled={chat.waitResponse || chat.isLoadingHistory}
      sendDisabled={chat.attachmentsUploading}
      enableVoiceInput
      onTranscribeAudio={handleTranscribeAudio}
      voiceInputDisabled={chat.waitResponse || chat.isLoadingHistory}
      onVoiceInputError={reportVoiceInputError}
      showSendButton
      compactLayout={isInitialState}
      aboveTextSlot={
        attachedContextPrompts.length > 0 || chat.attachments.length > 0 ? (
          <>
            {attachedContextPrompts.length > 0 && (
              <ContextPromptChips
                prompts={attachedContextPrompts}
                onRemove={(id) => chat.setContextPrompts(chat.contextPromptIds.filter((existing) => existing !== id))}
              />
            )}
            {chat.attachments.length > 0 && (
              <AttachmentChips attachments={chat.attachments} onRemove={chat.removeAttachment} />
            )}
          </>
        ) : undefined
      }
      leftSlot={
        <ComposerActionsMenu disabled={chat.waitResponse || chat.isLoadingHistory}>
          {({ closeMenu }) => (
            <ComposerControlSlot
              chatControls={chat.chatControls}
              onRequestClose={closeMenu}
              composer={{
                teamId,
                onAttach: () => fileInputRef.current?.click(),
                selectedLibraryIds: chat.selectedLibraryIds,
                onSelectedLibraryIdsChange: chat.setSelectedLibraryIds,
                selectedDocumentUids: chat.selectedDocumentUids,
                onSelectedDocumentUidsChange: chat.setSelectedDocumentUids,
                searchPolicy: chat.searchPolicy,
                onSearchPolicyChange: chat.setSearchPolicy,
                ragScope: chat.ragScope,
                onRagScopeChange: chat.setRagScope,
              }}
              contextPrompts={chat.contextPrompts}
              contextPromptIds={chat.contextPromptIds}
              onContextPromptIdsChange={chat.setContextPrompts}
            />
          )}
        </ComposerActionsMenu>
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
        {/* Main column — flexes to fill the row; the push drawer shifts it left */}
        <div className={styles.mainColumn}>
          {allowChatAttachments && dragActive && (
            <div className={styles.dropOverlay} aria-hidden>
              <div className={styles.dropOverlayContent}>
                <span className={styles.dropOverlayPlus}>+</span>
                <span className={styles.dropOverlayLabel}>{t("chatbot.dropFilesHere")}</span>
              </div>
            </div>
          )}
          {/* Session title — floats top-left, zero layout impact */}
          <div className={styles.topBar}>
            <div className={styles.topBarTitle}>
              {chat.sessionId && chat.sessionTitle != null && (
                <SessionTitleEditor title={chat.sessionTitle} onCommit={chat.commitTitle} />
              )}
            </div>
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
                  color="on-surface"
                  variant="icon"
                  size="small"
                  icon={{ category: "outlined", type: "build" }}
                  aria-label={t("chatbot.toggleDebugDrawer")}
                  onClick={() => setDebugOpen((v) => !v)}
                />
              )}
            </div>
          </div>

          <div
            className={`${styles.chatArea} ${isInitialState ? styles.chatAreaInitial : ""}`}
            ref={scrollContainerRef}
          >
            {isInitialState ? (
              <div className={styles.initialStage}>
                <ManagedChatWelcome />
                <div className={styles.initialComposer}>{composer}</div>
              </div>
            ) : (
              <ConversationThread
                messages={chat.threadMessages}
                pendingHitl={chat.pendingHitl}
                isLoading={chat.isLoadingHistory}
                isStreaming={chat.waitResponse}
                scrollContainerRef={scrollContainerRef}
                onHitlAnswer={chat.handleHitlAnswer}
              />
            )}
          </div>

          {!isInitialState && <div className={styles.inputOverlay}>{composer}</div>}
        </div>

        {/* Capability side-panel slot (#1979) — mounts as a flex sibling of the
            main column so its push drawer reflows the conversation left. */}
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
        <TraceDetailDrawer entry={selectedTraceEntry} onClose={() => setSelectedTraceKey(null)} />
        {isAdmin && <DebugRawDrawer open={debugOpen} onClose={() => setDebugOpen(false)} messages={chat.messages} />}
      </div>
    </TraceDrawerProvider>
  );
}
