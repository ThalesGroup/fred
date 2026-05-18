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

import { useParams } from "react-router-dom";
import { RichInputField } from "@shared/molecules/RichInputField/RichInputField";
import { AgentOptionsPanel } from "@shared/organisms/AgentOptionsPanel/AgentOptionsPanel";
import { ConversationHeader } from "@shared/organisms/ConversationHeader/ConversationHeader";
import { ConversationThread } from "@shared/organisms/ConversationThread/ConversationThread";
import { useManagedChat } from "./useManagedChat";
import styles from "./ManagedChatPage.module.css";

export default function ManagedChatPage() {
  const { teamId, agentInstanceId } = useParams<{ teamId: string; agentInstanceId: string }>();

  if (!teamId || !agentInstanceId) {
    return <div className={styles.error}>Missing team or agent context in URL.</div>;
  }

  const chat = useManagedChat({ teamId, agentInstanceId });

  return (
    <div className={styles.page}>
      <ConversationHeader
        agentDisplayName={chat.agentDisplayName}
        sessionId={chat.sessionId}
        sessionTitle={chat.sessionTitle}
        rightPanelOpen={chat.rightPanelOpen}
        onTitleCommit={chat.commitTitle}
        onNewConversation={chat.startNewConversation}
        onToggleRightPanel={() => chat.setRightPanelOpen((p) => !p)}
      />

      <div className={styles.body}>
        <div className={styles.chatColumn}>
          <ConversationThread
            messages={chat.threadMessages}
            pendingHitl={chat.pendingHitl}
            isLoading={chat.isLoadingHistory}
            isStreaming={chat.waitResponse}
            scrollVersion={chat.messages.length}
            onHitlAnswer={chat.handleHitlAnswer}
          />
          <RichInputField
            value={chat.input}
            onChange={chat.setInput}
            onSend={chat.handleSend}
            disabled={chat.waitResponse || chat.isLoadingHistory}
          />
        </div>

        {chat.rightPanelOpen && (
          <div className={styles.rightPanel}>
            <AgentOptionsPanel
              teamId={teamId}
              selectedLibraryIds={chat.selectedLibraryIds}
              onLibraryChange={chat.setSelectedLibraryIds}
              searchPolicy={chat.searchPolicy}
              onSearchPolicyChange={chat.setSearchPolicy}
              ragScope={chat.ragScope}
              onRagScopeChange={chat.setRagScope}
              options={chat.effectiveChatOptions}
              boundLibraryIds={chat.effectiveChatOptions?.bound_library_ids ?? undefined}
            />
          </div>
        )}
      </div>
    </div>
  );
}
