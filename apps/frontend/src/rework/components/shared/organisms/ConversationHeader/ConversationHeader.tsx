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

import Button from "@shared/atoms/Button/Button";
import { TogglePanelButton } from "@shared/atoms/TogglePanelButton/TogglePanelButton";
import { SessionTitleEditor } from "@shared/molecules/SessionTitleEditor/SessionTitleEditor";
import styles from "./ConversationHeader.module.css";

interface ConversationHeaderProps {
  agentDisplayName: string;
  sessionId: string | null;
  sessionTitle: string | null;
  rightPanelOpen: boolean;
  onTitleCommit: (title: string) => void;
  onNewConversation: () => void;
  onToggleRightPanel: () => void;
}

export function ConversationHeader({
  agentDisplayName,
  sessionId,
  sessionTitle,
  rightPanelOpen,
  onTitleCommit,
  onNewConversation,
  onToggleRightPanel,
}: ConversationHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.meta}>
        <span className={styles.agentName}>{agentDisplayName}</span>
        {sessionId && sessionTitle != null && <SessionTitleEditor title={sessionTitle} onCommit={onTitleCommit} />}
      </div>
      <Button color="on-surface" variant="text" size="small" onClick={onNewConversation}>
        New conversation
      </Button>
      <TogglePanelButton open={rightPanelOpen} onClick={onToggleRightPanel} />
    </header>
  );
}
