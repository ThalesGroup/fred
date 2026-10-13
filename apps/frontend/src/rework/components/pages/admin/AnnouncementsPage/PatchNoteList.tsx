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

import { useMemo, useState, type ButtonHTMLAttributes, type Ref } from "react";
import { useTranslation } from "react-i18next";
import {
  closestCenter,
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type Modifier,
  type UniqueIdentifier,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import Icon from "@shared/atoms/Icon/Icon";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { resolveAnnouncementText } from "../../../../features/announcements/announcementText";
import { useSetPatchNoteOrderMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { RowActions } from "./RowControls";
import styles from "./PatchNoteList.module.css";

const verticalOnly: Modifier = ({ transform }) => ({ ...transform, x: 0 });

interface PatchNoteListProps {
  /** Every patch note, in the administrator's order. */
  notes: Announcement[];
  pendingIds: ReadonlySet<string>;
  onPreview: (note: Announcement) => void;
  onToggle: (note: Announcement, enabled: boolean) => void;
  onEdit: (note: Announcement) => void;
  onDelete: (note: Announcement) => void;
}

interface PatchNoteCardProps extends Omit<PatchNoteListProps, "notes" | "pendingIds"> {
  note: Announcement;
  pending: boolean;
  /** `placeholder` marks where a dragged card will land; `lifted` is the card under the pointer. */
  state?: "placeholder" | "lifted";
  handle?: ButtonHTMLAttributes<HTMLButtonElement> & { ref: Ref<HTMLButtonElement> };
}

/** A neutral card: patch notes have no severity, so they never read as a warning banner. */
function PatchNoteCard({ note, pending, state, handle, onPreview, onToggle, onEdit, onDelete }: PatchNoteCardProps) {
  const { t, i18n } = useTranslation();
  const title = resolveAnnouncementText(note.title, i18n.language) || note.id;
  const checkboxId = `patch-note-included-${note.id}`;
  return (
    <div className={styles.card} data-state={state}>
      <button
        type="button"
        className={styles.handle}
        aria-label={t("rework.announcements.patchNote.row.move", { title })}
        {...handle}
      >
        <Icon category="outlined" type="drag_indicator" />
      </button>
      {/* The title and status are its label: the whole text is the click target. */}
      <Tooltip
        text={
          note.enabled
            ? t("rework.announcements.patchNote.row.disableHint")
            : t("rework.announcements.patchNote.row.enableHint")
        }
      >
        <Checkbox
          id={checkboxId}
          className={styles.check}
          checked={note.enabled}
          disabled={pending}
          onChange={(event) => onToggle(note, event.target.checked)}
          aria-label={t("rework.announcements.patchNote.row.enabled")}
        />
      </Tooltip>
      <label className={styles.text} htmlFor={checkboxId}>
        <span className={styles.title}>{title}</span>
        <span className={styles.status} data-visible={note.enabled || undefined}>
          {note.enabled
            ? t("rework.announcements.patchNote.row.statusVisible")
            : t("rework.announcements.patchNote.row.statusHidden")}
        </span>
      </label>
      <div className={styles.controls}>
        <IconButton
          size="small"
          variant="icon"
          icon={{ category: "outlined", type: "visibility" }}
          aria-label={t("rework.announcements.patchNote.row.preview")}
          onClick={() => onPreview(note)}
        />
        <RowActions announcement={note} onEdit={() => onEdit(note)} onDelete={() => onDelete(note)} />
      </div>
    </div>
  );
}

function SortablePatchNote({ reducedMotion, ...card }: PatchNoteCardProps & { reducedMotion: boolean }) {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: card.note.id,
    attributes: { roleDescription: t("rework.announcements.patchNote.reorder.role") },
    transition: reducedMotion ? null : undefined,
  });
  return (
    <li
      ref={setNodeRef}
      className={styles.row}
      data-kind="patch_note"
      // The offset follows the pointer or the neighbours' slide: it cannot live in the stylesheet.
      style={{ transform: CSS.Translate.toString(transform), transition }}
    >
      <PatchNoteCard
        {...card}
        state={isDragging ? "placeholder" : undefined}
        handle={{ ref: setActivatorNodeRef, ...attributes, ...listeners }}
      />
    </li>
  );
}

/**
 * The Patch notes tab's list: its order is the order of the next announcement, and
 * the administrator changes it by dragging a card's handle or with the keyboard
 * (Space or Enter on the handle, arrows, Space or Enter again).
 */
export default function PatchNoteList({ notes, pendingIds, ...actions }: PatchNoteListProps) {
  const { t, i18n } = useTranslation();
  const { showError } = useToast();
  const [setOrder] = useSetPatchNoteOrderMutation();
  const [activeId, setActiveId] = useState<UniqueIdentifier | null>(null);
  // The order just dropped, shown until the list read back from the server
  // differs from the one it was dropped on: no jump back while the save is in flight.
  const [dropped, setDropped] = useState<{ on: string; ids: string[] } | null>(null);
  const reducedMotion = useMemo(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false, []);
  const sensors = useSensors(
    // A few pixels of travel first, so a plain click on the handle is not a drag.
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const served = notes.map((note) => note.id).join();
  const ordered = useMemo(() => {
    if (!dropped || dropped.on !== served) return notes;
    const byId = new Map(notes.map((note) => [note.id, note]));
    return dropped.ids.flatMap((id) => byId.get(id) ?? []);
  }, [notes, dropped, served]);
  const ids = ordered.map((note) => note.id);
  const active = ordered.find((note) => note.id === activeId);

  const say = (key: string, id: UniqueIdentifier, at: UniqueIdentifier = id) => {
    const note = ordered.find((candidate) => candidate.id === id);
    return t(`rework.announcements.patchNote.reorder.${key}`, {
      title: (note && resolveAnnouncementText(note.title, i18n.language)) || String(id),
      position: ids.indexOf(String(at)) + 1,
      total: ids.length,
    });
  };
  // Dropping on a card takes its place, so its current position is where the moved one lands.
  const announcements: Announcements = {
    onDragStart: ({ active }) => say("picked", active.id),
    onDragOver: ({ active, over }) => (over ? say("moved", active.id, over.id) : undefined),
    onDragEnd: ({ active, over }) => say("dropped", active.id, over?.id),
    onDragCancel: ({ active }) => say("cancelled", active.id),
  };

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    setActiveId(null);
    if (!over || active.id === over.id) return;
    const next = arrayMove(ids, ids.indexOf(String(active.id)), ids.indexOf(String(over.id)));
    setDropped({ on: served, ids: next });
    setOrder({ patchNoteOrderRequest: { ids: next } })
      .unwrap()
      .catch((error: unknown) => {
        // Back to what the server holds, unless a later drop already replaced this one.
        setDropped((current) => (current?.ids === next ? null : current));
        showError({
          summary: t("rework.announcements.patchNote.reorder.failed"),
          detail: normalizeApiError(error).detail,
        });
      });
  };

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      modifiers={[verticalOnly]}
      accessibility={{
        announcements,
        screenReaderInstructions: { draggable: t("rework.announcements.patchNote.reorder.instructions") },
      }}
      onDragStart={({ active }) => setActiveId(active.id)}
      onDragEnd={onDragEnd}
      onDragCancel={() => setActiveId(null)}
    >
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <ul className={styles.list}>
          {ordered.map((note) => (
            <SortablePatchNote
              key={note.id}
              note={note}
              pending={pendingIds.has(note.id)}
              reducedMotion={reducedMotion}
              {...actions}
            />
          ))}
        </ul>
      </SortableContext>
      <DragOverlay dropAnimation={reducedMotion ? null : undefined}>
        {active && (
          // A picture of the card being moved: its controls must not take focus or clicks.
          <div inert>
            <PatchNoteCard note={active} pending={pendingIds.has(active.id)} state="lifted" {...actions} />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}
