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
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { userDisplayName } from "@core/utils/userDisplayName";
import { resolveAnnouncementText } from "../../../../features/announcements/announcementText";
import {
  useAnnouncePatchNotesMutation,
  usePatchNoteAnnouncementQuery,
  useUsersByIdsQuery,
  useWithdrawPatchNoteAnnouncementMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PatchNoteAnnouncer.module.css";

const KEYS = "rework.announcements.patchNote.announce";

/** Most patch notes one announcement may hold; the server refuses more. */
export const MAX_PATCH_NOTES_PER_ANNOUNCEMENT = 10;

interface PatchNoteAnnouncerProps {
  /** The included patch notes, in order: what the next announcement freezes. */
  includedNotes: Announcement[];
  /** A toggle, a reorder or a reload is under way: the list is not yet the server's. */
  settling?: boolean;
  /** The server refused the confirmed list as out of date. */
  onSelectionChanged?: () => void;
}

/**
 * "Announce the update" freezes the included patch notes as what users read,
 * until the next announcement; nothing else reaches them. Beside it, when and
 * by whom it was last used, and a way to withdraw the announcement in effect.
 */
export default function PatchNoteAnnouncer({ includedNotes, settling, onSelectionChanged }: PatchNoteAnnouncerProps) {
  const { t, i18n } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { data: announcement } = usePatchNoteAnnouncementQuery();
  const [announce, { isLoading: isAnnouncing }] = useAnnouncePatchNotesMutation();
  const [withdraw, { isLoading: isWithdrawing }] = useWithdrawPatchNoteAnnouncementMutation();
  const [confirming, setConfirming] = useState(false);
  const actorId = announcement?.announced_by;
  const { data: actors = [] } = useUsersByIdsQuery({ ids: actorId ? [actorId] : [] }, { skip: !actorId });

  const run = async (action: () => Promise<unknown>, keys: string) => {
    try {
      await action();
      showSuccess({ summary: t(`${keys}.done`) });
    } catch (error: unknown) {
      showError({ summary: t(`${keys}.failed`), detail: normalizeApiError(error).detail });
    }
  };

  // The ids sent are the list the confirmation showed: the server freezes
  // those or refuses, so nothing else can reach users.
  const announceConfirmed = async () => {
    try {
      await announce({ patchNoteAnnounceRequest: { ids: includedNotes.map((note) => note.id) } }).unwrap();
      showSuccess({ summary: t(`${KEYS}.done`) });
    } catch (error: unknown) {
      const { status, detail } = normalizeApiError(error);
      if (status === 409) {
        onSelectionChanged?.();
        showError({ summary: t(`${KEYS}.changed`) });
      } else {
        showError({ summary: t(`${KEYS}.failed`), detail });
      }
    }
  };

  const tooMany = includedNotes.length > MAX_PATCH_NOTES_PER_ANNOUNCEMENT;

  const askWithdraw = () =>
    showConfirmationDialog({
      title: t(`${KEYS}.withdraw.title`),
      message: t(`${KEYS}.withdraw.message`),
      confirmButtonLabel: t(`${KEYS}.withdraw.confirm`),
      criticalAction: true,
      onConfirm: () => void run(() => withdraw().unwrap(), `${KEYS}.withdraw`),
    });

  const lastUse =
    announcement &&
    t(`${KEYS}.lastUse`, {
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
        variant="tonal"
        size="medium"
        icon={{ category: "outlined", type: "campaign" }}
        disabled={includedNotes.length === 0 || tooMany || settling || isAnnouncing}
        onClick={() => setConfirming(true)}
      >
        {t(`${KEYS}.action`, { included: includedNotes.length, max: MAX_PATCH_NOTES_PER_ANNOUNCEMENT })}
      </Button>
      <p className={styles.lastUse} aria-live="polite">
        {tooMany
          ? t(`${KEYS}.tooMany`, { max: MAX_PATCH_NOTES_PER_ANNOUNCEMENT })
          : lastUse || (includedNotes.length === 0 && t(`${KEYS}.noneIncluded`))}
      </p>
      {announcement && (
        <div className={styles.withdraw}>
          <Button
            type="button"
            color="error"
            variant="text"
            size="medium"
            disabled={isWithdrawing}
            onClick={askWithdraw}
          >
            {t(`${KEYS}.withdraw.action`)}
          </Button>
        </div>
      )}

      {/* The list is the question: what is shown here is exactly what gets frozen. */}
      <ConfirmationDialog
        open={confirming}
        title={t(`${KEYS}.confirm.title`)}
        message={t(`${KEYS}.confirm.message`)}
        details={
          <ol className={styles.included} aria-label={t(`${KEYS}.confirm.list`)}>
            {includedNotes.map((note) => (
              <li key={note.id}>{resolveAnnouncementText(note.title, i18n.language) || note.id}</li>
            ))}
          </ol>
        }
        confirmLabel={t(`${KEYS}.confirm.confirm`)}
        cancelLabel={t("common.cancel")}
        onConfirm={() => {
          setConfirming(false);
          void announceConfirmed();
        }}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}
