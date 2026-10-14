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
import type { PatchNoteSnapshot } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { resolveAnnouncementText } from "./announcementText";

/**
 * Announced patch notes resolved to the viewer's locale, in their order. One
 * with no text to show is left out, so positions count readable notes only.
 */
export function resolvePatchNotes(snapshots: PatchNoteSnapshot[], language: string): PatchNote[] {
  return snapshots.flatMap((note): PatchNote[] => {
    // Title and body share their locales, so both resolve to the same language.
    const title = resolveAnnouncementText(note.title, language);
    const markdown = resolveAnnouncementText(note.description_long, language);
    return title?.trim() && markdown?.trim() ? [{ id: note.id, title, markdown }] : [];
  });
}

/**
 * What "What's new" shows: the package of the announcement in effect, frozen
 * when it was announced, plus that announcement's id while this user has not seen it.
 */
export function usePatchNoteHistory() {
  const { i18n } = useTranslation();
  const { data } = usePatchNoteHistoryQuery();
  const notes = useMemo(() => resolvePatchNotes(data?.patch_notes ?? [], i18n.language), [data, i18n.language]);
  return { notes, pendingAnnouncementId: data?.pending_announcement_id ?? null, loaded: data !== undefined };
}
