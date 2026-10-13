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
import IconButton from "../../atoms/IconButton/IconButton";
import { Dialog } from "../Dialog/Dialog";
import { PatchNoteBody } from "./PatchNoteBody";
import styles from "./PatchNoteDialog.module.css";

/** One patch note as the dialog shows it, already resolved to the viewer's locale. */
export interface PatchNote {
  id: string;
  title: string;
  markdown: string;
}

export interface PatchNoteDialogProps {
  open: boolean;
  /** The readable patch notes, newest first as the administrator ordered them. */
  notes: PatchNote[];
  /** Called by Close, Escape and the scrim alike. */
  onClose: () => void;
}

/**
 * The "What's new" dialog: the patch-note history, opened on its first entry.
 * Users get it after an announcement and from their profile menu; the admin
 * preview renders this same component with a single note.
 */
export function PatchNoteDialog({ open, notes, onClose }: PatchNoteDialogProps) {
  const { t } = useTranslation();
  const [position, setPosition] = useState(0);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const navigationRef = useRef<HTMLElement | null>(null);

  // The list can shrink under an open dialog when an administrator hides a note.
  const index = Math.min(position, notes.length - 1);
  const note = notes[index];
  const atEnd = index === 0 || index === notes.length - 1;

  // A button that reaches its end goes disabled and would drop the keyboard
  // focus out of the dialog: hand it to the other one.
  useEffect(() => {
    const navigation = navigationRef.current;
    if (!atEnd || !navigation?.contains(document.activeElement)) return;
    navigation.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
  }, [atEnd, index]);

  if (!note) return null;

  const close = () => {
    setPosition(0);
    onClose();
  };
  const move = (to: number) => {
    setPosition(to);
    // Dialog scrolls the element holding this body: show the next note from its top.
    const scroller = bodyRef.current?.parentElement;
    if (scroller) scroller.scrollTop = 0;
  };

  return (
    <Dialog
      open={open}
      title={note.title}
      confirmLabel={t("rework.announcements.dialog.close")}
      onConfirm={close}
      onCancel={close}
      hideCancel
      maxWidth={720}
      dividers
      // On the dialog, not on a link or copy button inside the note: the note
      // opens at its top and a screen reader starts from its title.
      initialFocus="dialog"
      footerStart={
        notes.length > 1 && (
          <nav
            ref={navigationRef}
            className={styles.navigation}
            aria-label={t("rework.announcements.patchNote.dialog.navigation")}
          >
            <IconButton
              variant="icon"
              size="medium"
              icon={{ category: "outlined", type: "chevron_left" }}
              aria-label={t("rework.announcements.patchNote.dialog.newer")}
              disabled={index === 0}
              onClick={() => move(index - 1)}
            />
            <span className={styles.position} aria-live="polite">
              {index + 1} / {notes.length}
            </span>
            <IconButton
              variant="icon"
              size="medium"
              icon={{ category: "outlined", type: "chevron_right" }}
              aria-label={t("rework.announcements.patchNote.dialog.older")}
              disabled={index === notes.length - 1}
              onClick={() => move(index + 1)}
            />
          </nav>
        )
      }
    >
      <div ref={bodyRef} className={styles.body} data-navigable={notes.length > 1 || undefined}>
        <PatchNoteBody markdown={note.markdown} />
      </div>
    </Dialog>
  );
}

export default PatchNoteDialog;
