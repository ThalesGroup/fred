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

import { useRef } from "react";
import { useParams } from "react-router-dom";
import { ConversationThread } from "./ConversationThread/ConversationThread";
import { ComposerSettingsControls } from "@shared/organisms/ComposerSettingsControls/ComposerSettingsControls";
import { RichInputField } from "@shared/molecules/RichInputField/RichInputField";
import { SessionTitleEditor } from "@shared/molecules/SessionTitleEditor/SessionTitleEditor";
import { useManagedChat } from "./useManagedChat";
import styles from "./ManagedChatPage.module.css";

export default function ManagedChatPage() {
  const { teamId, agentInstanceId } = useParams<{ teamId: string; agentInstanceId: string }>();

  if (!teamId || !agentInstanceId) {
    return <div className={styles.error}>Missing team or agent context in URL.</div>;
  }

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const chat = useManagedChat({ teamId, agentInstanceId });

  const opts = chat.effectiveChatOptions;
  const hasComposerControls =
    opts?.libraries_selection === true ||
    opts?.search_policy_selection === true ||
    opts?.rag_scope_selection === true;

  return (
    <div className={styles.page}>
      {/* Session title — floats top-left, zero layout impact */}
      <div className={styles.topBar}>
        <div className={styles.topBarTitle}>
          {chat.sessionId && chat.sessionTitle != null && (
            <SessionTitleEditor title={chat.sessionTitle} onCommit={chat.commitTitle} />
          )}
        </div>
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
    </div>
  );
}
