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

import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import Checkbox from "../../atoms/Checkbox/Checkbox";
import { Dialog } from "../Dialog/Dialog";
import { PatchNoteBody } from "./PatchNoteBody";
import styles from "./PatchNoteDialog.module.css";

export interface PatchNoteDialogProps {
  open: boolean;
  /** The patch note's title, already resolved to the viewer's locale. */
  title: string;
  /** The patch note's body, already resolved to the viewer's locale. */
  markdown: string;
  /** Off when the user reopens the note on purpose: there is nothing to dismiss then. */
  showDontShowAgain?: boolean;
  /** `dontShowAgain` is the checkbox state, reported by Close, Escape and the scrim alike. */
  onClose: (dontShowAgain: boolean) => void;
}

/**
 * The "What's new" dialog users get at load. The admin preview renders this
 * same component, which is what makes the preview trustworthy.
 */
export function PatchNoteDialog({ open, title, markdown, showDontShowAgain = true, onClose }: PatchNoteDialogProps) {
  const { t } = useTranslation();
  const checkboxId = useId();
  const [dontShowAgain, setDontShowAgain] = useState(false);

  const close = (remember: boolean) => {
    setDontShowAgain(false);
    onClose(remember);
  };

  return (
    <Dialog
      open={open}
      title={title}
      confirmLabel={t("rework.announcements.dialog.close")}
      onConfirm={() => close(dontShowAgain)}
      onCancel={() => close(dontShowAgain)}
      hideCancel
      maxWidth={720}
      dividers
      // On the dialog, not on a link or copy button inside the note: the note
      // opens at its top and a screen reader starts from its title.
      initialFocus="dialog"
      actionsAddon={
        showDontShowAgain && (
          <span className={styles.dontShowAgain}>
            <Checkbox
              id={checkboxId}
              checked={dontShowAgain}
              onChange={(event) => setDontShowAgain(event.target.checked)}
            />
            <label htmlFor={checkboxId} className={styles.dontShowAgainLabel}>
              {t("rework.announcements.patchNote.dialog.dontShowAgain")}
            </label>
          </span>
        )
      }
    >
      <div className={styles.body}>
        <PatchNoteBody markdown={markdown} />
      </div>
    </Dialog>
  );
}

export default PatchNoteDialog;
