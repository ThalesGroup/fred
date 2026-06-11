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

import { DragEvent, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ConversationThread } from "./ConversationThread/ConversationThread";
import { ComposerSettingsControls } from "@shared/organisms/ComposerSettingsControls/ComposerSettingsControls";
import { RichInputField } from "@shared/molecules/RichInputField/RichInputField";
import { SessionTitleEditor } from "@shared/molecules/SessionTitleEditor/SessionTitleEditor";
import { DebugRawDrawer } from "@shared/molecules/DebugRawDrawer/DebugRawDrawer";
import { AttachmentChips } from "@shared/molecules/AttachmentChips/AttachmentChips";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useManagedChat } from "./useManagedChat";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./ManagedChatPage.module.css";

export default function ManagedChatPage() {
  const { teamId, agentInstanceId } = useParams<{ teamId: string; agentInstanceId: string }>();

  if (!teamId || !agentInstanceId) {
    return <div className={styles.error}>Missing team or agent context in URL.</div>;
  }

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  const { activeTeam } = useFrontendBootstrap();
  const isPersonalTeam = teamId === activeTeam?.id;
  const { data: fetchedTeam } = useGetTeamQuery({ teamId }, { skip: !teamId || isPersonalTeam });
  const team = isPersonalTeam ? activeTeam : fetchedTeam;
  const isAdmin =
    isPersonalTeam || (Array.isArray(team?.permissions) && team.permissions.includes("can_administer_owners"));

  const chat = useManagedChat({ teamId, agentInstanceId });

  const opts = chat.effectiveChatOptions;
  const hasComposerControls =
    opts?.libraries_selection === true || opts?.search_policy_selection === true || opts?.rag_scope_selection === true;

  const handleFilesSelected = (files: FileList | null) => {
    const selected = Array.from(files ?? []);
    if (selected.length > 0) chat.handleAddAttachments(selected, "picker");
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDragActive(true);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDragActive(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) chat.handleAddAttachments(files, "drop");
  };

  return (
    <div
      className={styles.page}
      onDragEnter={handleDragOver}
      onDragOver={handleDragOver}
      onDragLeave={(event) => {
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
      {dragActive && (
        <div className={styles.dropOverlay} aria-hidden>
          <div className={styles.dropOverlayContent}>
            <span className={styles.dropOverlayPlus}>+</span>
            <span className={styles.dropOverlayLabel}>Drop files here</span>
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
        {isAdmin && (
          <div className={styles.topBarActions}>
            <IconButton
              color="on-surface"
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "build" }}
              aria-label="Toggle debug drawer"
              onClick={() => setDebugOpen((v) => !v)}
            />
          </div>
        )}
      </div>

      {/* Scroll container — input bar is NOT inside here so it never affects scrollHeight */}
      <div className={styles.chatArea} ref={scrollContainerRef}>
        <ConversationThread
          messages={chat.threadMessages}
          pendingHitl={chat.pendingHitl}
          isLoading={chat.isLoadingHistory}
          isStreaming={chat.waitResponse}
          scrollContainerRef={scrollContainerRef}
          onHitlAnswer={chat.handleHitlAnswer}
        />
      </div>

      {/* Floating input bar — absolutely positioned overlay, zero layout impact on scroll */}
      <div className={styles.inputOverlay}>
        <RichInputField
          value={chat.input}
          onChange={chat.setInput}
          onSend={chat.handleSend}
          onInterrupt={chat.handleAbort}
          disabled={chat.waitResponse || chat.isLoadingHistory}
          showSendButton
          aboveTextSlot={
            chat.attachments.length > 0 ? (
              <AttachmentChips attachments={chat.attachments} onRemove={chat.removeAttachment} />
            ) : undefined
          }
          leftSlot={
            <IconButton
              color="on-surface"
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "attach_file" }}
              aria-label="Attach files"
              disabled={chat.waitResponse || chat.isLoadingHistory}
              onClick={() => fileInputRef.current?.click()}
            />
          }
          topSlot={
            hasComposerControls ? (
              <ComposerSettingsControls
                teamId={teamId}
                selectedLibraryIds={chat.selectedLibraryIds}
                onLibraryChange={chat.setSelectedLibraryIds}
                searchPolicy={chat.searchPolicy}
                onSearchPolicyChange={chat.setSearchPolicy}
                ragScope={chat.ragScope}
                onRagScopeChange={chat.setRagScope}
                options={opts}
                boundLibraryIds={opts?.bound_library_ids ?? undefined}
              />
            ) : undefined
          }
        />
      </div>
      {isAdmin && <DebugRawDrawer open={debugOpen} onClose={() => setDebugOpen(false)} messages={chat.messages} />}
    </div>
  );
}
