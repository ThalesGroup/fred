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
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import TextArea from "@shared/atoms/TextArea/TextArea";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { relativeTime } from "@rework/features/tasks/taskLabels";
import {
  useAgentMemoryQuery,
  useForgetAgentMemoryNoteMutation,
  useRememberAgentMemoryNoteMutation,
} from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { AgentMemoryNote } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./MemorySection.module.css";

/** Mirrors the Control Plane limits on one agent's memory. */
const MAX_NOTE_LENGTH = 500;
const MAX_ACTIVE_NOTES = 50;

type MemorySectionProps = {
  spaceId: string;
  agentInstanceId: string;
};

/** The agent's memory, as its editors manage it: the active notes, a field to
 * add one, and the recently removed notes. Changes apply at once, outside the
 * form's Save. */
export function MemorySection({ spaceId, agentInstanceId }: MemorySectionProps) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const scope = { spaceId, agentInstanceId };
  const { currentData, isLoading, isError, refetch } = useAgentMemoryQuery(
    { ...scope, includeForgotten: true },
    { refetchOnMountOrArgChange: true },
  );
  const [remember, { isLoading: adding }] = useRememberAgentMemoryNoteMutation();
  const [forget] = useForgetAgentMemoryNoteMutation();
  const [draft, setDraft] = useState("");
  const [removing, setRemoving] = useState<string | null>(null);

  const notes = currentData?.notes ?? [];
  const active = notes.filter((note) => !note.forgotten_at);
  const forgotten = notes.filter((note) => note.forgotten_at);
  const full = active.length >= MAX_ACTIVE_NOTES;

  const who = (name: string | null) => name ?? t("rework.mcp.authorUnavailable");
  const when = (iso: string) => relativeTime(Date.parse(iso), t);

  const add = async () => {
    const content = draft.trim();
    if (!content) return;
    try {
      await remember({ ...scope, rememberAgentMemoryNoteRequest: { content } }).unwrap();
      setDraft("");
    } catch (error) {
      const code = (error as { data?: { code?: string } } | undefined)?.data?.code;
      showError({
        summary: t(code === "memory_full" ? "capability.memory.manage.full" : "capability.memory.manage.addFailed"),
      });
    }
  };

  const remove = async (note: AgentMemoryNote) => {
    setRemoving(note.note_id);
    try {
      await forget({ ...scope, noteId: note.note_id }).unwrap();
    } catch {
      showError({ summary: t("capability.memory.manage.removeFailed") });
    } finally {
      setRemoving(null);
    }
  };

  if (isLoading) return <Spinner size={20} />;
  if (isError && !currentData) {
    return (
      <div className={styles.section}>
        <span className={styles.empty}>{t("capability.memory.manage.loadFailed")}</span>
        <div>
          <Button color="primary" variant="text" size="small" onClick={() => void refetch()}>
            {t("capability.memory.manage.retry")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.section}>
      {active.length === 0 ? (
        <span className={styles.empty}>{t("capability.memory.manage.empty")}</span>
      ) : (
        <ul className={styles.list} aria-label={t("capability.memory.manage.listAria")}>
          {active.map((note) => (
            <li key={note.note_id} className={styles.note}>
              <span className={styles.noteBody}>
                <span className={styles.content}>{note.content}</span>
                <span className={styles.meta}>
                  {t("capability.memory.manage.addedBy", { user: who(note.created_by_name) })}
                  {` · ${when(note.created_at)}`}
                </span>
              </span>
              <IconButton
                variant="icon"
                size="medium"
                color="on-surface-retreat"
                icon={{ category: "outlined", type: "delete" }}
                title={t("capability.memory.manage.remove")}
                loading={removing === note.note_id}
                onClick={() => void remove(note)}
              />
            </li>
          ))}
        </ul>
      )}

      <div className={styles.add}>
        <TextArea
          label={t("capability.memory.manage.newNote")}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          rows={2}
          maxLength={MAX_NOTE_LENGTH}
          disabled={adding || full}
          explanation={full ? t("capability.memory.manage.full") : undefined}
        />
        <div>
          <Button
            color="primary"
            variant="tonal"
            size="small"
            icon={{ category: "outlined", type: "add" }}
            disabled={adding || full || !draft.trim()}
            onClick={() => void add()}
          >
            {t("capability.memory.manage.add")}
          </Button>
        </div>
      </div>

      {forgotten.length > 0 && (
        <Disclosure title={t("capability.memory.manage.history")}>
          <ul className={styles.list}>
            {forgotten.map((note) => (
              <li key={note.note_id} className={styles.historyItem}>
                <span className={styles.content}>{note.content}</span>
                <span className={styles.meta}>
                  {t("capability.memory.manage.removedBy", { user: who(note.forgotten_by_name) })}
                  {` · ${when(note.forgotten_at as string)}`}
                </span>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </div>
  );
}
