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

import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { userDisplayName } from "@core/utils/userDisplayName";
import { resolveAnnouncementText } from "../../../../features/announcements/announcementText";
import {
  useAnnouncePatchNotesMutation,
  usePatchNoteAnnouncementQuery,
  useUsersByIdsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PatchNoteAnnouncer.module.css";

/**
 * "Announce the update": the only thing that opens the What's new dialog on its
 * own, for every user at their next load. Beside it, when and by whom it was
 * last used; that line empties when hiding the last note cancels the announcement.
 */
export default function PatchNoteAnnouncer({ visibleNotes }: { visibleNotes: Announcement[] }) {
  const { t, i18n } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { data: announcement } = usePatchNoteAnnouncementQuery();
  const [announce, { isLoading }] = useAnnouncePatchNotesMutation();
  const actorId = announcement?.announced_by;
  const { data: actors = [] } = useUsersByIdsQuery({ ids: actorId ? [actorId] : [] }, { skip: !actorId });

  const first = visibleNotes[0];

  const confirmed = async () => {
    try {
      await announce().unwrap();
      showSuccess({ summary: t("rework.announcements.patchNote.announce.done") });
    } catch (error: unknown) {
      showError({
        summary: t("rework.announcements.patchNote.announce.failed"),
        detail: normalizeApiError(error).detail,
      });
    }
  };

  const ask = () =>
    showConfirmationDialog({
      title: t("rework.announcements.patchNote.announce.confirm.title"),
      message: t("rework.announcements.patchNote.announce.confirm.message", {
        count: visibleNotes.length,
        title: resolveAnnouncementText(first.title, i18n.language) || first.id,
      }),
      confirmButtonLabel: t("rework.announcements.patchNote.announce.confirm.confirm"),
      onConfirm: () => void confirmed(),
    });

  const lastUse =
    announcement &&
    t("rework.announcements.patchNote.announce.lastUse", {
      date: new Date(announcement.announced_at).toLocaleString(i18n.language, {
        dateStyle: "medium",
        timeStyle: "short",
      }),
      name: actorId
        ? userDisplayName(
            actorId,
            actors.find((actor) => actor.id === actorId),
          )
        : t("rework.announcements.history.unknownActor"),
    });

  return (
    <div className={styles.announcer}>
      <Button
        type="button"
        color="primary"
        variant="outlined"
        size="medium"
        icon={{ category: "outlined", type: "campaign" }}
        disabled={!first || isLoading}
        onClick={ask}
      >
        {t("rework.announcements.patchNote.announce.action")}
      </Button>
      {/* Polite: the line changes on its own when a toggle cancels the announcement. */}
      <p className={styles.lastUse} aria-live="polite">
        {first ? lastUse : t("rework.announcements.patchNote.announce.noneVisible")}
      </p>
    </div>
  );
}
