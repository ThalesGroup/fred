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

import Icon from "@shared/atoms/Icon/Icon";
import { TaskIndicator } from "@shared/molecules/TaskIndicator/TaskIndicator";
import type { ChatAttachment } from "@rework/types/attachments";
import styles from "./AttachmentChips.module.css";

interface AttachmentChipsProps {
  attachments: ChatAttachment[];
  onRemove: (id: string) => void;
}

function fileLabel(attachment: ChatAttachment): string {
  if (attachment.status === "uploading") return "Uploading";
  if (attachment.status === "error") return "Failed";
  if (attachment.status === "ingesting") return "Processing";
  return attachment.isImage ? "Image" : "File";
}

export function AttachmentChips({ attachments, onRemove }: AttachmentChipsProps) {
  if (attachments.length === 0) return null;

  return (
    <div className={styles.chips} aria-label="Attached files">
      {attachments.map((attachment) => (
        <span key={attachment.id} className={styles.chip} data-status={attachment.status}>
          <span className={styles.icon} aria-hidden>
            <Icon category="outlined" type={attachment.isImage ? "image" : "attach_file"} />
          </span>
          <span className={styles.text}>
            <span className={styles.name} title={attachment.name}>
              {attachment.name}
            </span>
            <span className={styles.meta}>{fileLabel(attachment)}</span>
          </span>
          {attachment.taskIds.map((taskId) => (
            <TaskIndicator key={taskId} taskId={taskId} size="sm" />
          ))}
          <button
            type="button"
            className={styles.remove}
            onClick={() => onRemove(attachment.id)}
            aria-label={`Remove ${attachment.name}`}
          >
            <Icon category="outlined" type="close" />
          </button>
        </span>
      ))}
    </div>
  );
}
