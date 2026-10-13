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

import { useTranslation } from "react-i18next";
import ChatSidePanel from "../ChatSidePanel/ChatSidePanel";
import styles from "./CommandPromptPanel.module.css";

interface CommandPromptPanelProps {
  open: boolean;
  onClose: () => void;
  /** For a sent turn, its own stored text: what was actually sent, never
   *  re-fetched. For a composer token, the prompt's current instructions. */
  text: string;
  command: string | null;
  promptName: string | null;
  /** Set while a composer token's prompt is being read, or when it cannot be. */
  status?: "loading" | "error";
}

/** Shows the prompt behind a command, kept out of the chat body. */
export default function CommandPromptPanel({
  open,
  onClose,
  text,
  command,
  promptName,
  status,
}: CommandPromptPanelProps) {
  const { t } = useTranslation();

  return (
    <ChatSidePanel
      open={open}
      onClose={onClose}
      title={t("chatbot.commandTurn.panelTitle")}
      persistKey="command-prompt-panel"
    >
      <div className={styles.header}>
        {promptName && <span className={styles.name}>{promptName}</span>}
        {command && <span className={styles.slug}>/{command}</span>}
      </div>
      {status ? (
        <p className={styles.text} role="status">
          {t(status === "loading" ? "chatbot.commandTurn.previewLoading" : "chatbot.commandTurn.previewError")}
        </p>
      ) : (
        <p className={styles.text}>{text}</p>
      )}
    </ChatSidePanel>
  );
}
