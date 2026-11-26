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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  useAgentMemoryQuery,
  useForgetAgentMemoryNoteMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { UiPartRendererProps } from "../types";
import type { MemoryNotePartData } from "./types";
import { useChatAgentScope } from "./useChatAgentScope";
import styles from "./MemoryNoteCard.module.css";

/** One note the agent remembered or forgot during the turn. A remembered note
 * can be undone here with the person's own credentials. */
export function MemoryNoteCard({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const note = part as unknown as MemoryNotePartData;
  const { spaceId, agentInstanceId } = useChatAgentScope();
  const remembered = note.action === "remembered";
  const scope = spaceId && agentInstanceId ? { spaceId, agentInstanceId } : undefined;

  // The note may have been removed since (from this card, another chat or the
  // agent settings). Only a note listed as forgotten counts as removed: a note
  // missing from a stale list is assumed still there.
  const { currentData } = useAgentMemoryQuery(
    { spaceId: spaceId ?? "", agentInstanceId: agentInstanceId ?? "", includeForgotten: true },
    { skip: !remembered || !scope, refetchOnMountOrArgChange: true },
  );
  const stored = currentData?.notes.find((entry) => entry.note_id === note.note_id);
  const [forget, { isLoading }] = useForgetAgentMemoryNoteMutation();
  const [undone, setUndone] = useState(false);
  const removed = !remembered || undone || Boolean(stored?.forgotten_at);

  const undo = async () => {
    if (!scope) return;
    try {
      await forget({ ...scope, noteId: note.note_id }).unwrap();
      setUndone(true);
    } catch {
      showError({ summary: t("capability.memory.card.undoFailed") });
    }
  };

  return (
    <div className={styles.card} role="note" aria-label={t("capability.memory.name")}>
      <span className={styles.icon} aria-hidden>
        <Icon category="outlined" type="neurology" />
      </span>
      <span className={styles.text}>
        {removed && remembered && <span role="status">{t("capability.memory.card.removed")}</span>}
        {removed && !remembered && t("capability.memory.card.forgotten", { content: note.content })}
        {!removed && t("capability.memory.card.remembered", { content: note.content })}
      </span>
      {!removed && scope && (
        <Button color="primary" variant="text" size="small" disabled={isLoading} onClick={() => void undo()}>
          {t("capability.memory.card.undo")}
        </Button>
      )}
    </div>
  );
}
