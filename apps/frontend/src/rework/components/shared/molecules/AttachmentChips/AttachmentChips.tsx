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

import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import { TaskIndicator } from "@shared/molecules/TaskIndicator/TaskIndicator";
import { TERMINAL_STATES, type TaskState } from "../../../../features/tasks/taskTypes";
import type { ChatAttachment } from "@rework/types/attachments";
import styles from "./AttachmentChips.module.css";

interface AttachmentChipsProps {
  attachments: ChatAttachment[];
  onRemove: (id: string) => void;
}

interface TasksRootState {
  tasks: {
    byId: Record<
      string,
      {
        taskId: string;
        state: TaskState;
      }
    >;
  };
}

function fileLabel(attachment: ChatAttachment, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (attachment.status === "uploading") return t("chatbot.attachmentChip.uploading");
  if (attachment.status === "error") return t("chatbot.attachmentChip.failed");
  if (attachment.status === "ingesting") return t("chatbot.attachmentChip.processing");
  return attachment.isImage ? t("chatbot.attachmentChip.image") : t("chatbot.attachmentChip.file");
}

function AttachmentTaskStatus({ taskIds }: { taskIds: string[] }) {
  const displayTaskId = useSelector((state: TasksRootState) => {
    const tasks = taskIds.map((taskId) => state.tasks.byId[taskId]).filter(Boolean);
    const activeTask = tasks.find((task) => !TERMINAL_STATES.has(task.state));
    const lastTask = tasks.length > 0 ? tasks[tasks.length - 1] : null;
    return activeTask?.taskId ?? lastTask?.taskId ?? null;
  });

  if (!displayTaskId) return null;
  return <TaskIndicator taskId={displayTaskId} size="sm" />;
}

export function AttachmentChips({ attachments, onRemove }: AttachmentChipsProps) {
  const { t } = useTranslation();

  if (attachments.length === 0) return null;

  return (
    <div className={styles.chips} aria-label={t("chatbot.attachmentChip.ariaLabel")}>
      {attachments.map((attachment) => (
        <span key={attachment.id} className={styles.chip} data-status={attachment.status}>
          <span className={styles.icon} aria-hidden>
            <Icon category="outlined" type={attachment.isImage ? "image" : "attach_file"} />
          </span>
          <span className={styles.text}>
            <span className={styles.name} title={attachment.name}>
              {attachment.name}
            </span>
            {attachment.taskIds.length === 0 && <span className={styles.meta}>{fileLabel(attachment, t)}</span>}
          </span>
          <AttachmentTaskStatus taskIds={attachment.taskIds} />
          <button
            type="button"
            className={styles.remove}
            onClick={() => onRemove(attachment.id)}
            aria-label={t("chatbot.attachmentChip.removeAria", { name: attachment.name })}
          >
            <Icon category="outlined" type="close" />
          </button>
        </span>
      ))}
    </div>
  );
}
