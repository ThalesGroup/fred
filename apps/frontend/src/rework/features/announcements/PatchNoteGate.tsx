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

// Opens the active patch note once per sign-in, at app load, unless the user
// ticked "Don't show again" on this edition. Mounted inside GcuGuard/BootstrapGuard
// (see App.tsx), above the router, so it never remounts on navigation.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PatchNoteDialog } from "@shared/molecules/PatchNoteDialog/PatchNoteDialog";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useDismissPatchNoteMutation } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { markClosedThisSession, wasClosedThisSession } from "./patchNoteSession";
import { useActivePatchNote } from "./useActivePatchNote";

export default function PatchNoteGate() {
  const { t } = useTranslation();
  const { showError } = useToast();
  const active = useActivePatchNote();
  const [dismissPatchNote] = useDismissPatchNoteMutation();
  // Also held in state so failing storage cannot reopen it on rerender.
  const [closedEdition, setClosedEdition] = useState<string | null>(null);

  if (!active || active.dismissed) return null;
  const { note, title, markdown } = active;
  const edition = `${note.id}.${note.content_version}`;
  if (edition === closedEdition || wasClosedThisSession(note)) return null;

  const onClose = (dontShowAgain: boolean) => {
    markClosedThisSession(note);
    setClosedEdition(edition);
    if (dontShowAgain) {
      dismissPatchNote({ announcementId: note.id })
        .unwrap()
        .catch(() => showError({ summary: t("rework.announcements.patchNote.dismissFailed") }));
    }
  };

  return <PatchNoteDialog open title={title} markdown={markdown} onClose={onClose} />;
}
