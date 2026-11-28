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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  useAgentMemoryQuery,
  useEditAgentMemoryNoteMutation,
  useForgetAgentMemoryNoteMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { UiPartRendererProps } from "../types";
import type { MemoryNotePartData } from "./types";
import { useChatAgentScope } from "./useChatAgentScope";
import styles from "./MemoryNoteCard.module.css";

/** One note the agent remembered, edited or forgot during the turn. A
 * remembered note can be undone here with the person's own credentials; an
 * edited note can be put back to the text it replaced. */
export function MemoryNoteCard({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const note = part as unknown as MemoryNotePartData;
  const { spaceId, agentInstanceId } = useChatAgentScope();
  const remembered = note.action === "remembered";
  const edited = note.action === "edited";
  const previousContent = edited ? note.previous_content : null;
  const undoable = remembered || Boolean(previousContent);
  const scope = spaceId && agentInstanceId ? { spaceId, agentInstanceId } : undefined;

  // The note may have changed since (from this card, another chat or the
  // agent settings). Only a note listed as forgotten or replaced counts as
  // inactive: a note missing from a stale list is assumed still there.
  const { currentData } = useAgentMemoryQuery(
    { spaceId: spaceId ?? "", agentInstanceId: agentInstanceId ?? "", includeForgotten: true },
    { skip: !undoable || !scope, refetchOnMountOrArgChange: true },
  );
  const stored = currentData?.notes.find((entry) => entry.note_id === note.note_id);
  const [forget, { isLoading: forgetting }] = useForgetAgentMemoryNoteMutation();
  const [editNote, { isLoading: editing }] = useEditAgentMemoryNoteMutation();
  const [undone, setUndone] = useState(false);
  const inactive = undone || Boolean(stored?.forgotten_at);
  const statusRef = useRef<HTMLSpanElement>(null);

  // The undo button unmounts once it succeeds: focus moves to the status that replaces it.
  useEffect(() => {
    if (undone) statusRef.current?.focus();
  }, [undone]);

  const undo = async () => {
    if (!scope) return;
    try {
      if (previousContent) {
        await editNote({
          ...scope,
          noteId: note.note_id,
          rememberAgentMemoryNoteRequest: { content: previousContent },
        }).unwrap();
      } else {
        await forget({ ...scope, noteId: note.note_id }).unwrap();
      }
      setUndone(true);
    } catch {
      showError({ summary: t(edited ? "capability.memory.card.editUndoFailed" : "capability.memory.card.undoFailed") });
    }
  };

  const text = () => {
    if (edited) {
      return undone ? (
        <span ref={statusRef} role="status" tabIndex={-1}>
          {t("capability.memory.card.editUndone")}
        </span>
      ) : (
        t("capability.memory.card.edited", { content: note.content })
      );
    }
    if (!remembered) return t("capability.memory.card.forgotten", { content: note.content });
    return inactive ? (
      <span ref={statusRef} role="status" tabIndex={-1}>
        {t("capability.memory.card.removed")}
      </span>
    ) : (
      t("capability.memory.card.remembered", { content: note.content })
    );
  };

  return (
    <div className={styles.card} role="note" aria-label={t("capability.memory.name")}>
      <span className={styles.icon} aria-hidden>
        <Icon category="outlined" type="neurology" />
      </span>
      <span className={styles.text}>{text()}</span>
      {undoable && !inactive && scope && (
        <Button
          color="primary"
          variant="text"
          size="small"
          disabled={forgetting || editing}
          onClick={() => void undo()}
        >
          {t("capability.memory.card.undo")}
        </Button>
      )}
    </div>
  );
}
