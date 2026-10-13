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

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { usePatchNoteHistoryQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { PatchNote } from "@shared/molecules/PatchNoteDialog/PatchNoteDialog";
import { resolveAnnouncementText } from "./announcementText";

/**
 * The patch notes a user can read, in the administrator's order and resolved to
 * the viewer's locale, plus the announcement still pending for this user. A note
 * with no text to show is left out, so positions count readable notes only.
 */
export function usePatchNoteHistory() {
  const { i18n } = useTranslation();
  const { data } = usePatchNoteHistoryQuery();
  const notes = useMemo(
    () =>
      (data?.patch_notes ?? []).flatMap((note): PatchNote[] => {
        // Title and body share their locales, so both resolve to the same language.
        const title = resolveAnnouncementText(note.title, i18n.language);
        const markdown = resolveAnnouncementText(note.description_long, i18n.language);
        return title?.trim() && markdown?.trim() ? [{ id: note.id, title, markdown }] : [];
      }),
    [data, i18n.language],
  );
  return { notes, pendingAnnouncementId: data?.pending_announcement_id ?? null, loaded: data !== undefined };
}
